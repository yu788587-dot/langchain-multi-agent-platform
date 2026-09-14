"""reviewer 测试：approved / revise 结论、修订计数、畸形输出容错。"""
from conftest import FakeLLM

from app.agents import reviewer

STATE = {
    "question": "Q",
    "steps_results": [{"step": 1, "tool": "none", "sub_answer": "子答案"}],
}


def _patch(monkeypatch, fake):
    monkeypatch.setattr(reviewer, "_default_llm", lambda: fake)


def test_approved(monkeypatch):
    fake = FakeLLM(['{"verdict": "approved", "feedback": ""}'])
    _patch(monkeypatch, fake)
    out = reviewer.reviewer_node(dict(STATE))
    assert out["review"]["verdict"] == "approved"
    assert "revision_count" not in out


def test_revise_increments_counter(monkeypatch):
    fake = FakeLLM(['{"verdict": "revise", "feedback": "请补充禁忌"}'])
    _patch(monkeypatch, fake)
    out = reviewer.reviewer_node({**STATE, "revision_count": 1})
    assert out["review"]["verdict"] == "revise"
    assert out["revision_count"] == 2
    assert out["review"]["feedback"] == "请补充禁忌"


def test_verdict_normalized_to_lowercase(monkeypatch):
    fake = FakeLLM(['{"verdict": "REVISE", "feedback": "x"}'])
    _patch(monkeypatch, fake)
    out = reviewer.reviewer_node(dict(STATE))
    assert out["review"]["verdict"] == "revise"


def test_malformed_output_defaults_approved(monkeypatch):
    fake = FakeLLM(["我看了一下，觉得还行"])  # 非 JSON
    _patch(monkeypatch, fake)
    out = reviewer.reviewer_node(dict(STATE))
    assert out["review"]["verdict"] == "approved"


def test_invalid_verdict_defaults_approved(monkeypatch):
    fake = FakeLLM(['{"verdict": "maybe", "feedback": "?"}'])
    _patch(monkeypatch, fake)
    out = reviewer.reviewer_node(dict(STATE))
    assert out["review"]["verdict"] == "approved"


def test_review_inside_code_fence(monkeypatch):
    fake = FakeLLM(['```json\n{"verdict": "revise", "feedback": "补充依据"}\n```'])
    _patch(monkeypatch, fake)
    out = reviewer.reviewer_node(dict(STATE))
    assert out["review"]["verdict"] == "revise"
