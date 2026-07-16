from app.workflow.spiff_engine import SpiffEngine


def test_scenario_b(spiff_engine: SpiffEngine):
    result = spiff_engine.start(
        signal="B",
        requester_id="user-002",
        requester_roles=["USER"]
    )

    print(result)

    assert result.workflow_id
    assert result.status == "COMPLETED"
    assert result.human_tasks == ()

    assert result.data["signal"] == "B"
    assert result.data["requester_id"] == "user-002"

    # Task_GetCurrentTime 의 resultVariable="tool_result" 로 저장되므로
    # 해당 키가 존재하는지, 그리고 비어있지 않은지 확인
    assert "tool_result" in result.data
    assert result.data["tool_result"]