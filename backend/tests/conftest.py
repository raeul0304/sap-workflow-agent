from pathlib import Path

import pytest

from app.workflow.spiff_engine import SpiffEngine
from app.workflow.store import InMemoryWorkflowStore


BACKEND_DIR = Path(__file__).resolve().parents[1]

BPMN_PATH = BACKEND_DIR / "bpmn" / "workflow.bpmn"
PROCESS_ID = "signal_permission_demo"


@pytest.fixture
def workflow_store() -> InMemoryWorkflowStore:
    return InMemoryWorkflowStore()


@pytest.fixture
def spiff_engine(
    workflow_store: InMemoryWorkflowStore,
) -> SpiffEngine:
    return SpiffEngine(
        bpmn_path=BPMN_PATH,
        process_id=PROCESS_ID,
        store=workflow_store,
    )