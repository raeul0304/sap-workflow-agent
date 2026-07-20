# tests/unit/agents/conftest.py

from collections.abc import Callable
from typing import Any
import pytest
from app.agents.graph import build_graph
from app.workflow.spiff_engine import SpiffEngine
from app.workflow.registry import WorkflowRegistry


@pytest.fixture
def workflow_registry(
    spiff_engine: SpiffEngine,
) -> WorkflowRegistry:
    registry = WorkflowRegistry()

    registry.register(
        "signal_permission_demo",
        spiff_engine,
    )

    return registry


@pytest.fixture
def workflow_graph(
    workflow_registry: WorkflowRegistry,
):
    return build_graph(workflow_registry)


@pytest.fixture
def make_initial_state() -> Callable[..., dict[str, Any]]:
    """LangGraph 테스트용 초기 State 생성 함수."""

    def factory(
        *,
        signal: str,
        user_id: str,
        roles: list[str],
    ) -> dict[str, Any]:
        return {
            "user_input": f"{signal} 시나리오를 실행해줘",
            "requester": {
                "user_id": user_id,
                "roles": roles,
            },
            "routing": {
                "intent": "run_signal_demo",
                "workflow_type": "signal_permission_demo",
                "parameters": {
                    "signal": signal,
                },
            },
        }

    return factory


@pytest.fixture
def make_config() -> Callable[[str], dict[str, Any]]:
    """LangGraph checkpointer 설정 생성 함수."""

    def factory(thread_id: str) -> dict[str, Any]:
        return {
            "configurable": {
                "thread_id": thread_id,
            }
        }

    return factory