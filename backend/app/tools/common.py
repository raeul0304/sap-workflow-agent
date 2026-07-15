# 공통 python Tool

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


def get_current_time() -> dict[str, Any]:
    """현재 한국 시간을 반환"""
    location = "Asia/Seoul"
    now = datetime.now(ZoneInfo(location))
    
    return {
        "datetime": now.isoformat(),
        "date": now.date().isoformat(),
        "time": now.time().isoformat(timespec="seconds"),
        "timezone": location
    }



TOOL_REGISTRY = {
    "get_current_time": get_current_time,
}