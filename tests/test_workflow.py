"""workflow 测试：mock 全部节点，验证图拓扑、revise 回环、超限强制定稿。"""
from app.config import get_settings
from app.graph import workflow as wf_mod


def _patch_nodes(monkeypatch, planner_fn, executor_fn, reviewer_fn, finalize_fn):
    monkeypatch.setattr(wf_mod, "planner_node", planner_fn)
    monkeypatch.setattr(wf_mod, "executor_node", executor_fn)
    monkeypatch.setattr(wf_mod, "reviewer_node", reviewer_fn)
    monkeypatch.setattr(wf_mod, "finalize_node", finalize_fn)


def _plan():
    # 与真实 planner_node 的返回形状一致：工作流起点初始化修订计数
    return {
        "plan": [{"step": 1, "tool": "none", "tool_input": "", "description": "d"}],
        "revision_count": 0,
    }


def _executed():
    return {
        "steps_results": [{"step": 1, "tool": "none", "tool_input": "", "tool_output": "", "sub_answer": "a"}],
        "messages": [{"role": "executor", "phase": "done"}],
    }


def test_approved_flow_runs_each_node_once(monkeypatch):
    calls = []

    def planner(s):
        calls.append("planner")
        return _plan()

    def executor(s):
        calls.append("executor")
        return _executed()

    def reviewer(s):
        calls.append("reviewer")
        return {"review": {"verdict": "approved", "feedback": ""}, "messages": []}

    def finalize(s):
        calls.append("finalize")
        return {"final_answer": "最终答案", "messages": [{"role": "finalizer", "phase": "done"}]}

    _patch_nodes(monkeypatch, planner, executor, reviewer, finalize)
    graph = wf_mod.build_workflow()
    final = graph.invoke({"question": "Q"})

    assert calls == ["planner", "executor", "reviewer", "finalize"]
    assert final["final_answer"] == "最终答案"
    assert final["revision_count"] == 0
    assert len(final["messages"]) >= 2  # messages 走追加式 reducer


def test_revise_loop_then_approve(monkeypatch):
    verdicts = iter(["revise", "approved"])
    executor_calls = []

    def planner(s):
        return _plan()

    def executor(s):
        executor_calls.append(s.get("review"))
        return _executed()

    def reviewer(s):
        v = next(verdicts)
        out = {"review": {"verdict": v, "feedback": "改一下"}, "messages": []}
        if v == "revise":
            out["revision_count"] = s.get("revision_count", 0) + 1
        return out

    def finalize(s):
        return {"final_answer": "定稿", "messages": []}

    _patch_nodes(monkeypatch, planner, executor, reviewer, finalize)
    graph = wf_mod.build_workflow()
    final = graph.invoke({"question": "Q"})

    assert len(executor_calls) == 2  # 初次执行 + 1 次修订
    assert executor_calls[1]["verdict"] == "revise"  # 第二次执行时收到审核反馈
    assert final["final_answer"] == "定稿"


def test_max_revisions_forces_finalize(monkeypatch):
    monkeypatch.setattr(get_settings(), "max_revisions", 2)
    executor_calls = []

    def planner(s):
        return _plan()

    def executor(s):
        executor_calls.append(s.get("revision_count", 0))
        return _executed()

    def reviewer(s):
        return {
            "review": {"verdict": "revise", "feedback": "再改"},
            "revision_count": s.get("revision_count", 0) + 1,
            "messages": [],
        }

    finalize_calls = []

    def finalize(s):
        finalize_calls.append(1)
        return {"final_answer": "超限定稿", "messages": []}

    _patch_nodes(monkeypatch, planner, executor, reviewer, finalize)
    graph = wf_mod.build_workflow()
    final = graph.invoke({"question": "Q"})

    assert len(executor_calls) == 3  # 1 次初始 + MAX_REVISIONS(2) 次修订
    assert len(finalize_calls) == 1  # 超限后直接强制定稿，不再回环
    assert final["final_answer"] == "超限定稿"
    assert final["revision_count"] == 3


def test_max_revisions_respects_settings(monkeypatch):
    monkeypatch.setattr(get_settings(), "max_revisions", 1)
    executor_calls = []

    def planner(s):
        return _plan()

    def executor(s):
        executor_calls.append(1)
        return _executed()

    def reviewer(s):
        return {
            "review": {"verdict": "revise", "feedback": "改"},
            "revision_count": s.get("revision_count", 0) + 1,
            "messages": [],
        }

    def finalize(s):
        return {"final_answer": "定稿", "messages": []}

    _patch_nodes(monkeypatch, planner, executor, reviewer, finalize)
    graph = wf_mod.build_workflow()
    graph.invoke({"question": "Q"})
    assert len(executor_calls) == 2  # 1 + 1 次修订


def test_checkpointed_graph_supports_thread_id(monkeypatch):
    def planner(s):
        return _plan()

    def executor(s):
        return _executed()

    def reviewer(s):
        return {"review": {"verdict": "approved", "feedback": ""}, "messages": []}

    def finalize(s):
        return {"final_answer": "带检查点的答案", "messages": []}

    _patch_nodes(monkeypatch, planner, executor, reviewer, finalize)
    graph = wf_mod.build_default_graph()
    config = {"configurable": {"thread_id": "thread-1"}}
    final = graph.invoke({"question": "Q"}, config=config)
    assert final["final_answer"] == "带检查点的答案"
