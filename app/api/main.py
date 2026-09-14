"""FastAPI 入口：POST /api/chat 以 SSE 流式推送多智能体执行过程，/ 托管前端静态页面。

流式映射：langgraph `stream_mode=["updates","custom"]` → SSE 事件协议（前后端契约见 README）：
- updates 模式驱动主事件序列（plan / step 汇总 / review / final），并按图拓扑推导各角色 start/done；
- custom 模式承接 executor 的 `_emit` 自定义事件，提供逐步进行中的实时反馈；
- 出错时以 `event: error` 收尾，保证前端总能收到可展示的终止信号。
"""
import json
import time
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.api.schemas import ChatRequest

app = FastAPI(title="LangChain 多智能体医疗问答平台", version="1.0.0")

_STATIC_DIR = Path(__file__).resolve().parents[2] / "static"

_TOOL_OUTPUT_LIMIT = 500  # SSE step 事件中工具输出的截断上限

_graph = None


def get_graph():
    """延迟构建默认图（带内存检查点）；测试可通过 set_graph 注入替身。"""
    global _graph
    if _graph is None:
        from app.graph.workflow import build_default_graph

        _graph = build_default_graph()
    return _graph


def set_graph(graph) -> None:
    """测试注入/重置图实例。"""
    global _graph
    _graph = graph


def _sse(event: str, data: dict) -> str:
    """编码一条 SSE 消息（UTF-8、中文不转义）。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _truncate(text, limit: int = _TOOL_OUTPUT_LIMIT) -> str:
    return str(text or "")[:limit]


def _chat_events(question: str, thread_id: str | None) -> Iterator[str]:
    """把 langgraph 流事件翻译为 SSE 事件序列（协议见 README）。"""
    start = time.monotonic()
    try:
        graph = get_graph()
        # 检查点器要求 config 必带 thread_id；未传则每次请求使用独立随机会话
        config = {"configurable": {"thread_id": thread_id or uuid4().hex}}
        stream = graph.stream(
            {"question": question}, config=config, stream_mode=["updates", "custom"]
        )

        yield _sse("agent", {"role": "planner", "phase": "start"})

        current_round = 0   # 当前执行轮次（0 为首次；每次 revise 重跑 +1）
        executor_done = 0   # 已完成的 executor 节点次数（最终 revisions = executor_done - 1）
        complete_steps: set[tuple[int, int]] = set()  # 已发出含 sub_answer 的 (round, step)
        tool_outputs: dict[tuple[int, int], str] = {}  # (round, step) → 工具原始输出（≤500）

        for mode, payload in stream:
            if mode == "custom":
                # executor 执行中的实时自定义事件：tool（工具已产出观测）/ step_done（子答案就绪）
                kind = payload.get("type")
                key = (current_round, payload.get("step"))
                if kind == "tool":
                    output = _truncate(payload.get("tool_output"))
                    tool_outputs.setdefault(key, output)
                    yield _sse(
                        "step",
                        {
                            "round": current_round,
                            "step": payload.get("step"),
                            "tool": payload.get("tool"),
                            "tool_input": _truncate(payload.get("tool_input")),
                            "tool_output": output,
                            "sub_answer": None,  # 子答案尚未生成
                        },
                    )
                elif kind == "step_done":
                    complete_steps.add(key)
                    yield _sse(
                        "step",
                        {
                            "round": current_round,
                            "step": payload.get("step"),
                            "tool": payload.get("tool"),
                            "tool_input": _truncate(payload.get("tool_input")),
                            "tool_output": tool_outputs.get(key, ""),
                            "sub_answer": payload.get("sub_answer"),
                        },
                    )
                continue

            # updates 模式：payload 形如 {节点名: 状态增量}
            for node, delta in (payload or {}).items():
                delta = delta or {}
                if node == "planner":
                    steps = [
                        {
                            "step": s.get("step"),
                            "tool": s.get("tool"),
                            "description": s.get("description"),
                        }
                        for s in delta.get("plan") or []
                    ]
                    yield _sse("plan", {"steps": steps})
                    yield _sse(
                        "agent", {"role": "planner", "phase": "done", "steps": len(steps)}
                    )
                    yield _sse(
                        "agent", {"role": "executor", "phase": "start", "round": current_round}
                    )
                elif node == "executor":
                    executor_done += 1
                    # 兜底补发：替身/异常路径下 executor 可能未发 custom 事件
                    for r in delta.get("steps_results") or []:
                        key = (current_round, r.get("step"))
                        if key in complete_steps:
                            continue
                        complete_steps.add(key)
                        output = _truncate(r.get("tool_output"))
                        tool_outputs.setdefault(key, output)
                        yield _sse(
                            "step",
                            {
                                "round": current_round,
                                "step": r.get("step"),
                                "tool": r.get("tool"),
                                "tool_input": _truncate(r.get("tool_input")),
                                "tool_output": output,
                                "sub_answer": r.get("sub_answer"),
                            },
                        )
                    yield _sse(
                        "agent",
                        {"role": "executor", "phase": "done", "round": current_round},
                    )
                    yield _sse("agent", {"role": "reviewer", "phase": "start"})
                elif node == "reviewer":
                    review = delta.get("review") or {}
                    yield _sse(
                        "review",
                        {"verdict": review.get("verdict"), "feedback": review.get("feedback", "")},
                    )
                    yield _sse(
                        "agent",
                        {"role": "reviewer", "phase": "done", "verdict": review.get("verdict")},
                    )
                    if review.get("verdict") == "revise":
                        current_round += 1  # 审核要求修订：执行者即将重跑
                        yield _sse(
                            "agent", {"role": "executor", "phase": "start", "round": current_round}
                        )
                    else:
                        yield _sse("agent", {"role": "finalizer", "phase": "start"})
                elif node == "finalize":
                    yield _sse("agent", {"role": "finalizer", "phase": "done"})
                    yield _sse(
                        "final",
                        {
                            "answer": delta.get("final_answer", ""),
                            "elapsed_ms": int((time.monotonic() - start) * 1000),
                            "revisions": max(0, executor_done - 1),
                        },
                    )
    except Exception as exc:  # 流中途任何异常都降级为 error 事件，前端可展示
        yield _sse("error", {"message": f"服务器处理失败：{exc}"})


@app.post("/api/chat")
def chat(req: ChatRequest) -> StreamingResponse:
    """接收问题，返回 text/event-stream 流式执行过程。"""
    return StreamingResponse(
        _chat_events(req.question, req.thread_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 等反代缓冲，保证事件实时到达
            "Connection": "keep-alive",
        },
    )


# 静态托管放在最后注册：显式 API 路由优先匹配，/ 兜底到 static/index.html
app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
