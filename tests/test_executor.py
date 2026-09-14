"""executor 测试：逐步执行（mock 工具）、工具失败容错、修订反馈注入提示词。"""
from conftest import FakeLLM

from app.agents import executor


PLAN = [
    {"step": 1, "tool": "web_search", "tool_input": "布洛芬联用", "description": "检索联用资料"},
    {"step": 2, "tool": "none", "tool_input": "", "description": "综合建议"},
]


def _patch(monkeypatch, fake, run_tool=None):
    monkeypatch.setattr(executor, "_default_llm", lambda: fake)
    if run_tool is not None:
        monkeypatch.setattr(executor, "run_tool", run_tool)


def test_executes_all_steps_in_order(monkeypatch):
    fake = FakeLLM(["子答案一", "子答案二"])
    _patch(
        monkeypatch,
        fake,
        run_tool=lambda name, q: f"观测-{q}" if name == "web_search" else "",
    )
    out = executor.executor_node({"question": "Q", "plan": PLAN})
    results = out["steps_results"]
    assert len(results) == 2
    assert results[0]["tool"] == "web_search"
    assert results[0]["tool_output"] == "观测-布洛芬联用"
    assert results[0]["sub_answer"] == "子答案一"
    assert results[1]["tool_output"] == ""
    assert results[1]["sub_answer"] == "子答案二"


def test_tool_failure_keeps_flow(monkeypatch):
    fake = FakeLLM(["已说明工具失败"])
    _patch(monkeypatch, fake, run_tool=lambda name, q: "工具执行失败：boom")
    out = executor.executor_node({"question": "Q", "plan": PLAN[:1]})
    assert out["steps_results"][0]["tool_output"].startswith("工具执行失败")
    assert out["steps_results"][0]["sub_answer"] == "已说明工具失败"


def test_revision_feedback_in_prompt(monkeypatch):
    fake = FakeLLM(["修改后的子答案"])
    _patch(monkeypatch, fake, run_tool=lambda name, q: "观测")
    state = {
        "question": "Q",
        "plan": PLAN[:1],
        "review": {"verdict": "revise", "feedback": "请补充用药禁忌"},
    }
    executor.executor_node(state)
    prompt_text = "".join(str(m.content) for m in fake.calls[0])
    assert "请补充用药禁忌" in prompt_text


def test_no_feedback_when_approved(monkeypatch):
    fake = FakeLLM(["子答案"])
    _patch(monkeypatch, fake, run_tool=lambda name, q: "观测")
    state = {
        "question": "Q",
        "plan": PLAN[:1],
        "review": {"verdict": "approved", "feedback": ""},
    }
    executor.executor_node(state)
    prompt_text = "".join(str(m.content) for m in fake.calls[0])
    assert "审核者修改意见" not in prompt_text


def test_missing_plan_uses_fallback(monkeypatch):
    fake = FakeLLM(["直接回答"])
    _patch(monkeypatch, fake, run_tool=lambda name, q: "")
    out = executor.executor_node({"question": "维生素C每天吃多少合适？"})
    assert len(out["steps_results"]) == 1
    assert out["steps_results"][0]["tool"] == "none"


def test_run_tool_registry_integration():
    # 真实注册表：calculator 可直接算出结果；未注册工具返回空串
    assert executor.run_tool("calculator", "1+2") == "3"
    assert executor.run_tool("nonexistent", "x") == ""
    assert executor.run_tool("none", "x") == ""
