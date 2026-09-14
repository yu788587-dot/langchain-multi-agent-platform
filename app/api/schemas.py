"""API 请求模型：pydantic 校验，缺 question 或空白问题统一返回 422。"""
from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """POST /api/chat 请求体。"""

    question: str = Field(..., min_length=1, max_length=2000, description="用户的医疗健康问题")
    thread_id: str | None = Field(None, max_length=128, description="可选会话ID，用于多轮状态隔离")

    @field_validator("question")
    @classmethod
    def _strip_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question 不能为空白")
        return value
