"""LLM 工厂：统一创建 ChatOpenAI 客户端（SiliconFlow OpenAI 兼容端点）。"""
from langchain_openai import ChatOpenAI

from app.config import get_settings


def create_llm(temperature: float | None = None, **kwargs) -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=settings.model,
        api_key=settings.siliconflow_api_key or "sk-not-configured",
        base_url=settings.base_url,
        temperature=settings.temperature if temperature is None else temperature,
        **kwargs,
    )
