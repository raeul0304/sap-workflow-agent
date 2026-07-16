import pytest
from app.workflow.spiff_engine import SpiffEngine
from app.auth.guardian import TaskPermissionError


def test_scenario_c_user_requires_approval(spiff_engine: SpiffEngine):
    # 1. 시작: signal C -> UserTask_EnterName 에서 대기
    result = spiff_engine.start(
        signal="C",
        requester_id="user-003",
        requester_roles=["USER"]
    )

    assert result.status == "WAITING"
    enter_name_task = result.human_tasks[0]
    assert enter_name_task.bpmn_id == "UserTask_EnterName"
    assert enter_name_task.lane == "USER"

    # 2. 이름 입력 -> requester가 USER이므로 UserTask_ApproveName 에서 대기 (Lane_ADMIN)
    result = spiff_engine.complete_human_task(
        workflow_id=result.workflow_id,
        task_id=enter_name_task.task_id,
        actor_roles=["USER"],
        task_data={"name": "Bob"}
    )

    assert result.status == "WAITING"
    assert len(result.human_tasks) == 1

    approve_task = result.human_tasks[0]
    assert approve_task.bpmn_id == "UserTask_ApproveName"
    assert approve_task.lane == "ADMIN"

    # 3. 관리자가 승인 -> Task_HelloName 실행 후 종료
    result = spiff_engine.complete_human_task(
        workflow_id=result.workflow_id,
        task_id=approve_task.task_id,
        actor_roles=["ADMIN"],
        task_data={"approval_decision": "APPROVE"}
    )

    print(result)

    assert result.status == "COMPLETED"
    assert result.human_tasks == ()

    assert result.data["signal"] == "C"
    assert result.data["requester_id"] == "user-003"
    assert result.data["name"] == "Bob"
    assert result.data["result_message"] == "Hello, Bob"


def test_scenario_c_user_rejected_then_resubmit(spiff_engine: SpiffEngine):
    # 1. 시작 -> 이름 입력
    result = spiff_engine.start(
        signal="C",
        requester_id="user-004",
        requester_roles=["USER"]
    )
    enter_name_task = result.human_tasks[0]

    # 2. 이름 입력 -> 승인 대기
    result = spiff_engine.complete_human_task(
        workflow_id=result.workflow_id,
        task_id=enter_name_task.task_id,
        actor_roles=["USER"],
        task_data={"name": "Carol"}
    )
    approve_task = result.human_tasks[0]
    assert approve_task.bpmn_id == "UserTask_ApproveName"

    # 3. 관리자가 반려 -> UserTask_EnterName 으로 다시 돌아감
    result = spiff_engine.complete_human_task(
        workflow_id=result.workflow_id,
        task_id=approve_task.task_id,
        actor_roles=["ADMIN"],
        task_data={"approval_decision": "REJECT"}
    )

    assert result.status == "WAITING"
    resubmit_task = result.human_tasks[0]
    assert resubmit_task.bpmn_id == "UserTask_EnterName"

    # 4. 이름을 다시 입력하여 재제출 -> 다시 승인 대기
    result = spiff_engine.complete_human_task(
        workflow_id=result.workflow_id,
        task_id=resubmit_task.task_id,
        actor_roles=["USER"],
        task_data={"name": "Carol Updated"}
    )

    assert result.status == "WAITING"
    reapprove_task = result.human_tasks[0]
    assert reapprove_task.bpmn_id == "UserTask_ApproveName"

    # 5. 이번에는 승인 -> 종료
    result = spiff_engine.complete_human_task(
        workflow_id=result.workflow_id,
        task_id=reapprove_task.task_id,
        actor_roles=["ADMIN"],
        task_data={"approval_decision": "APPROVE"}
    )

    print(result)

    assert result.status == "COMPLETED"
    assert result.data["name"] == "Carol Updated"
    assert result.data["result_message"] == "Hello, Carol Updated"


def test_scenario_c_user_cannot_approve(spiff_engine: SpiffEngine):
    """USER 역할은 ADMIN Lane(UserTask_ApproveName)을 수행할 권한이 없어야 한다."""
    result = spiff_engine.start(
        signal="C",
        requester_id="user-005",
        requester_roles=["USER"]
    )
    enter_name_task = result.human_tasks[0]

    result = spiff_engine.complete_human_task(
        workflow_id=result.workflow_id,
        task_id=enter_name_task.task_id,
        actor_roles=["USER"],
        task_data={"name": "Dave"}
    )
    approve_task = result.human_tasks[0]
    assert approve_task.bpmn_id == "UserTask_ApproveName"

    # USER 는 ADMIN Lane 을 수행할 수 없으므로 TaskPermissionError 발생해야 함
    with pytest.raises(TaskPermissionError):
        spiff_engine.complete_human_task(
            workflow_id=result.workflow_id,
            task_id=approve_task.task_id,
            actor_roles=["USER"],
            task_data={"approval_decision": "APPROVE"}
        )