"""全局配置：从 .env 读取密钥与模型参数，全程不落盘、不打印密钥。"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    siliconflow_api_key: str = ""
    base_url: str = "https://api.siliconflow.cn/v1"
    model: str = "deepseek-ai/DeepSeek-V3"
    tavily_api_key: str = ""
    max_revisions: int = 2
    temperature: float = 0.3


@lru_cache
def get_settings() -> Settings:
    return Settings()
