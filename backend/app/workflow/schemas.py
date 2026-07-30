from dataclasses import dataclass
from typing import Any
from pydantic import BaseModel, Field

# ==== Workflow Payload ====
class BaseWorkflowPayload(BaseModel):
    """모든 워크플로 페이로드의 기본 클래스"""
    def to_initial_data(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class GatewayTestPayload(BaseWorkflowPayload):
    signal: str = Field(..., description="Gateway 분기 처리를 위한 시그널 값")



# ==== Workflow Reponse ====
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



# ==== API Request Body ====
class ProcessApplyRequest(BaseModel):
    """BPMN XML 업로드 및 프로세스 실행"""
    xml : str = Field(..., description="BPMN XML 문자열")




# ==== API Response Body ====
class ProcessApplyResponseData(BaseModel):
    workflow_id: str
    status : str
    events_url: str

class ProcessApplyResponse(BaseModel):
    """프로세스 시작 API 응답 규격"""
    code: str
    message: str
    data: ProcessApplyResponseData