# tests/unit/agents/test_graph_scenario_a.py


def test_graph_scenario_a(
    workflow_graph,
    make_initial_state,
    make_config,
):
    config = make_config("graph-scenario-a")

    initial_state = make_initial_state(
        signal="A",
        user_id="user-001",
        roles=["USER"],
    )

    result = workflow_graph.invoke(
        initial_state,
        config=config,
    )

    assert result["status"] == "COMPLETED", result.get("error")
    assert result["workflow_id"]
    assert result["human_tasks"] == []

    assert result["data"]["signal"] == "A"
    assert result["data"]["requester_id"] == "user-001"
    assert result["data"]["result_message"] == "Hello"

    assert result["final_response"] == "Hello"
    assert result["error"] is None

    snapshot = workflow_graph.get_state(config)
    assert snapshot.next == ()