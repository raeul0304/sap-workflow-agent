#SpiffWorkflow Data 및 Lane 매핑 정의 ( Spiff Task 객체에서 BPMN Lane 이름만 추출 (역할/권한 판단은 하지 않음)

from dataclasses import dataclass
from typing import Any
from SpiffWorkflow.task import Task

@dataclass(frozen=True, slots=True)
class TaskLaneInfo:
    """SpiffWorkflow Task에서 추출한 BPMN 및 Lane 정보"""
    task_id: str
    bpmn_id : str | None
    task_name: str
    lane: str | None


def get_task_lane(task: Task) -> str | None:
    """SpiffWorkflow Task가 속한 BPMN Lane 이름을 반환한다."""
    return task.task_spec.lane


def get_task_lane_info(task: Task) -> TaskLaneInfo:
    """SpiffWorkflow Task에서 BPMN 및 Lane 정보를 추출한다."""
    task_spec = task.task_spec

    return TaskLaneInfo(
        task_id = str(task.id),
        bpmn_id = task_spec.bpmn_id,
        task_name = task_spec.bpmn_name or task_spec.name,
        lane = task_spec.lane
    )