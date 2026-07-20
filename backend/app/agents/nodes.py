from __future__ import annotations
from dataclasses import asdict, is_dataclass
from typing import Any, cast
from langgraph.types import interrupt
from app.agents.state import AgentState, HumanTaskPayload, HumanTaskResponse, RoutingResult
from app.workflow.spiff_engine import HumanTaskInfo, SpiffEngine, WorkflowExecutionResult


class WorkflowNodes:
    """SpiffWorkflow 실행과 관련된 LangGraph 노드."""

    def __init__(self, spiff_engine: SpiffEngine) -> None:
        self.spiff_engine = spiff_engine


    def start_workflow(self, state: AgentState) -> dict[str, Any]:
        """라우팅 결과를 이용해 새로운 SpiffWorkflow를 시작한다."""
        routing = state.get("routing")

        if routing is None:
            return {
                "status": "FAILED",
                "error": "워크플로 실행에 필요한 routing 결과가 없습니다.",
            }

        requester = state["requester"]

        workflow_input = {
            **routing["parameters"],
            "requester_id": requester["user_id"],
            "requester_roles": requester["roles"],
            "workflow_type": routing["workflow_type"],
        }

        try:
            result = self.spiff_engine.start(**workflow_input)
        except Exception as exc:
            return {
                "status": "FAILED",
                "error": str(exc),
            }

        return self._result_to_state(result)


    def handle_human_task(self, state: AgentState) -> dict[str, Any]:
        """현재 대기 중인 Human Task에 대해 사용자 입력을 받는다."""
        workflow_id = state.get("workflow_id")
        human_tasks = state.get("human_tasks", [])

        if workflow_id is None:
            return {
                "status": "FAILED",
                "error": "재개할 workflow_id가 없습니다.",
            }

        if not human_tasks:
            return {
                "status": "FAILED",
                "error": "처리할 Human Task가 없습니다.",
            }

        # 현재 PoC에서는 동시에 여러 Human Task가 열리지 않는다고 가정한다.
        pending_task = human_tasks[0]

        resume_value = interrupt(
            {
                "type": "human_task",
                "workflow_id": workflow_id,
                "task": pending_task,
            }
        )

        response = cast(HumanTaskResponse, resume_value)

        validation_error = self._validate_human_task_response(response)

        if validation_error is not None:
            return {
                "status": "FAILED",
                "error": validation_error,
            }

        try:
            result = self.spiff_engine.complete_human_task(
                workflow_id=workflow_id,
                task_id=pending_task["task_id"],
                actor_roles=response["actor_roles"],
                output=response["output"],
            )
        except Exception as exc:
            return {
                "status": "FAILED",
                "error": str(exc),
            }

        return {
            **self._result_to_state(result),
            "human_task_response": response,
        }


    def build_final_response(self, state: AgentState) -> dict[str, Any]:
        """완료된 워크플로 결과를 최종 사용자 응답으로 변환한다."""
        status = state.get("status")

        if status == "FAILED":
            error = state.get("error", "알 수 없는 오류가 발생했습니다.")

            return {
                "final_response": f"요청 처리 중 오류가 발생했습니다: {error}",
            }

        if status != "COMPLETED":
            return {
                "final_response": "워크플로가 아직 완료되지 않았습니다.",
            }

        data = state.get("data", {})
        result_message = data.get("result_message")

        if result_message:
            final_response = str(result_message)
        else:
            final_response = "워크플로 처리가 완료되었습니다."

        return {
            "final_response": final_response,
        }


    @staticmethod
    def _result_to_state(
        result: WorkflowExecutionResult,
    ) -> dict[str, Any]:
        """SpiffEngine 실행 결과를 AgentState 갱신값으로 변환한다."""
        human_tasks = [
            WorkflowNodes._human_task_to_payload(task)
            for task in result.human_tasks
        ]

        return {
            "workflow_id": result.workflow_id,
            "status": result.status,
            "data": result.data,
            "human_tasks": human_tasks,
            "error": None,
        }


    @staticmethod
    def _human_task_to_payload(
        task: HumanTaskInfo,
    ) -> HumanTaskPayload:
        """HumanTaskInfo를 LangGraph State용 dict로 변환한다."""
        if is_dataclass(task):
            task_data = asdict(task)
        elif isinstance(task, dict):
            task_data = task
        else:
            task_data = {
                "task_id": getattr(task, "task_id", None),
                "bpmn_id": getattr(task, "bpmn_id", None),
                "task_name": getattr(task, "task_name", None),
                "lane": getattr(task, "lane", None),
            }

        return HumanTaskPayload(
            task_id=str(task_data["task_id"]),
            bpmn_id=task_data.get("bpmn_id"),
            task_name=str(task_data["task_name"]),
            lane=task_data.get("lane"),
        )


    @staticmethod
    def _validate_human_task_response(
        response: object,
    ) -> str | None:
        """interrupt 재개값이 올바른 HumanTaskResponse인지 검증한다."""
        if not isinstance(response, dict):
            return "Human Task 응답은 dict 형식이어야 합니다."

        actor_id = response.get("actor_id")
        actor_roles = response.get("actor_roles")
        output = response.get("output")

        if not isinstance(actor_id, str) or not actor_id.strip():
            return "Human Task 응답에 actor_id가 필요합니다."

        if not isinstance(actor_roles, list):
            return "Human Task 응답의 actor_roles는 list 형식이어야 합니다."

        if not all(isinstance(role, str) for role in actor_roles):
            return "actor_roles에는 문자열만 들어갈 수 있습니다."

        if not isinstance(output, dict):
            return "Human Task 응답의 output은 dict 형식이어야 합니다."

        return None