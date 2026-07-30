import asyncio
from typing import Any
import json

class WorkflowEventManager:
    """워크플로 실행 상태를 SSE로 브로드캐스트 하기 위한 이벤트 큐 매니저"""

    def __init__(self) -> None:
        self.subscribers: dict[str, asyncio.Queue] = {}

    def subscribe(self, workflow_id: str) -> asyncio.Queue:
        """클라이언트가 특정 워크플로의 이벤트를 구독"""
        queue = asyncio.Queue()
        self.subscriber[workflow_id] = queue
        return queue

    def unsubscribe(self, workflow_id: str)-> None:
        """구독 해제"""
        if workflow_id in self.subscribers:
            del self.subscribers[workflow_id]

    def publish_sync(self, workflow_id: str, event_data: dict[str, Any]) -> None:
        """SpiffEngine에서 이벤트를 비동기 큐에 발행"""
        if workflow_id in self.subscribers:
            queue = self.subscribers[workflow_id]

            try: #현재 동작 중인 비동기 이벤트 루프를 가져와 큐에 데이터를 밀어넣음
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(queue.put_nowait, json.dumps(event_data))
            except RuntimeError:
                pass


event_manager = WorkflowEventManager()