from app.workflow.spiff_engine import SpiffEngine


def test_scenario_c_admin_bypasses_approval(spiff_engine: SpiffEngine):
    # 1. 시작: signal C -> UserTask_EnterName 에서 대기 (Lane_USER)
    result = spiff_engine.start(
        signal="C",
        requester_id="admin-001",
        requester_roles=["ADMIN"]
    )

    assert result.status == "WAITING"
    assert len(result.human_tasks) == 1

    enter_name_task = result.human_tasks[0]
    assert enter_name_task.bpmn_id == "UserTask_EnterName"
    assert enter_name_task.lane == "USER"

    # 2. 이름 입력 (ADMIN은 USER Lane도 수행 가능)
    #    -> requester_roles 에 ADMIN 이 있으므로 승인 없이 바로 Task_HelloName 으로 진행
    result = spiff_engine.complete_human_task(
        workflow_id=result.workflow_id,
        task_id=enter_name_task.task_id,
        actor_roles=["ADMIN"],
        task_data={"name": "Alice"}
    )

    print(result)

    assert result.status == "COMPLETED"
    assert result.human_tasks == ()

    assert result.data["signal"] == "C"
    assert result.data["requester_id"] == "admin-001"
    assert result.data["name"] == "Alice"
    assert result.data["result_message"] == "Hello, Alice"





