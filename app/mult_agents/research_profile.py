"""运行时研究域配置：让同一套研究链路支持企业知识库和金融投研。"""

from collections.abc import Iterable


FINANCE_TERMS = {
    "股票", "个股", "估值", "财务", "研报", "市值", "股价", "PE", "PB", "ROE",
    "DCF", "营收", "净利润", "现金流", "宏观经济", "行业景气", "机构评级", "A股", "港股",
}


def resolve_research_domain(requested: str, query: str) -> str:
    value = (requested or "auto").strip().lower()
    if value in {"finance", "general"}:
        return value
    return "finance" if any(term.lower() in query.lower() for term in FINANCE_TERMS) else "general"


def research_guidance(domain: str) -> str:
    if domain == "finance":
        return (
            "本次研究域为 finance。可以使用宏观、行业、公司、估值、舆情框架；"
            "所有金融数据要标注时点和来源，不把公开信息整理结果表述为投资建议。"
        )
    return (
        "本次研究域为 general enterprise research。请围绕用户问题动态设计章节，"
        "优先覆盖背景、现状、方案/技术、对比、风险与结论；不要强行生成投资评级、目标价或财务指标。"
    )


def source_summary(evidence: Iterable[dict], source_index: Iterable[dict]) -> dict:
    evidence_items = list(evidence or [])
    sources = list(source_index or [])
    source_types = sorted({str(item.get("source_type", "unknown")) for item in evidence_items})
    scores = [float(item.get("reliability_score", 0)) for item in evidence_items if item.get("reliability_score") is not None]
    return {
        "evidence_count": len(evidence_items),
        "source_count": len(sources),
        "source_types": source_types,
        "avg_reliability": round(sum(scores) / len(scores), 3) if scores else None,
        "high_confidence_count": sum(1 for score in scores if score >= 0.8),
    }
