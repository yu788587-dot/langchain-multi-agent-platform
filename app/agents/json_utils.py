"""LLM 输出解析容错与提示词辅助工具。"""
import json
import re


def extract_json(text: str) -> dict | None:
    """从 LLM 输出中尽力提取第一个 JSON 对象；失败返回 None。"""
    if not text:
        return None
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def brace_safe(text) -> str:
    """转义花括号，避免动态内容进入 str.format 时被误解析。"""
    return str(text).replace("{", "{{").replace("}", "}}")
