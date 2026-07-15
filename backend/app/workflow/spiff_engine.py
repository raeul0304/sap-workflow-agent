# SpiffWorkflow 기반 BPMN 실행 엔진

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
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


# ===== Custom Exceptions =====
class WorkflowTaskNotFoundError(KeyError):
    """workflow 내에서 특정 task_id를 찾지 못했을 때 발생"""

    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(f"Task를 찾을 수 없습니다: {task_id}")

class ToolNotFoundError(LookupError):
    """Service Task에 지정된 Tool을 찾지 못했을 때 발생"""

    def __init__(self, operation_name: str) -> None:
        self.operation_name = operation_name

        super().__init__(f"등록되지 않은 Tool입니다: operation_name = {operation_name}")


# ==== Data Classes ====
@dataclass(frozen=True, slots=True)
class HumanTaskInfo:
    """Front에 전달할 Human Task 정보"""

    task_id: str
    bpmn_id: str | None
    task_name: str
    lane: str | None


@dataclass(frozen=True, slots=True)
class WorkflowExecutionResult:
    """워크플로 실행 또는 재개 결과"""
    
    workflow_id: str
    status: bool
    data: dict[str, Any]
    human_tasks: tuple[HumanTaskInfo, ...]



# ==== Tool, Task 연결 ====
class ToolServiceEnvironment(TaskDataEnvironment):
    """SpiffWorkflow의 TaskDataEnvironment를 상속하여, Service Task에서 Tool을 호출할 수 있도록 확장"""

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

        for name, parameter in operation_params.iems():
            if isinstance(parameter, dict) and "value" in parameter:
                normalized_params[name] = parameter["value"]
            else:
                normalized_params[name] = parameter
        
        return normalized_params


# ==== SpiffWorkflow 실행 엔진 ====
class SpiffEngine:
    """BPMN 워크플로 생성, 실행, Human Task 재개 담당"""

    def __init__(self, *, bpmn_path: str | Path, process_id: str, store: InMemoryWorkflowStore = workflow_store) -> None:
        self.bpmn_path = Path(bpmn_path)
        self.process_id = process_id
        self.store = store
        self._workflow_spec = self._load_workflow_spec()
    
    def _load_workflow_spec(self):
        """BPMN XML을 파싱하여 WorkflowSpec을 생성(실행 명세)"""
        if not self.bpmn_path.is_file():
            raise FileNotFoundError(f"BPMN 파일을 찾을 수 없습니다: {self.bpmn_path}")
        
        parser = SpiffBpmnParser()
        parser.add_bpmn_file(str(self.bpmn_path))

        return parser.get_spec(self.process_id)
    

    @staticmethod
    def _create_script_engine() -> PythonScriptEngine:
        """SpiffWorkflow의 PythonScriptEngine을 생성 - script task, gateway, service task에서 사용할 실행 환경 생성"""
        return PythonScriptEngine(environment=ToolServiceEnvironment())
    

    def start(self, *, signal: str, requester_id: str, requester_roles: Iterable[str],) -> WorkflowExecutionResult:
        """워크플로를 새로 시작하고, Human Task에 도달하면 실행을 멈추고 워크플로를 저장"""
        
        normalized_requester_roles = normalize_roles(requester_roles)
        workflow = BpmnWorkflow(self._workflow_spec, script_engine = self._create_script_engine())

        workflow.data.update(
            {
                "signal": signal.strip().upper(),
                "requester_id": requester_id,
                "requester_roles": sorted(normalized_requester_roles),
                "workflow_status": "RUNNING"
            }
        )

        # 엔진이 처리할 수 있는 자동 Task 실행 (Start Event, Gateway, Script/Service Task)
        workflow.do_engine_steps()
        workflow_id = self.store.create(workflow)

        return self._build_result(workflow_id=workflow_id, workflow=workflow)
    

    def complete_human_task(self, *, workflow_id: str, task_id: str, actor_roles: Iterable[str], task_data: Mapping[str, Any]) -> WorkflowExecutionResult:
        """Human Task에 사용자 입력을 반영하고 워크플로를 재개 - Human Task 수행 권한 검증 후, Task 완료 및 엔진 재개"""
        
        workflow = self.store.get(workflow_id)
        task = self._find_ready_human_task(workflow, workflow_id, task_id)

        # Lane 및 Task 수행 권한 검증
        ensure_task_access(task, actor_roles)

        # 사용자 입력을 Task Data에 반영
        task.data.update(dict(task_data))

        # 현재 Human Task 완료
        task.run()

        # 자동 Task 실행
        workflow.do_engine_steps()
        self.store.save(workflow_id, workflow)

        return self._build_result(workflow_id=workflow_id, workflow=workflow)
    

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
            status = str(workflow.data.get("workflow_status", "COMPLETED"))
        elif human_tasks:
            status = "WAITING"
        else:
            status = str(workflow.data.get("workflow_stats", "RUNNING"))

        return WorkflowExecutionResult(
            workflow_id = workflow_id,
            status = status,
            data = dict(workflow.data),
            human_tasks = human_tasks
        )


    
    
