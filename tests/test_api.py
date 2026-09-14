"""API 测试：SSE 事件序列、422 校验、响应头、自定义事件映射与错误降级。

全部 mock（替身图 / 假节点），不打真实 LLM API。两种策略：
- 策略A：monkeypatch 假节点后构建真实工作流图，验证节点增量 → SSE 主事件序列；
- 策略B：注入桩图（按脚本吐 (mode, data) 块），精确验证 custom 事件映射等分支。
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.api import main as api_main
from app.graph import workflow as wf_mod


# ============ 公共设施 ============

@pytest.fixture(autouse=True)
def _reset_graph():
    """每个测试结束后重置注入的图，避免串扰。"""
    yield
    api_main.set_graph(None)


def parse_sse(text: str) -> list[tuple[str, dict]]:
    """把 SSE 文本解析为 (event, data) 有序列表。"""
    events = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        event, data_lines = "message", []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
        events.append((event, json.loads("\n".join(data_lines)) if data_lines else {}))
    return events


def events_of(events, name):
    """过滤出指定事件名的 data 列表。"""
    return [data for evt, data in events if evt == name]


def agent_phases(events, role):
    """某角色按序出现的 phase 列表。"""
    return [
        d.get("phase") for evt, d in events
        if evt == "agent" and d.get("role") == role
    ]


class StubGraph:
    """桩图：按脚本吐 (mode, data) 块，并记录调用参数。"""

    def __init__(self, chunks, error_after=None):
        self._chunks = chunks
        self._error_after = error_after  # 吐完前 N 块后抛异常
        self.calls = []

    def stream(self, state, config=None, stream_mode=None):
        self.calls.append({"state": state, "config": config, "stream_mode": stream_mode})
        for i, chunk in enumerate(self._chunks):
            if self._error_after is not None and i == self._error_after:
                raise RuntimeError("桩图故意抛错")
            yield chunk
        if self._error_after is not None:  # 脚本吐完后再抛（覆盖 error_after == len(chunks) 的情形）
            raise RuntimeError("桩图故意抛错")


def make_client_with_stub(chunks, error_after=None) -> tuple[TestClient, StubGraph]:
    stub = StubGraph(chunks, error_after)
    api_main.set_graph(stub)
    return TestClient(api_main.app), stub


# ============ 策略A：真实图 + 假节点 ============

def _plan_state(steps):
    return {"plan": steps, "revision_count": 0, "messages": []}


def _exec_state(results):
    return {"steps_results": results, "messages": []}


def _review_state(verdict, feedback=""):
    out = {"review": {"verdict": verdict, "feedback": feedback}, "messages": []}
    return out


TWO_STEP_PLAN = [
    {"step": 1, "tool": "drug_lookup", "tool_input": "布洛芬", "description": "查询布洛芬信息"},
    {"step": 2, "tool": "web_search", "tool_input": "联用建议", "description": "搜索联用建议"},
]


def _patch_pipeline(monkeypatch, review_states):
    """打桩四个节点：2 步计划、固定执行结果、按序返回审核结论。"""
    monkeypatch.setattr(wf_mod, "planner_node", lambda s: _plan_state(TWO_STEP_PLAN))
    monkeypatch.setattr(
        wf_mod, "executor_node",
        lambda s: _exec_state([
            {"step": 1, "tool": "drug_lookup", "tool_input": "布洛芬",
             "tool_output": "药" * 3000, "sub_answer": "子答案一"},  # 3000 字符触发 500 截断
            {"step": 2, "tool": "web_search", "tool_input": "联用建议",
             "tool_output": "搜", "sub_answer": "子答案二"},
        ]),
    )
    verdicts = iter(review_states)

    def reviewer(s):
        return _review_state(next(verdicts), "意见")

    monkeypatch.setattr(wf_mod, "reviewer_node", reviewer)
    monkeypatch.setattr(
        wf_mod, "finalize_node",
        lambda s: {"final_answer": "这是最终答案", "messages": []},
    )


def test_missing_question_returns_422():
    client, _ = make_client_with_stub([])
    assert client.post("/api/chat", json={}).status_code == 422
    assert client.post("/api/chat", json={"question": "   "}).status_code == 422
    ok = client.post("/api/chat", json={"question": " 合法问题 "})
    assert ok.status_code == 200  # 前后空白被剥离后放行


def test_sse_headers():
    client, _ = make_client_with_stub([])
    resp = client.post("/api/chat", json={"question": "Q"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers["cache-control"] == "no-cache"
    assert resp.headers["x-accel-buffering"] == "no"


def test_sse_happy_path_sequence(monkeypatch):
    _patch_pipeline(monkeypatch, ["approved"])
    api_main.set_graph(wf_mod.build_workflow())
    client = TestClient(api_main.app)
    resp = client.post("/api/chat", json={"question": "测试问题"})

    events = parse_sse(resp.text)
    names = [e for e, _ in events]

    # 主事件序列：agent 开场 → plan → step×2 → review → final
    assert names[0] == "agent"
    assert names.count("plan") == 1
    assert names.count("review") == 1
    assert names.count("final") == 1
    assert "error" not in names

    # plan 事件包含两步且字段齐全
    plan = events_of(events, "plan")[0]
    assert [s["step"] for s in plan["steps"]] == [1, 2]
    assert plan["steps"][0]["tool"] == "drug_lookup"
    assert plan["steps"][1]["description"] == "搜索联用建议"

    # agent 角色 phase 序列符合工作流拓扑
    assert agent_phases(events, "planner") == ["start", "done"]
    assert agent_phases(events, "executor") == ["start", "done"]
    assert agent_phases(events, "reviewer") == ["start", "done"]
    assert agent_phases(events, "finalizer") == ["start", "done"]

    # step 事件：executor 未发 custom 事件时由 updates 兜底补发
    steps = events_of(events, "step")
    assert [s["step"] for s in steps] == [1, 2]
    assert steps[0]["sub_answer"] == "子答案一"
    assert len(steps[0]["tool_output"]) == 500  # 3000 字符被截断到 500
    assert steps[1]["tool_output"] == "搜"

    # final 事件：答案、耗时、修订次数
    final = events_of(events, "final")[0]
    assert final["answer"] == "这是最终答案"
    assert isinstance(final["elapsed_ms"], int)
    assert final["revisions"] == 0


def test_sse_revise_round_repeats_steps(monkeypatch):
    _patch_pipeline(monkeypatch, ["revise", "approved"])
    api_main.set_graph(wf_mod.build_workflow())
    client = TestClient(api_main.app)
    resp = client.post("/api/chat", json={"question": "测试问题"})

    events = parse_sse(resp.text)
    assert agent_phases(events, "executor") == ["start", "done", "start", "done"]

    # revise 结论 + 第二轮步骤重发
    reviews = events_of(events, "review")
    assert [r["verdict"] for r in reviews] == ["revise", "approved"]
    steps = events_of(events, "step")
    assert [(s["round"], s["step"]) for s in steps] == [(0, 1), (0, 2), (1, 1), (1, 2)]

    final = events_of(events, "final")[0]
    assert final["revisions"] == 1  # 执行者重跑了 1 次


# ============ 策略B：桩图，验证 custom 事件与错误分支 ============

def test_custom_tool_event_streams_progressively():
    chunks = [
        ("updates", {"planner": {"plan": TWO_STEP_PLAN, "revision_count": 0, "messages": []}}),
        ("custom", {"type": "tool", "step": 1, "tool": "web_search",
                    "tool_input": "查询词", "tool_output": "x" * 1500}),
        ("custom", {"type": "step_done", "step": 1, "tool": "web_search",
                    "tool_input": "查询词", "sub_answer": "子答案一"}),
        ("updates", {"executor": {"steps_results": [
            {"step": 1, "tool": "web_search", "tool_input": "查询词",
             "tool_output": "x" * 3000, "sub_answer": "子答案一"},
        ], "messages": []}}),
        ("updates", {"reviewer": _review_state("approved")}),
        ("updates", {"finalize": {"final_answer": "答案", "messages": []}}),
    ]
    client, stub = make_client_with_stub(chunks)
    resp = client.post("/api/chat", json={"question": "Q", "thread_id": "t-1"})

    steps = events_of(parse_sse(resp.text), "step")
    # tool 事件先到（子答案未就绪），step_done 合入工具输出，executor 增量去重不重发
    assert len(steps) == 2
    assert steps[0]["sub_answer"] is None
    assert steps[0]["round"] == 0
    assert steps[1]["sub_answer"] == "子答案一"
    assert len(steps[1]["tool_output"]) == 500

    # thread_id 与流模式正确透传给图
    call = stub.calls[0]
    assert call["state"] == {"question": "Q"}
    assert call["config"] == {"configurable": {"thread_id": "t-1"}}
    assert call["stream_mode"] == ["updates", "custom"]


def test_no_thread_id_generates_isolated_session():
    """未传 thread_id 时也应带随机 thread_id（检查点器必需），保证请求间会话隔离。"""
    client, stub = make_client_with_stub([])
    client.post("/api/chat", json={"question": "Q"})
    config = stub.calls[0]["config"]
    assert config["configurable"]["thread_id"]
    client.post("/api/chat", json={"question": "Q"})
    first, second = (c["config"]["configurable"]["thread_id"] for c in stub.calls)
    assert first != second  # 每次请求独立会话


def test_stream_failure_degrades_to_error_event():
    chunks = [
        ("updates", {"planner": {"plan": TWO_STEP_PLAN, "revision_count": 0, "messages": []}}),
    ]
    client, _ = make_client_with_stub(chunks, error_after=1)
    resp = client.post("/api/chat", json={"question": "Q"})

    events = parse_sse(resp.text)
    errors = events_of(events, "error")
    assert len(errors) == 1
    assert "桩图故意抛错" in errors[0]["message"]
    assert events_of(events, "final") == []  # 出错后不再有 final
