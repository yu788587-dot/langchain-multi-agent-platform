"""审核者（Reviewer）：检查步骤结果，给出 approved / revise 结论（JSON 输出，含容错）。"""
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.json_utils import brace_safe, extract_json
from app.agents.prompts import REVIEWER_SYSTEM, REVIEWER_USER
from app.llm import create_llm

_VALID_VERDICTS = {"approved", "revise"}


def _default_llm():
    return create_llm()


def format_steps_results(steps_results) -> str:
    """把步骤结果列表格式化为提示词文本（审核者/定稿共用）。"""
    lines = []
    for r in steps_results or []:
        lines.append(f"第{r.get('step')}步 [{r.get('tool')}] {r.get('sub_answer', '')}")
    return "\n".join(lines) or "（无）"


def parse_review(text: str) -> dict:
    """解析审核结论；解析失败默认 approved，避免 revise 死循环。"""
    data = extract_json(text)
    if data is not None:
        verdict = str(data.get("verdict", "")).strip().lower()
        if verdict in _VALID_VERDICTS:
            return {"verdict": verdict, "feedback": str(data.get("feedback") or "")}
    return {"verdict": "approved", "feedback": "审核输出解析失败，默认通过。"}


def review_results(question: str, steps_results, llm=None) -> dict:
    llm = llm or _default_llm()
    messages = [
        SystemMessage(content=REVIEWER_SYSTEM),
        HumanMessage(
            content=REVIEWER_USER.format(
                question=brace_safe(question),
                results=brace_safe(format_steps_results(steps_results)),
            )
        ),
    ]
    resp = llm.invoke(messages)
    return parse_review(resp.content)


def reviewer_node(state: dict) -> dict:
    review = review_results(state["question"], state.get("steps_results"))
    out = {
        "review": review,
        "messages": [{"role": "reviewer", "phase": "done", "verdict": review["verdict"]}],
    }
    if review["verdict"] == "revise":
        out["revision_count"] = state.get("revision_count", 0) + 1
    return out
