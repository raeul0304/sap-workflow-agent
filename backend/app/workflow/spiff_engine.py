# SpiffWorkflow 기반 BPMN 실행 엔진
import io
import re
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from SpiffWorkflow.spiff.parser import SpiffBpmnParser
from SpiffWorkflow.bpmn.workflow import BpmnWorkflow
from SpiffWorkflow.bpmn.script_engine import PythonScriptEngine, TaskDataEnvironment
from SpiffWorkflow.task import Task
from SpiffWorkflow.util.task import TaskState
from SpiffWorkflow.bpmn.specs.bpmn_task_spec import BpmnTaskSpec

from app.tools.common import TOOL_REGISTRY
from app.auth.guardian import ensure_task_access, normalize_roles
from app.workflow.lanes import get_task_lane_info
from app.workflow.store import InMemoryWorkflowStore, workflow_store
from app.workflow.registry import WorkflowRegistry
from app.workflow.schemas import BaseWorkflowPayload, HumanTaskInfo, WorkflowExecutionResult
from app.workflow.events import event_manager


# ===== Custom Exceptions =====
class WorkflowTaskNotFoundError(KeyError):
    """workflow 내에서 특정 task_id를 찾지 못했을 때 발생"""

    def __init__(self, workflow_id: str, task_id: str):
        self.workflow_id = workflow_id
        self.task_id = task_id
        super().__init__(f"Task를 찾을 수 없습니다: {task_id} - (workflow_id : {workflow_id})")

class ToolNotFoundError(LookupError):
    """Service Task에 지정된 Tool을 찾지 못했을 때 발생"""

    def __init__(self, operation_name: str) -> None:
        self.operation_name = operation_name

        super().__init__(f"등록되지 않은 Tool입니다: operation_name = {operation_name}")




# ==== Tool, Task 연결 ====
class ToolServiceEnvironment(TaskDataEnvironment):
    """SpiffWorkflow의 TaskDataEnvironment를 상속하여, Service Task에서 Tool을 호출할 수 있도록 확장"""

    def evaluate(self, expression: str, context: dict, external_context=None):
        """eval 실패 시 원본 문자열을 그대로 반환"""
        try:
            return super().evaluate(expression, context, external_context)
        except NameError:
            return expression


    def call_service(self, task_data: dict[str, Any], operation_name: str, operation_params: dict[str, Any]) -> str:
        tool = TOOL_REGISTRY.get(operation_name)
        if tool is None:
            raise ToolNotFoundError(operation_name)
        
        params = self._normalize_operation_params(operation_params)
        result = tool(**params)

        return json.dumps(result, ensure_ascii=False, default=str)
    
    @staticmethod
    def _normalize_operation_params(operation_params: dict[str, Any]) -> dict[str, Any]:
        """SpiffWorkflow의 Service Task에서 전달된 operation_params를 Tool 호출에 맞게 변환"""
        normalized_params = {}

        for name, parameter in operation_params.items():
            if isinstance(parameter, dict) and "value" in parameter:
                normalized_params[name] = parameter["value"]
            else:
                normalized_params[name] = parameter
        
        return normalized_params


