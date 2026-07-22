import json
from pathlib import Path
from typing import Any

TASK_DEFINITIONS_PATH = (
    Path(__file__).resolve().parent / "task_definitions.json"
)

class TaskCatalog:
    def __init__(self) -> None:
        self._definitions = self._load_definitions()

    def _load_definitions():
        with TASK_DEFINITIONS_PATH.open(
            "r",
            encoding="utf-8",
        ) as file:
            definitions = json.load(file)

        catalog: dict[str, dict[str, Any]] = {}

        for definition in definitions:
            task_type = definition["taskType"]

            if task_type in catalog:
                raise ValueError(
                    f"중복된 Task 유형입니다: {task_type}"
                )

            catalog[task_type] = definition

        return catalog

    def list_all(self) -> list[dict[str, Any]]:
        return list(self._definitions.values())

    def get(self, task_type: str) -> dict[str, Any]:
        definition = self._definitions.get(task_type)

        if definition is None:
            raise KeyError(
                f"등록되지 않은 Task 유형입니다: {task_type}"
            )

        return definition


task_catalog = TaskCatalog()