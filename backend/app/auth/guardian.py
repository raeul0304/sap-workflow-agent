# User 역할과 BPMN Lane 일치 여부 검증 (Lane-Role 매핑 + 검증 로직을 모두 여기로 흡수)

from collections.abc import Iterable
from SpiffWorkflow.task import Task
from app.workflow.lanes import TaskLaneInfo, get_task_lane_info


LANE_ROLE_MAP: dict[str, frozenset[str]] = {
    "USER": frozenset({"USER", "ADMIN"}),
    "ADMIN": frozenset({"ADMIN"}),
}


class TaskPermissionError(PermissionError):
    """사용자가 BPMN Task를 수행할 권한이 없을 때 발생하는 예외."""

    def __init__(
        self,
        task_info: TaskLaneInfo,
        actor_roles: frozenset[str],
    ) -> None:
        self.task_info = task_info
        self.actor_roles = actor_roles

        super().__init__(
            f"Task 수행 권한이 없습니다. "
            f"task={task_info.bpmn_id}, "
            f"lane={task_info.lane}, "
            f"actor_roles={sorted(actor_roles)}"
        )


def normalize_roles(actor_roles: Iterable[str]) -> frozenset[str]:
    """사용자 역할을 비교 가능한 대문자 집합으로 정규화한다."""
    return frozenset(
        role.strip().upper()
        for role in actor_roles
        if role and role.strip()
    )


def get_allowed_roles(lane: str | None) -> frozenset[str]:
    """BPMN Lane을 수행할 수 있는 역할 목록을 반환한다."""
    if lane is None:
        return frozenset()

    return LANE_ROLE_MAP.get(lane.upper(), frozenset())


def can_access_task(
    task: Task,
    actor_roles: Iterable[str],
) -> bool:
    """사용자가 Task를 수행할 권한이 있는지 확인한다."""
    task_info = get_task_lane_info(task)
    if task_info.lane is None:
        return False

    lane = task_info.lane.upper()

    if lane == "SYSTEM":   # SYSTEM Lane은 SpiffWorkflow 엔진이 자동으로 수행
        return False

    normalized_roles = normalize_roles(actor_roles)
    allowed_roles = get_allowed_roles(lane)

    return bool(normalized_roles.intersection(allowed_roles))


def ensure_task_access(
    task: Task,
    actor_roles: Iterable[str],
) -> TaskLaneInfo:
    """
    사용자의 Task 수행 권한을 검증한다. 권한이 있으면 Task 정보를 반환하고, 권한이 없으면 TaskPermissionError를 발생시킨다.
    """
    task_info = get_task_lane_info(task)
    normalized_roles = normalize_roles(actor_roles)

    if not can_access_task(task, normalized_roles):
        raise TaskPermissionError(
            task_info=task_info,
            actor_roles=normalized_roles,
        )

    return task_info