# ==== SpiffWorkflow 실행 엔진 ====
class SpiffEngine:
    """BPMN 워크플로 생성, 실행, Human Task 재개 담당"""

    def __init__(
            self, 
            *, 
            bpmn_path: str | Path | None = None,
            bpmn_xml: str | bytes | None = None,  
            process_id: str, 
            store: InMemoryWorkflowStore = workflow_store
        ) -> None:
        self.process_id = process_id
        self.store = store

        if bpmn_xml:   # DB에서 불러온 XML 문자열 파싱
            raw = bpmn_xml.encode('utf-8') if isinstance(bpmn_xml, str) else bpmn_xml

        elif bpmn_path: # 물리적 파일 파싱
            self.bpmn_path = Path(bpmn_path)
            if not self.bpmn_path.is_file():
                        raise FileNotFoundError(f"BPMN 파일을 찾을 수 없습니다: {self.bpmn_path}")
            raw = self.bpmn_path.read_bytes()

        else:
            raise ValueError("bpmn_path, bpmn_xml 중 하나는 반드시 제공되어야 합니다.")

        self._workflow_spec = self._load_workflow_spec(raw)

    
    def _load_workflow_spec(self, raw):
        """BPMN XML을 파싱하여 WorkflowSpec을 생성(실행 명세)"""
        
        normalized = self._normalize_spiff_tags(raw)
        parser = SpiffBpmnParser()

        filename = str(self.bpmn_path) if hasattr(self, 'bpmn_path') else "db_or_memory_bpmn.xml"
        
        parser.add_bpmn_io(
            io.BytesIO(normalized),
            filename=filename,
        )

        return parser.get_spec(self.process_id)
    

    @staticmethod
    def _normalize_spiff_tags(xml_bytes: bytes) -> bytes:
        """SpiffWorkflow 네임스페이스 태그명의 첫 글자를 소문자로 정규화"""
        return re.sub(
            rb"(</?spiffworkflow:)([A-Z])",
            lambda m: m.group(1) + m.group(2).lower(),
            xml_bytes,
        )
    

    @staticmethod
    def _create_script_engine() -> PythonScriptEngine:
        """SpiffWorkflow의 PythonScriptEngine을 생성 - script task, gateway, service task에서 사용할 실행 환경 생성"""
        return PythonScriptEngine(environment=ToolServiceEnvironment())



    @staticmethod
    def _get_task_type(task: Task) -> str:
        """SpiffWorkflow Task를 프론트 표시용 유형으로 변환."""

        class_name = task.task_spec.__class__.__name__.upper()

        if task.task_spec.manual:
            return "USER_TASK"

        if "SERVICE" in class_name:
            return "SERVICE_TASK"

        if "SCRIPT" in class_name:
            return "SCRIPT_TASK"

        return "ENGINE_TASK"

    @staticmethod
    def _get_task_bpmn_id(task: Task) -> str:
        return (
            getattr(task.task_spec, "bpmn_id", None)
            or task.task_spec.name
            or str(task.id)
        )

    def _publish_task_event(
        self,
        *,
        workflow_id: str,
        task: Task,
        event_type: str,
    ) -> None:
        event_manager.publish_sync(
            workflow_id,
            {
                "type": event_type,
                "event_type": event_type,
                "task_id": str(task.id),
                "bpmn_id": self._get_task_bpmn_id(task),
                "task_name": (
                    task.task_spec.name
                    or self._get_task_bpmn_id(task)
                ),
                "task_type": self._get_task_type(task),
                "state": event_type.removeprefix("TASK_"),
            },
        )



    def _initialize_workflow(self, requester_id: str, requester_roles: Iterable[str], initial_data: dict[str, Any] | None) -> BpmnWorkflow:
        """워크플로 실행에 필요한 초기 데이터 세팅 및 인스턴스 생성"""
        normalize_requester_roles = normalize_roles(requester_roles)
        workflow_data = {
            "requester_id": requester_id,
            "requester_roles": sorted(normalize_requester_roles),
            "workflow_status" : "RUNNING"
        }

        if initial_data:
            workflow_data.update(initial_data)

        workflow = BpmnWorkflow(
            self._workflow_spec,
            script_engine = self._create_script_engine()
        )
        workflow.task_tree.set_data(**workflow_data)

        return workflow


    def _execute_and_publish_event(
            self,
            workflow_id: str,
            workflow: BpmnWorkflow,
        ) -> None:
            """자동 Task를 실행하고 Task 실행 이벤트를 발행."""

            before_completed_ids = {
                str(task.id)
                for task in workflow.get_tasks(state=TaskState.COMPLETED)
            }

            started_task_ids: set[str] = set()

            BPMN_ELEMENT_TYPES = {
                "StartEvent",
                "EndEvent", 
                "ServiceTask",
                "UserTask",
                "ScriptTask",
                "ExclusiveGateway",
                "ParallelGateway",
                "InclusiveGateway",
            }
            

            def before_task_completed(task: Task) -> bool:
                """
                SpiffWorkflow가 자동 Task를 완료하기 직전에 호출한다.
                """
                print(f"[DEBUG] task spec type: {type(task.task_spec).__name__}, name: {task.task_spec.bpmn_name or task.task_spec.name}")
                type_name = type(task.task_spec).__name__

                if type_name not in BPMN_ELEMENT_TYPES:
                    return True

                self._publish_task_event(
                    workflow_id=workflow_id,
                    task=task,
                    event_type="TASK_STARTED",
                )

                return True

            def after_task_completed(task: Task) -> None:
                type_name = type(task.task_spec).__name__
                print(f"[DEBUG] after_task_completed - type: {type_name}, name: {task.task_spec.bpmn_name or task.task_spec.name}")
                if type_name not in BPMN_ELEMENT_TYPES:
                    return

                self._publish_task_event(
                    workflow_id=workflow_id,
                    task=task,
                    event_type="TASK_COMPLETED"
                )

            workflow.do_engine_steps(
                will_complete_task=before_task_completed,
                did_complete_task=after_task_completed
            )

            # after_completed_tasks = workflow.get_tasks(
            #     state=TaskState.COMPLETED
            # )

            # newly_completed_tasks = [
            #     task
            #     for task in after_completed_tasks
            #     if str(task.id) not in before_completed_ids
            # ]

            # for task in newly_completed_tasks:
            #     if self._get_task_type(task) == "ENGINE_TASK":
            #         continue

            #     self._publish_task_event(
            #         workflow_id=workflow_id,
            #         task=task,
            #         event_type="TASK_COMPLETED",
            #     )

            # 자동 Task 실행 후 READY 상태로 남은 User Task 발행
            for task in workflow.get_tasks(state=TaskState.READY):
                if not task.task_spec.manual:
                    continue

                self._publish_task_event(
                    workflow_id=workflow_id,
                    task=task,
                    event_type="TASK_STARTED",
                )

                self._publish_task_event(
                    workflow_id=workflow_id,
                    task=task,
                    event_type="TASK_WAITING",
                )


    def create_instance(
        self,
        *,
        requester_id: str,
        requester_roles: Iterable[str],
        initial_data: dict[str, Any] | None = None,
    ) -> str:
        """워크플로 인스턴스만 생성하고 아직 실행하지 않는다."""

        workflow = self._initialize_workflow(
            requester_id=requester_id,
            requester_roles=requester_roles,
            initial_data=initial_data,
        )

        workflow_id = self.store.create(workflow)
        #self.store.save(workflow_id, workflow)

        return workflow_id


    def run_instance(
        self,
        *,
        workflow_id: str,
    ) -> WorkflowExecutionResult:
        """이미 생성한 워크플로 인스턴스를 실행한다."""

        workflow = self.store.get(workflow_id)

        event_manager.publish_sync(
            workflow_id,
            {
                "type": "WORKFLOW_STARTED",
                "event_type": "WORKFLOW_STARTED",
                "status": "RUNNING",
            },
        )

        try:
            self._execute_and_publish_event(
                workflow_id=workflow_id,
                workflow=workflow,
            )

            self.store.save(workflow_id, workflow)

            result = self._build_result(
                workflow_id=workflow_id,
                workflow=workflow,
            )

            event_manager.publish_sync(
                workflow_id,
                {
                    "type": "WORKFLOW_STATUS_UPDATE",
                    "event_type": "WORKFLOW_STATUS_UPDATE",
                    "status": result.status,
                },
            )

            return result

        except Exception as exc:
            workflow.data["workflow_status"] = "FAILED"
            workflow.data["error"] = str(exc)
            self.store.save(workflow_id, workflow)

            event_manager.publish_sync(
                workflow_id,
                {
                    "type": "WORKFLOW_STATUS_UPDATE",
                    "event_type": "WORKFLOW_STATUS_UPDATE",
                    "status": "FAILED",
                    "error": str(exc),
                },
            )

            raise

    def start(
        self,
        *,
        requester_id: str,
        requester_roles: Iterable[str],
        initial_data: dict[str, Any] | None = None,
    ) -> WorkflowExecutionResult:
        """
        기존 호출부와의 호환성을 위한 함수.

        신규 API에서는 create_instance()와 run_instance()를
        나누어 호출한다.
        """

        workflow_id = self.create_instance(
            requester_id=requester_id,
            requester_roles=requester_roles,
            initial_data=initial_data,
        )

        return self.run_instance(workflow_id=workflow_id)
    

    def complete_human_task(
        self,
        *,
        workflow_id: str,
        task_id: str,
        actor_roles: Iterable[str],
        task_data: Mapping[str, Any],
    ) -> WorkflowExecutionResult:
        """User Task를 완료하고 워크플로 실행을 재개한다."""

        workflow = self.store.get(workflow_id)

        task = self._find_ready_human_task(
            workflow=workflow,
            workflow_id=workflow_id,
            task_id=task_id,
        )

        ensure_task_access(task, actor_roles)

        task.data.update(dict(task_data))
        task.run()

        self._publish_task_event(
            workflow_id=workflow_id,
            task=task,
            event_type="TASK_COMPLETED",
        )

        self._execute_and_publish_event(
            workflow_id=workflow_id,
            workflow=workflow,
        )

        self.store.save(workflow_id, workflow)

        result = self._build_result(
            workflow_id=workflow_id,
            workflow=workflow,
        )

        event_manager.publish_sync(
            workflow_id,
            {
                "type": "WORKFLOW_STATUS_UPDATE",
                "event_type": "WORKFLOW_STATUS_UPDATE",
                "status": result.status,
            },
        )

        return result
    

    @staticmethod
    def _find_ready_human_task(*, workflow: BpmnWorkflow, workflow_id: str, task_id: str) -> Task:
        """Id가 일치하는 Human Task 찾기"""
        ready_tasks = workflow.get_tasks(state=TaskState.READY)

        for task in ready_tasks:
            if (str(task.id) == task_id and task.task_spec.manual):
                return task
            
        raise WorkflowTaskNotFoundError(workflow_id=workflow_id, task_id=task_id)
    

    @staticmethod
    def _get_ready_human_tasks(workflow: BpmnWorkflow) -> tuple[HumanTaskInfo, ...]:
        """워크플로에서 현재 READY 상태인 Human Task 목록을 모두 반환"""
        human_tasks: list[HumanTaskInfo] = []

        for task in workflow.get_tasks(state=TaskState.READY):
            if not task.task_spec.manual:
                continue

            task_info = get_task_lane_info(task)

            human_tasks.append(
                HumanTaskInfo(
                    task_id=task_info.task_id,
                    bpmn_id=task_info.bpmn_id,
                    task_name=task_info.task_name,
                    lane=task_info.lane,
                )
            )

        return tuple(human_tasks)
    

    def _build_result(self, *, workflow_id: str, workflow: BpmnWorkflow) -> WorkflowExecutionResult:
        """현재 워크플로 상태를 응답용 객체로 변환"""

        human_tasks = self._get_ready_human_tasks(workflow)
        
        if workflow.is_completed():
            status = "COMPLETED"
        elif human_tasks:
            status = "WAITING"
        else:
            status = "RUNNING"

        workflow.data["workflow_status"] = status

        return WorkflowExecutionResult(
            workflow_id = workflow_id,
            status = status,
            data = dict(workflow.data),
            human_tasks = human_tasks
        )


    
    
