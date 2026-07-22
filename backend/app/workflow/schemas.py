from dataclasses import dataclass
from typing import Any
from pydantic import BaseModel, Field

# ==== Request Payload ====
class BaseWorkflowPayload(BaseModel):
    """모든 워크플로 페이로드의 기본 클래스"""
    def to_initial_data(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class GatewayTestPayload(BaseWorkflowPayload):
    signal: str = Field(..., description="Gateway 분기 처리를 위한 시그널 값")




# ==== Reponse 구조 ====
@dataclass(frozen=True, slots=True)
class HumanTaskInfo:
    """Human Task 정보"""

    task_id: str
    bpmn_id: str | None
    task_name: str
    lane: str | None


@dataclass(frozen=True, slots=True)
class WorkflowExecutionResult:
    """워크플로 실행 또는 재개 결과"""
    
    workflow_id: str
    status: str
    data: dict[str, Any]
    human_tasks: tuple[HumanTaskInfo, ...]