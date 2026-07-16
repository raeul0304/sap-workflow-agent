# LangGraph State 정의 (signal, current_user, pending_task 등) - # State 스키마 (TypedDict/Pydantic)
from typing import Any, Literal, TypedDict
from typing_extensions import NotRequired


WorkflowStatus = Literal["RUNNING", "WAITING", "COMPLETED", "FAILED"]

class RequestContext(TypedDict):
    """그래프 실행을 요청한 사용자의 정보"""
    user_id: str
    roles: list[str]


class RoutingResult(TypedDict):
    """LLM이 사용자 요청을 분석한 결과"""

    intent: str
    workflow_type: str
    parameters: dict[str, Any]


class HumanTaskPayload(TypedDict):
    """State와 interrupt payload에 사용할 Human Task 정보"""

    task_id: str
    bpmn_id: str | None
    task_name: str
    lane: str | None


class HumanTaskResponse(TypedDict):
     """Command를 통해 전달받는 Human Task 처리 정보"""

     actor_id: str
     actor_roles: list[str]
     output: dict[str, Any]


class AgentState(TypedDict):
    # 최초 사용자 요청
    user_input: str
    requester: RequestContext

    # LLM 라우팅 결과
    routing: NotRequired[RoutingResult]

    # SpiffWorkflow 실행 상태
    workflow_id: NotRequired[str]
    status: NotRequired[WorkflowStatus]
    human_tasks: NotRequired[list[HumanTaskPayload]]
    data: NotRequired[dict[str, Any]]

    # 가장 최근 Human Task 응답
    human_task_response: NotRequired[HumanTaskResponse]

    # 최종 사용자 응답
    final_response: NotRequired[str]

    # 오류 정보
    error: NotRequired[str]

