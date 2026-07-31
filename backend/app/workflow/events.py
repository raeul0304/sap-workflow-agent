import asyncio
from typing import Any
from collections import defaultdict
from threading import RLock
import json
from datetime import datetime
from zoneinfo import ZoneInfo

class WorkflowEventManager:
    """워크플로 실행 상태를 SSE로 브로드캐스트 하기 위한 이벤트 큐 매니저"""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._history: dict[str, list[str]] = defaultdict(list)
        self._event_sequences: dict[str, int] = defaultdict(int)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = RLock()

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop


    def subscribe(
        self,
        workflow_id: str,
        last_event_id: int | None = None,
    ) -> asyncio.Queue[str]:
        """특정 워크플로 이벤트 구독 및 기존 이력 재전송."""

        queue: asyncio.Queue[str] = asyncio.Queue()

        with self._lock:
            self._subscribers.setdefault(workflow_id, set()).add(queue)
            history = list(self._history.get(workflow_id, []))

        print(f"[SSE] 클라이언트 구독 시작 - workflow_id : {workflow_id}")
        print(f"[SSE] history 누적 이벤트 수 : {len(history)}개")

        for message in history:
            event = json.loads(message)

            print(f"[SSE] history: event_id: {event.get('event_id')}, type: {event.get('event_type')}")

            if (
                last_event_id is not None
                and event.get("event_id", 0) <= last_event_id
            ):
                continue

            queue.put_nowait(message)

        return queue


    def unsubscribe(
        self,
        workflow_id: str,
        queue: asyncio.Queue[str],
    ) -> None:
        """현재 SSE 연결에 해당하는 Queue만 제거."""

        with self._lock:
            subscribers = self._subscribers.get(workflow_id)

            if subscribers is None:
                return

            subscribers.discard(queue)

            if not subscribers:
                self._subscribers.pop(workflow_id, None)

    def publish_sync(
        self,
        workflow_id: str,
        event_data: dict[str, Any],
    ) -> dict[str, Any]:
        """동기 SpiffEngine 스레드에서 이벤트를 안전하게 발행."""

        loop = self._loop

        if loop is None:
            raise RuntimeError(
                "WorkflowEventManager의 이벤트 루프가 설정되지 않았습니다."
            )

        with self._lock:
            self._event_sequences[workflow_id] += 1

            event = {
                "event_id": self._event_sequences[workflow_id],
                "workflow_id": workflow_id,
                "occurred_at": datetime.now(
                    ZoneInfo("Asia/Seoul")
                ).isoformat(),
                **event_data,
            }

            message = json.dumps(
                event,
                ensure_ascii=False,
                default=str,
            )

            self._history[workflow_id].append(message)
            subscribers = list(self._subscribers.get(workflow_id, set()))

        for queue in subscribers:
            loop.call_soon_threadsafe(queue.put_nowait, message)

        return event

    def clear(self, workflow_id: str) -> None:
        """워크플로 삭제 시 이벤트 이력도 제거."""

        with self._lock:
            self._history.pop(workflow_id, None)
            self._event_sequences.pop(workflow_id, None)


event_manager = WorkflowEventManager()