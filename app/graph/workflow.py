"""工作流编排：START → Planner → Executor → Reviewer →（approved 或超限）→ Finalize → END。

revise 时带反馈回到 Executor，最多 MAX_REVISIONS 次修订，超限强制定稿，防死循环。
"""
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.executor import executor_node
from app.agents.finalize import finalize_node
from app.agents.planner import planner_node
from app.agents.reviewer import reviewer_node
from app.config import get_settings
from app.graph.state import AgentState


def route_after_review(state: dict) -> str:
    """审核后的条件路由：approved → 定稿；revise 且修订次数未超上限（≤MAX_REVISIONS）→ 回到执行者；
    超过上限 → 强制定稿，防死循环。"""
    review = state.get("review") or {}
    if review.get("verdict") != "revise":
        return "finalize"
    if state.get("revision_count", 0) <= get_settings().max_revisions:
        return "executor"
    return "finalize"


def build_workflow(checkpointer=None):
    graph = StateGraph(AgentState)
    graph.add_node("planner", planner_node)
    graph.add_node("executor", executor_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_node("finalize", finalize_node)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "executor")
    graph.add_edge("executor", "reviewer")
    graph.add_conditional_edges(
        "reviewer", route_after_review, {"executor": "executor", "finalize": "finalize"}
    )
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer)


def build_default_graph():
    """带内存检查点的默认图：支持 thread_id 会话隔离。"""
    return build_workflow(checkpointer=MemorySaver())
