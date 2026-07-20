# LangGraph 컴파일 및 StateGraph 조립 + edge 조건
from __future__ import annotations
from typing import Any, Literal
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.nodes import WorkflowNodes
from app.agents.state import AgentState
from app.workflow.spiff_engine import SpiffEngine

NextNode = Literal["handle_human_task", "build_final_response"]

def route_by_workflow_status(state: AgentState) -> NextNode:
    """SpiffWorkflow 상태에 따라 다음 LangGraph 노드를 선택한다."""
    status = state.get("status")

    if status == "WAITING":
        return "handle_human_task"
    
    if status in {"COMPLETED", "FAILED"} :
        return "build_final_response"
    
    raise RuntimeError(
        f"처리할 수 없는 워크플로 상태입니다. status:{status!r}"
    )


def build_graph(spiff_engine: SpiffEngine, *, checkpointer: BaseCheckpointSaver[Any] | None = None) -> Any:
    """SpiffEngine을 사용하는 LangGraph 실행 그래프 생성"""
    nodes = WorkflowNodes(spiff_engine)
    graph_builder = StateGraph(AgentState)

    graph_builder.add_node(
        "start_workflow",
        nodes.start_workflow
    )

    graph_builder.add_node(
        "handle_human_task",
        nodes.handle_human_task
    )

    graph_builder.add_node(
        "build_final_reponse",
        nodes.build_final_response
    )

    graph_builder.add_edge(
        START,
        "start_workflow"
    )

    graph_builder.add_conditional_edges(
        "start_workflow",
        route_by_workflow_status,
        {
            "handle_human_task": "handle_human_task",
            "build_final_response": "build_final_response"
        }
    )

    graph_builder.add_conditional_edges(
        "handle_human_task",
        route_by_workflow_status,
        {
            "handle_human_task": "handle_human_task",
            "build_final_response": "build_final_response"
        }
    )

    graph_builder.add_edge(
        "build_final_response",
        END
    )

    return graph_builder.compile(
        checkpointer=checkpointer or MemorySaver()
    )