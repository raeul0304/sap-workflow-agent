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


    def _execute_and_publish_event(self, workflow_id, workflow) -> None:
        """엔진을 스텝 단위로 실행하며 SSE 이벤트 발행"""
        while True:
            executed_tasks = workflow.do_engine_step()

            if not executed_tasks:
                break

            for task in executed_tasks:
                event_manager.publish_sync(workflow_id, {
                    "type": "TASK_COMPLETED",
                    "task_id": str(task.id),
                    "task_name": task.task_spec.name or task.task_spec.bpmn_id,
                    "state": task.state.name
                })


    def start(
        self,
        *,
        requester_id: str,
        requester_roles: Iterable[str],
        initial_data: dict[str, Any] | None = None,
    ) -> WorkflowExecutionResult:
        """워크플로를 새로 시작하고 Human Task에 도달할 때까지 실행."""

        # 초기화
        workflow = self._initialize_workflow(requester_id, requester_roles, initial_data)
        workflow_id = self.store.create(workflow)

        # 시작 이벤트 알림
        event_manager.publish_sync(workflow_id, {"type": "WORKFLOW_STARTED", "workflow_id": workflow_id})

        # 엔진 구ㅈ동 및 이벤트 발행
        self._execute_and_publish_event(workflow_id, workflow)

        # 마무리 및 결과 저장
        self.store.save(workflow_id, workflow)
        result = self._build_result(workflow_id=workflow_id, workflow=workflow)

        event_manager.publish_sync(workflow_id, {
            "type": "WORKFLOW_STATUS_UPDATE",
            "status": result.status
        })

        return result
    

    def complete_human_task(self, *, workflow_id: str, task_id: str, actor_roles: Iterable[str], task_data: Mapping[str, Any]) -> WorkflowExecutionResult:
        """Human Task에 사용자 입력을 반영하고 워크플로를 재개 - Human Task 수행 권한 검증 후, Task 완료 및 엔진 재개"""
        
        workflow = self.store.get(workflow_id)
        task = self._find_ready_human_task(workflow=workflow, workflow_id=workflow_id, task_id=task_id)

        # Lane 및 Task 수행 권한 검증
        ensure_task_access(task, actor_roles)

        # 사용자 입력을 Task Data에 반영
        task.data.update(dict(task_data))

        # 현재 Human Task 완료
        task.run()

        self._execute_and_publish_event(workflow_id, workflow)
        self.store.save(workflow_id, workflow)
        result = self._build_result(workflow_id=workflow_id, workflow=workflow)

        # Human Task 후 상태 업데이트 이벤트
        event_manager.publish_sync(workflow_id, {
            "type": "WORKFLOW_STATUS_UPDATE",
            "status": result.status
        })

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