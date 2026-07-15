import uuid
from threading import Lock
from SpiffWorkflow.bpmn.workflow import BpmnWorkflow


class WorkflowNotFoundError(KeyError):
    """존재하지 않는 workflow_id로 조회했을 때 발생."""

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        super().__init__(f"워크플로 인스턴스를 찾을 수 없습니다: {workflow_id}")


class InMemoryWorkflowStore:
    """
    프로세스 메모리 내에서 BpmnWorkflow 인스턴스를 관리하는 저장소.
    """

    def __init__(self) -> None:
        self._workflows: dict[str, BpmnWorkflow] = {}
        self._lock = Lock()



    def create(self, workflow: BpmnWorkflow, workflow_id: str | None = None) -> str:
        """
        새 워크플로 인스턴스를 저장하고 workflow_id를 반환한다.
        workflow_id를 지정하지 않으면 uuid4로 자동 생성한다.
        """
        workflow_id = workflow_id or str(uuid.uuid4())

        with self._lock:
            if workflow_id in self._workflows:
                raise ValueError(f"이미 존재하는 workflow_id입니다: {workflow_id}")
            self._workflows[workflow_id] = workflow

        return workflow_id



    def get(self, workflow_id: str) -> BpmnWorkflow:
        """workflow_id에 해당하는 BpmnWorkflow 인스턴스를 반환한다."""
        with self._lock:
            workflow = self._workflows.get(workflow_id)

        if workflow is None:
            raise WorkflowNotFoundError(workflow_id)

        return workflow



    def save(self, workflow_id: str, workflow: BpmnWorkflow) -> None:
        """
        기존 workflow_id의 인스턴스를 명시적으로 갱신한다.
        """
        with self._lock:
            if workflow_id not in self._workflows:
                raise WorkflowNotFoundError(workflow_id)
            self._workflows[workflow_id] = workflow



    def delete(self, workflow_id: str) -> None:
        """워크플로 인스턴스를 저장소에서 제거한다 (예: 워크플로 완료/취소 시)."""
        with self._lock:
            if workflow_id not in self._workflows:
                raise WorkflowNotFoundError(workflow_id)
            del self._workflows[workflow_id]



    def exists(self, workflow_id: str) -> bool:
        with self._lock:
            return workflow_id in self._workflows


# 애플리케이션 전역에서 공유할 단일 인스턴스.
# spiff_engine.py 등에서 이 객체를 그대로 import해서 사용한다.
workflow_store = InMemoryWorkflowStore()