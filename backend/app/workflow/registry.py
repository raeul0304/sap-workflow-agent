# 워크플로 유형별 SpiffEngine Registry
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.workflow.spiff_engine import SpiffEngine


class WorkflowNotRegisteredError(LookupError):
    """등록되지 않은 workflow_type을 요청했을 때 핸들링"""

    def __init__(self, workflow_type: str) -> None:
        self.workflow_type = workflow_type

        super().__init__(
            f"등록되지 않은 workflow_type입니다: {workflow_type}"
        )


class WorkflowRegistry:
    """workflow_type애 따른 SpiffEngine을 연결"""
    
    def __init__(self) -> None:
        self._engines: dict[str, SpiffEngine] = {}

    def register(self, workflow_type: str, engine: SpiffEngine, force: bool = False) :
        """워크플로 우형과 실행 엔진을 등록 (force 옵션: True일 경우 기존 등록된 엔진을 덮어씀. Admin 프로세스 업데이트 가능)"""
        
        workflow_type = workflow_type.strip()
        if not workflow_type:
            raise ValueError("workflow_type은 비어있을 수 없습니다.")
        
        if workflow_type in self._engines:
            raise ValueError(f"이미 등록된 workflow_type입니다: {workflow_type}")
        
        self._engines[workflow_type] = engine
        print(f"[Registry] '{workflow_type}' 워크플로가 배포(등록) 되었습니다.")
    

    def get(self, workflow_type: str) -> SpiffEngine:
        """워크플로 유형에 해당하는 엔진을 반환"""

        try:
            return self._engines[workflow_type]
        except KeyError as exc:
            raise WorkflowNotRegisteredError(
                workflow_type
            ) from exc