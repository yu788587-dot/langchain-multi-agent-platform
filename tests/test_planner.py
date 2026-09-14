"""planner 测试：JSON 解析（含代码围栏）、容错重试、回退默认计划。"""
import json

from conftest import FakeLLM

from app.agents import planner

VALID = json.dumps(
    {
        "steps": [
            {"step": 1, "tool": "web_search", "tool_input": "布洛芬 对乙酰氨基酚 联用", "description": "检索两药联用资料"},
            {"step": 2, "tool": "none", "tool_input": "", "description": "综合给出建议"},
        ]
    },
    ensure_ascii=False,
)


def _patch(monkeypatch, fake):
    monkeypatch.setattr(planner, "_default_llm", lambda: fake)


def test_valid_plan(monkeypatch):
    fake = FakeLLM([VALID])
    _patch(monkeypatch, fake)
    plan = planner.plan_question("布洛芬和对乙酰氨基酚能一起吃吗？")
    assert len(plan) == 2
    assert plan[0]["tool"] == "web_search"
    assert plan[0]["step"] == 1
    assert plan[1]["step"] == 2
    assert plan[1]["tool"] == "none"


def test_plan_inside_code_fence(monkeypatch):
    fake = FakeLLM(["```json\n" + VALID + "\n```"])
    _patch(monkeypatch, fake)
    plan = planner.plan_question("问题")
    assert len(plan) == 2


def test_json_with_surrounding_text(monkeypatch):
    fake = FakeLLM(["好的，规划如下：\n" + VALID + "\n以上。"])
    _patch(monkeypatch, fake)
    plan = planner.plan_question("问题")
    assert len(plan) == 2


def test_malformed_output_retries_then_falls_back(monkeypatch):
    fake = FakeLLM(["这不是JSON", "还是不是JSON"])
    _patch(monkeypatch, fake)
    question = "维生素C每天吃多少？"
    plan = planner.plan_question(question)
    assert plan == planner.fallback_plan(question)
    assert len(fake.calls) == 2  # 重试了一次


def test_invalid_json_object_retries(monkeypatch):
    fake = FakeLLM(['{"steps": [1, 2, 3]}', VALID])
    _patch(monkeypatch, fake)
    plan = planner.plan_question("问题")
    assert len(plan) == 2


def test_more_than_five_steps_clamped(monkeypatch):
    steps = [{"step": i, "tool": "unknown_tool", "description": f"s{i}"} for i in range(1, 7)]
    fake = FakeLLM([json.dumps({"steps": steps}, ensure_ascii=False)])
    _patch(monkeypatch, fake)
    plan = planner.plan_question("问题")
    assert len(plan) == planner.MAX_STEPS
    assert all(s["tool"] == "none" for s in plan)  # 未知工具归为 none
    assert [s["step"] for s in plan] == [1, 2, 3, 4, 5]  # 步骤号连续


def test_planner_node_returns_state_patch(monkeypatch):
    fake = FakeLLM([VALID])
    _patch(monkeypatch, fake)
    out = planner.planner_node({"question": "Q"})
    assert len(out["plan"]) == 2
    assert out["messages"][0]["role"] == "planner"
