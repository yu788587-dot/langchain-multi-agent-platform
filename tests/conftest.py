"""测试公共设施：按序返回预设响应的 FakeLLM，替代真实 API。"""
import pytest
from langchain_core.messages import AIMessage


class FakeLLM:
    """按序返回预设响应的假 LLM；记录每次收到的 messages 供断言。"""

    def __init__(self, responses):
        self._responses = [
            r if isinstance(r, AIMessage) else AIMessage(content=r) for r in responses
        ]
        self.calls = []

    def invoke(self, messages, config=None, **kwargs):
        self.calls.append(messages)
        if not self._responses:
            raise AssertionError("FakeLLM 响应已用尽")
        return self._responses.pop(0)


@pytest.fixture
def make_fake_llm():
    return FakeLLM
