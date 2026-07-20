# tests/unit/agents/test_graph_scenario_c.py

from typing import Any

from langgraph.types import Command


def get_interrupt_value(
    result: dict[str, Any],
) -> dict[str, Any]:
    """LangGraph 실행 결과에서 interrupt payload를 꺼낸다."""
    interrupts = result.get("__interrupt__")

    assert interrupts
    assert len(interrupts) == 1

    value = interrupts[0].value

    assert isinstance(value, dict)

    return value


def test_graph_scenario_c_admin_bypasses_approval(
    workflow_graph,
    make_initial_state,
    make_config,
):
    config = make_config("graph-scenario-c-admin")

    result = workflow_graph.invoke(
        make_initial_state(
            signal="C",
            user_id="admin-001",
            roles=["ADMIN"],
        ),
        config=config,
    )

    print(result)

    assert result["status"] == "WAITING", result.get("error")

    interrupt_value = get_interrupt_value(result)
    pending_task = interrupt_value["task"]

    assert pending_task["bpmn_id"] == "UserTask_EnterName"
    assert pending_task["lane"] == "USER"

    workflow_id = result["workflow_id"]

    result = workflow_graph.invoke(
        Command(
            resume={
                "actor_id": "admin-001",
                "actor_roles": ["ADMIN"],
                "output": {
                    "name": "Alice",
                },
            }
        ),
        config=config,
    )

    print(result)

    assert result["status"] == "COMPLETED", result.get("error")
    assert result["workflow_id"] == workflow_id
    assert result["human_tasks"] == []

    assert result["data"]["name"] == "Alice"
    assert result["data"]["result_message"] == "Hello, Alice"
    assert result["final_response"] == "Hello, Alice"