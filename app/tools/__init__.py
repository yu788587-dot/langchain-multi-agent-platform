"""工具集：calculator / web_search / drug_lookup，统一注册表与描述清单。"""
from app.tools.calculator import calculator
from app.tools.drug_lookup import drug_lookup
from app.tools.web_search import web_search

ALL_TOOLS = [calculator, web_search, drug_lookup]

TOOL_REGISTRY = {t.name: t for t in ALL_TOOLS}


def tools_description() -> str:
    """供 Planner 提示词使用的工具清单（名称 + 首行描述，LLM 依据它选择工具）。"""
    return "\n".join(f"- {t.name}: {t.description.strip().splitlines()[0]}" for t in ALL_TOOLS)
