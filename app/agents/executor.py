"""执行者（Executor）：逐步执行计划——调用工具获取观测结果，LLM 综合产出子答案。"""
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.json_utils import brace_safe
from app.agents.planner import fallback_plan
from app.agents.prompts import EXECUTOR_SYSTEM, EXECUTOR_USER
from app.llm import create_llm
from app.tools import TOOL_REGISTRY

_TOOL_OUTPUT_LIMIT = 2000


def _default_llm():
    return create_llm()


def run_tool(tool_name: str, tool_input: str) -> str:
    """按名称执行工具；未注册的工具返回空串，工具异常转为文本反馈。"""
    if tool_name == "none":
        return ""
    tool = TOOL_REGISTRY.get(tool_name)
    if tool is None:
        return ""
    try:
        return str(tool.invoke(tool_input))
    except Exception as exc:
        return f"工具执行失败：{exc}"


def _emit(event: dict) -> None:
    """推送自定义流事件（窗口2 SSE 使用；无流式上下文时静默跳过）。"""
    try:
        from langgraph.config import get_stream_writer

        writer = get_stream_writer()
        if writer:
            writer(event)
    except Exception:
        pass


def execute_step(question: str, step: dict, llm, feedback: str | None = None) -> dict:
    tool_name = str(step.get("tool") or "none")
    tool_input = step.get("tool_input") or step.get("description") or question
    tool_output = "" if tool_name == "none" else run_tool(tool_name, tool_input)
    if tool_name != "none":
        _emit(
            {
                "type": "tool",
                "step": step.get("step"),
                "tool": tool_name,
                "tool_input": tool_input,
                "tool_output": tool_output[:500],
            }
        )
    feedback_block = f"审核者修改意见（请重点回应）：{feedback}" if feedback else ""
    messages = [
        SystemMessage(content=EXECUTOR_SYSTEM),
        HumanMessage(
            content=EXECUTOR_USER.format(
                question=brace_safe(question),
                step_no=step.get("step", "?"),
                description=brace_safe(step.get("description", "")),
                tool=tool_name,
                tool_input=brace_safe(tool_input),
                tool_output=brace_safe(tool_output or "（无）"),
                feedback_block=feedback_block,
            )
        ),
    ]
    resp = llm.invoke(messages)
    return {
        "step": step.get("step"),
        "tool": tool_name,
        "tool_input": tool_input,
        "tool_output": tool_output[:_TOOL_OUTPUT_LIMIT],
        "sub_answer": str(resp.content).strip(),
    }


def executor_node(state: dict) -> dict:
    question = state["question"]
    plan = state.get("plan") or fallback_plan(question)
    review = state.get("review") or {}
    feedback = review.get("feedback") if review.get("verdict") == "revise" else None
    llm = _default_llm()
    results = []
    for step in plan:
        result = execute_step(question, step, llm, feedback)
        results.append(result)
        _emit(
            {
                "type": "step_done",
                "step": result["step"],
                "tool": result["tool"],
                "tool_input": result["tool_input"],
                "sub_answer": result["sub_answer"],
            }
        )
    return {
        "steps_results": results,
        "messages": [{"role": "executor", "phase": "done", "steps": len(results), "revising_for": feedback}],
    }
