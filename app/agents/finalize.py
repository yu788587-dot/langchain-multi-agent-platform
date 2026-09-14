"""定稿（Finalize）：综合所有步骤结果生成最终答案，并附医疗免责声明。"""
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.json_utils import brace_safe
from app.agents.prompts import FINALIZE_SYSTEM, FINALIZE_USER, MEDICAL_DISCLAIMER
from app.agents.reviewer import format_steps_results
from app.llm import create_llm


def _default_llm():
    return create_llm()


def finalize_node(state: dict) -> dict:
    llm = _default_llm()
    messages = [
        SystemMessage(content=FINALIZE_SYSTEM),
        HumanMessage(
            content=FINALIZE_USER.format(
                question=brace_safe(state["question"]),
                results=brace_safe(format_steps_results(state.get("steps_results"))),
            )
        ),
    ]
    resp = llm.invoke(messages)
    answer = str(resp.content).strip() + MEDICAL_DISCLAIMER
    return {
        "final_answer": answer,
        "messages": [{"role": "finalizer", "phase": "done"}],
    }
