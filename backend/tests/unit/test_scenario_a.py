from app.workflow.spiff_engine import SpiffEngine

def test_scenario_a(spiff_engine: SpiffEngine):
    result = spiff_engine.start(
        signal="A",
        requester_id="user-001",
        requester_roles=["USER"]
    )

    print(result)

    assert result.workflow_id
    assert result.status == "COMPLETED"
    assert result.human_tasks == ()

    assert result.data["signal"] == "A"
    assert result.data["requester_id"] == "user-001"
    assert result.data["result_message"] == "Hello"