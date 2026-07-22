# database.bpmn 실행 통합 테스트
# SpiffEngine이 BPMN을 실행하면서 ServiceTask → read_dataset 툴 호출까지 연결되는지 검증

import pytest
from pathlib import Path

from app.workflow.spiff_engine import SpiffEngine
from app.workflow.store import InMemoryWorkflowStore


BACKEND_DIR = Path(__file__).resolve().parents[2]

BPMN_PATH = BACKEND_DIR / "bpmn" / "database.bpmn"
PROCESS_ID = "Process_1"


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


def test_database_bpmn_completes(spiff_engine):
    """워크플로가 끝까지 실행되어 COMPLETED 상태가 되는지 확인"""
    result = spiff_engine.start(
        requester_id="test_user",
        requester_roles=["USER"],
    )
    print(result)

    assert result.status == "COMPLETED"


def test_database_bpmn_sap_result_exists(spiff_engine):
    """read_dataset 툴 호출 결과가 sap_result로 workflow data에 담기는지 확인"""
    result = spiff_engine.start(
        requester_id="test_user",
        requester_roles=["USER"],
    )

    assert "sap_result" in result.data


def test_database_bpmn_sap_result_is_list(spiff_engine):
    """sap_result가 리스트 형태인지 확인 (read_dataset 반환 타입)"""

    result = spiff_engine.start(
        requester_id="test_user",
        requester_roles=["USER"],
    )

    # ToolServiceEnvironment.call_service()가 json.dumps로 직렬화해서 반환하므로 역직렬화
    sap_result = result.data["sap_result"]
    print(sap_result)

    assert isinstance(sap_result, list)
    assert len(sap_result) > 0