# ==== 워크플로 연계 실행 함수 ====
def run_workflow(
        *, 
        registry: WorkflowRegistry, 
        workflow_type: str, 
        requester_id: str, 
        requester_roles: Iterable[str],
        payload: BaseWorkflowPayload | None = None,
) -> WorkflowExecutionResult:
    """registry에서 workflow_type에 맞는 엔진을 찾고, payload를 initial_data로 변환하여 실행까지 연결"""

    engine = registry.get(workflow_type)
    initial_data = payload.to_initial_data() if payload is not None else None

    return engine.start(requester_id=requester_id, requester_roles=requester_roles, initial_data=initial_data)

def run_created_workflow(
    *,
    registry: WorkflowRegistry,
    workflow_type: str,
    workflow_id: str,
) -> WorkflowExecutionResult:
    """API에서 미리 만든 워크플로 인스턴스를 백그라운드에서 실행."""

    engine = registry.get(workflow_type)

    return engine.run_instance(workflow_id=workflow_id)

def resume_workflow(
        *, 
        registry: WorkflowRegistry,
        workflow_type: str, 
        workflow_id: str, 
        task_id: str,
        actor_roles: Iterable[str],
        task_data: Mapping[str, Any]
) -> WorkflowExecutionResult:
    """workflow_type으로 엔진을 조회하고 Human Task를 완료하여 워크플로를 재개한다"""

    engine = registry.get(workflow_type)

    return engine.complete_human_task(workflow_id=workflow_id, task_id=task_id, actor_roles=actor_roles, task_data=task_data)