"""规划者（Planner）：把用户问题拆解为 1-5 个结构化步骤（JSON 输出，含容错与重试）。"""
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agents.json_utils import brace_safe, extract_json
from app.agents.prompts import PLANNER_SYSTEM, PLANNER_USER
from app.llm import create_llm
from app.tools import tools_description

VALID_TOOLS = {"web_search", "calculator", "drug_lookup", "none"}
MAX_STEPS = 5


def _default_llm():
    return create_llm()


def fallback_plan(question: str) -> list[dict]:
    """JSON 彻底解析失败时的兜底计划：单步、不调用工具。"""
    return [{"step": 1, "tool": "none", "tool_input": "", "description": question}]


def normalize_plan(data: dict) -> list[dict]:
    """校验并规范化 LLM 产出的计划：截断到 5 步、未知工具归为 none、步骤号连续。"""
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("缺少有效的 steps 字段")
    normalized = []
    for raw in steps[:MAX_STEPS]:
        if not isinstance(raw, dict):
            continue
        tool = str(raw.get("tool") or "none").strip().lower()
        if tool not in VALID_TOOLS:
            tool = "none"
        normalized.append(
            {
                "step": len(normalized) + 1,
                "tool": tool,
                "tool_input": str(raw.get("tool_input") or ""),
                "description": str(raw.get("description") or f"第{len(normalized) + 1}步"),
            }
        )
    if not normalized:
        raise ValueError("steps 为空")
    return normalized


def plan_question(question: str, llm=None) -> list[dict]:
    llm = llm or _default_llm()
    messages = [
        SystemMessage(content=PLANNER_SYSTEM.format(tools=tools_description())),
        HumanMessage(content=PLANNER_USER.format(question=brace_safe(question))),
    ]
    for _ in range(2):  # 解析失败重试一次，仍失败则回退默认计划
        resp = llm.invoke(messages)
        data = extract_json(resp.content)
        if data is not None:
            try:
                return normalize_plan(data)
            except ValueError:
                pass
        messages = messages + [
            resp if isinstance(resp, AIMessage) else AIMessage(content=str(resp.content)),
            HumanMessage(content="你的输出不是合法 JSON 或缺少 steps 字段，请严格按要求的 JSON 格式重新输出。"),
        ]
    return fallback_plan(question)


def planner_node(state: dict) -> dict:
    plan = plan_question(state["question"])
    return {
        "plan": plan,
        "revision_count": 0,  # 工作流起点：尚未发生任何修订
        "messages": [{"role": "planner", "phase": "done", "steps": len(plan)}],
    }
