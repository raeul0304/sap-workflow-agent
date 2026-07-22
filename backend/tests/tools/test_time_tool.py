from app.tools.common import TOOL_REGISTRY


def test_get_current_time():
    tool = TOOL_REGISTRY["get_current_time"]

    result = tool()
    print(result)

    assert result["timezone"] == "Asia/Seoul"
    assert "datetime" in result
    assert "date" in result
    assert "time" in result