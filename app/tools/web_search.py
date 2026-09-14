"""联网搜索工具：优先走 Tavily REST API；未配置密钥或网络失败时回退内置演示医疗数据。"""
import httpx
from langchain_core.tools import tool

from app.config import get_settings

_TAVILY_ENDPOINT = "https://api.tavily.com/search"

_DEMO_CORPUS = [
    {
        "keywords": ["布洛芬", "对乙酰氨基酚", "扑热息痛", "退热", "一起吃", "联用"],
        "title": "布洛芬与对乙酰氨基酚联用须知",
        "content": "布洛芬（非甾体抗炎药）与对乙酰氨基酚（扑热息痛）作用机制不同，在医生或药师指导下可交替用于退热，但不建议自行长期叠加；两者超量均可能造成肝肾损伤，儿童、孕产妇及肝肾功能不全者使用前必须咨询医师。",
        "url": "https://example.com/demo/ibuprofen-paracetamol",
    },
    {
        "keywords": ["维生素c", "维生素", "维c", "摄入量"],
        "title": "成年人每日维生素C推荐摄入量",
        "content": "中国营养学会推荐成年人每日维生素C摄入量约100毫克，可耐受最高摄入量为2000毫克；日常通过新鲜蔬果（猕猴桃、鲜枣、青椒等）摄入即可满足，长期大剂量补充可能增加肾结石风险。",
        "url": "https://example.com/demo/vitamin-c",
    },
    {
        "keywords": ["高血压", "血压", "降压"],
        "title": "高血压日常管理与用药提醒",
        "content": "高血压患者应低盐饮食、规律运动、定期测量血压；常用降压药包括氨氯地平等钙通道阻滞剂，须长期规律服用，不可自行停药或频繁换药，血压控制目标遵医嘱（一般低于140/90mmHg）。",
        "url": "https://example.com/demo/hypertension",
    },
    {
        "keywords": ["二甲双胍", "糖尿病", "降糖", "血糖"],
        "title": "二甲双胍：2型糖尿病一线降糖药",
        "content": "二甲双胍是2型糖尿病（尤其超重者）的一线降糖药，常见副作用为胃肠道反应，建议随餐服用；严重肾功能不全、缺氧状态等患者禁用，用药期间定期监测肾功能与维生素B12。",
        "url": "https://example.com/demo/metformin",
    },
    {
        "keywords": ["阿莫西林", "抗生素", "消炎药", "感染"],
        "title": "阿莫西林使用注意事项",
        "content": "阿莫西林为青霉素类处方抗生素，用于敏感菌引起的感染；青霉素过敏者禁用，用药前必须告知医生过敏史；应足量足疗程使用，不可症状缓解后自行停药，以免细菌耐药。",
        "url": "https://example.com/demo/amoxicillin",
    },
    {
        "keywords": ["感冒", "发烧", "咳嗽", "鼻塞"],
        "title": "普通感冒的对症处理",
        "content": "普通感冒多由病毒引起，以休息、多饮水为主；发热或头痛可对症使用对乙酰氨基酚或布洛芬；注意许多复方感冒药已含对乙酰氨基酚，避免与退烧药重复叠加造成过量。",
        "url": "https://example.com/demo/common-cold",
    },
]


def _tavily_search(query: str) -> str | None:
    """调用 Tavily REST API；任何失败返回 None 以便回退演示数据。"""
    try:
        resp = httpx.post(
            _TAVILY_ENDPOINT,
            json={"api_key": get_settings().tavily_api_key, "query": query, "max_results": 5},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results") or []
    except Exception:
        return None
    if not results:
        return None
    lines = [
        f"{i}. {r.get('title', '')}\n   {r.get('content', '')}\n   来源: {r.get('url', '')}"
        for i, r in enumerate(results, start=1)
    ]
    return "Tavily 检索结果：\n" + "\n".join(lines)


def _demo_search(query: str) -> str:
    q = (query or "").strip().lower()
    if q:
        hits = [doc for doc in _DEMO_CORPUS if any(kw in q for kw in doc["keywords"])]
    else:
        hits = []
    if not hits:
        return (
            f"未检索到与「{query}」相关的资料。"
            "当前为内置演示数据，仅覆盖常见药品与健康话题（如布洛芬、维生素C、高血压等）。"
        )
    lines = [
        f"{i}. {doc['title']}\n   {doc['content']}\n   来源: {doc['url']}"
        for i, doc in enumerate(hits, start=1)
    ]
    return f"【演示数据】检索到 {len(hits)} 条相关资料：\n" + "\n".join(lines)


@tool
def web_search(query: str) -> str:
    """联网搜索医疗健康参考资料。输入为搜索关键词或问题，例如"布洛芬和对乙酰氨基酚能一起吃吗"。"""
    if get_settings().tavily_api_key:
        result = _tavily_search(query)
        if result is not None:
            return result
    return _demo_search(query)
