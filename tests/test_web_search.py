"""web_search 工具测试：演示数据回退 + Tavily 分支（mock httpx）。"""
import sys

import app.tools.web_search  # noqa: F401  触发子模块加载

# app/tools/__init__ 把包属性 web_search 覆盖成了 Tool 对象，
# 因此这里从 sys.modules 取真正的模块以便访问 httpx 等内部引用。
ws_mod = sys.modules["app.tools.web_search"]

from app.config import get_settings


def test_demo_fallback_hit(monkeypatch):
    monkeypatch.setattr(get_settings(), "tavily_api_key", "")
    out = ws_mod.web_search.invoke({"query": "布洛芬和对乙酰氨基酚能一起吃吗？"})
    assert "布洛芬" in out
    assert "演示数据" in out


def test_demo_fallback_no_hit(monkeypatch):
    monkeypatch.setattr(get_settings(), "tavily_api_key", "")
    out = ws_mod.web_search.invoke({"query": "量子纠缠的原理是什么"})
    assert "未检索到" in out


def test_tavily_branch(monkeypatch):
    monkeypatch.setattr(get_settings(), "tavily_api_key", "test-key")

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "results": [
                    {"title": "Tavily标题", "content": "Tavily正文", "url": "https://t.cn/1"}
                ]
            }

    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"], captured["payload"] = url, json
        return FakeResp()

    monkeypatch.setattr(ws_mod.httpx, "post", fake_post)
    out = ws_mod.web_search.invoke({"query": "成年人每天需要多少维生素C"})
    assert "Tavily 检索结果" in out and "Tavily标题" in out
    assert captured["payload"]["query"] == "成年人每天需要多少维生素C"
    assert captured["payload"]["api_key"] == "test-key"


def test_tavily_failure_falls_back_to_demo(monkeypatch):
    monkeypatch.setattr(get_settings(), "tavily_api_key", "test-key")

    def boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(ws_mod.httpx, "post", boom)
    out = ws_mod.web_search.invoke({"query": "高血压"})
    assert "演示数据" in out and "高血压" in out


def test_tavily_empty_results_falls_back(monkeypatch):
    monkeypatch.setattr(get_settings(), "tavily_api_key", "test-key")

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": []}

    monkeypatch.setattr(ws_mod.httpx, "post", lambda *a, **k: FakeResp())
    out = ws_mod.web_search.invoke({"query": "阿莫西林"})
    assert "演示数据" in out and "阿莫西林" in out
