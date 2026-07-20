# tests/unit/agents/test_graph_scenario_b.py


def test_graph_scenario_b(
    workflow_graph,
    make_initial_state,
    make_config,
):
    config = make_config("graph-scenario-b")

    initial_state = make_initial_state(
        signal="B",
        user_id="user-002",
        roles=["USER"],
    )

    result = workflow_graph.invoke(
        initial_state,
        config=config,
    )

    print(result)

    assert result["status"] == "COMPLETED"
    assert result["workflow_id"]
    assert result["human_tasks"] == []

    assert result["data"]["signal"] == "B"
    assert result["data"]["requester_id"] == "user-002"

    assert "tool_result" in result["data"]
    assert result["data"]["tool_result"]

    assert result["error"] is None

    snapshot = workflow_graph.get_state(config)
    assert snapshot.next == ()