"""节点执行模块：实现意图识别、检索、证据裁判、分析与写作等节点逻辑。"""

import json
import logging
import os
import re
from functools import partial

from langchain_core.messages import HumanMessage

from .state import ResearchState
from .tools import bocha_web_search_records, search_knowledge_base_records


logger = logging.getLogger("mult_agents")


ANSI = {
    "reset": "\033[0m",
    "cyan": "\033[36m",
    "magenta": "\033[35m",
    "yellow": "\033[33m",
    "green": "\033[32m",
    "red": "\033[31m",
}


def colorize(text: str, color: str) -> str:
    if os.getenv("NO_COLOR"):
        return text
    code = ANSI.get(color, "")
    if not code:
        return text
    return f"{code}{text}{ANSI['reset']}"


def emit(node: str, content: str):
    preview = content.replace("\n", " ")
    if len(preview) > 400:
        preview = preview[:400] + "..."
    logger.info("%s 输出: %s", colorize(f"[{node}]", "yellow"), preview)


def collect_tool_calls(messages) -> tuple[list, list]:
    tools = []
    tool_outputs = []
    for msg in messages:
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            for call in tool_calls:
                name = call.get("name") if isinstance(call, dict) else None
                if name:
                    tools.append(name)
        name = getattr(msg, "name", None)
        msg_type = getattr(msg, "type", None)
        if msg_type == "tool" and name:
            tools.append(name)
            output = getattr(msg, "content", "")
            if output:
                tool_outputs.append(f"{name}: {output}")
    return tools, tool_outputs


def with_memory_context(state: ResearchState, user_prompt: str) -> str:
    memory_context = state.get("memory_context", "").strip()
    if not memory_context:
        return user_prompt
    return f"{user_prompt}\n\n[跨会话记忆]\n{memory_context}"


def log_inputs(node: str, agent_name: str, payload: dict):
    preview = {
        key: (value[:200] + "..." if isinstance(value, str) and len(value) > 200 else value)
        for key, value in payload.items()
    }
    logger.info("%s 输入 | agent=%s | data=%s", colorize(f"[{node}]", "cyan"), colorize(agent_name, "magenta"), preview)


def detect_intent(query: str) -> str:
    normalized_query = query.strip()
    force_multiagent_keywords = [
        "调查",
        "调研",
        "来源",
        "证据",
        "检索统计",
        "来源清单",
        "重大新闻",
        "热门项目",
        "趋势",
        "新闻",
        "最新",
        "盘点",
    ]
    if re.search(r"20\d{2}年", normalized_query) and any(word in normalized_query for word in ["趋势", "新闻", "调研", "调查", "盘点"]):
        return "multiagent"
    if any(word in query for word in force_multiagent_keywords):
        return "multiagent"
    keywords = [
        "调研",
        "研究",
        "调查",
        "盘点",
        "热门",
        "趋势",
        "榜单",
        "分析",
        "方案",
        "架构",
        "设计",
        "对比",
        "报告",
        "代码",
        "实现",
        "落地",
        "检索",
        "知识库",
        "证据",
        "来源",
        "溯源",
        "资料",
        "手册",
        "验证",
        "数据",
        "模型",
    ]
    return "multiagent" if any(word in query for word in keywords) else "direct"


def bind_agent(node_func, agent, agent_name: str):
    return partial(node_func, agent=agent, agent_name=agent_name)


def _last_content(result) -> str:
    content = result["messages"][-1].content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(item.get("text", "") if isinstance(item, dict) else str(item) for item in content)
    return str(content)


def _extract_json_block(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return cleaned[start : end + 1]
    return cleaned


def _load_json(text: str, fallback: dict) -> dict:
    try:
        value = json.loads(_extract_json_block(text))
        if isinstance(value, dict):
            return value
    except Exception:
        pass
    return fallback


def _invoke_json_agent(state: ResearchState, prompt: str, agent, agent_name: str, node: str, fallback: dict) -> tuple[dict, str, list]:
    human = HumanMessage(content=with_memory_context(state, prompt))
    # Optimization: Do NOT pass state["messages"] to avoid token accumulation
    # Each node only needs its specific instruction and the current state data
    result = agent.invoke({"messages": [human]})
    tools, tool_outputs = collect_tool_calls(result["messages"])
    logger.info("%s 工具: %s", colorize(f"[{node}]", "green"), ", ".join(tools) if tools else "无")
    for item in tool_outputs[:5]:
        logger.info("%s 工具输出: %s", colorize(f"[{node}]", "green"), item[:400])
    logger.info("%s LLM调用: 是 | 思考: 不可见", colorize(f"[{node}]", "yellow"))
    content = _last_content(result)
    emit(node, content)
    return _load_json(content, fallback), content, [human, result["messages"][-1]]


def _default_plan(state: ResearchState) -> dict:
    return {
        "objective": state["query"],
        "sub_questions": [state["query"]],
        "outline": [
            {
                "id": "sec_1",
                "title": "默认大纲",
                "description": "默认生成的大纲",
                "section_type": "mixed",
                "requires_data": False,
                "requires_chart": False,
                "priority": 1,
                "search_queries": [state["query"]],
                "status": "pending",
            }
        ],
        "research_questions": [state["query"]],
        "budget": {"max_rounds": 2, "max_sources": 12, "max_tokens": 12000, "max_seconds": 45},
    }


def _guess_primary_entity(query: str) -> str:
    lowered = query.lower()
    ascii_terms = re.findall(r"[a-z][a-z0-9_-]{2,}", lowered)
    for term in ascii_terms:
        if term not in {"latest", "trend", "news", "agent", "open", "using"}:
            return term
    chinese_terms = re.findall(r"[\u4e00-\u9fff]{2,}", query)
    for term in chinese_terms:
        if term not in {"帮我", "调查", "最新", "使用趋势", "是什么", "多少", "情况"}:
            return term
    return ""


def _derive_direct_search_queries(query: str) -> list[str]:
    base_query = query.strip()
    if not base_query:
        return []
    entity = _guess_primary_entity(base_query)
    candidates = [base_query]
    if entity:
        candidates.extend(
            [
                f"{entity}是什么",
                f"{entity} GitHub",
                f"{entity} 官方文档",
                f"{entity} 使用趋势",
                f"{entity} AI Agent",
            ]
        )
    else:
        candidates.extend(
            [
                f"{base_query} 是什么",
                f"{base_query} GitHub",
                f"{base_query} 官方文档",
            ]
        )
    deduped: list[str] = []
    for item in candidates:
        text = item.strip()
        if text and text not in deduped:
            deduped.append(text)
    return deduped[:6]


def _is_query_grounded(candidate: str, user_query: str) -> bool:
    candidate_terms = set(_extract_query_terms(candidate))
    user_terms = set(_extract_query_terms(user_query))
    if not candidate_terms or not user_terms:
        return False
    if _guess_primary_entity(user_query) and _guess_primary_entity(user_query) in candidate.lower():
        return True
    overlap = candidate_terms & user_terms
    return len(overlap) >= 1


def _derive_search_plan(outline: list[dict], sub_questions: list[str], _research_questions: list[str], query: str) -> list[dict]:
    plan: list[dict] = []
    for direct_query in _derive_direct_search_queries(query):
        plan.append(
            {
                "section_id": "user_query",
                "query": direct_query,
                "source_preference": "hybrid",
                "reason": "围绕用户原始问题生成的直接检索词",
            }
        )
    for section in outline:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("id") or "sec")
        for item in section.get("search_queries", []) or []:
            text = str(item).strip()
            if text and _is_query_grounded(text, query):
                plan.append(
                    {
                        "section_id": section_id,
                        "query": text,
                        "source_preference": "hybrid",
                        "reason": f"来自大纲章节 {section_id}",
                    }
                )
    if not plan:
        plan.append({"section_id": "sec_1", "query": query, "source_preference": "hybrid", "reason": "fallback"})
    deduped = _dedupe_sources(plan, ["query"])
    return deduped[:6]


def _build_queries(state: ResearchState, source_preference: str) -> list[dict]:
    queries: list[dict] = []
    
    # Check if we are in re-search iteration
    iteration = state.get("iteration", 0)
    if iteration > 0 and state.get("supplementary_queries"):
        base_plan = state.get("supplementary_queries", [])
    else:
        base_plan = state.get("search_plan", [])
        
    for item in base_plan:
        if not isinstance(item, dict):
            continue
        pref = item.get("source_preference", "hybrid")
        if pref in (source_preference, "hybrid"):
            query = str(item.get("query", "")).strip()
            if query:
                queries.append(item)
    if not queries:
        queries.append({"section_id": "sec_1", "query": state["query"], "source_preference": source_preference, "reason": "fallback"})
    return queries[:6]


def _extract_query_terms(query: str) -> list[str]:
    parts = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_-]{3,}", query.lower())
    terms = []
    stopwords = {"什么", "如何", "以及", "一个", "关于", "这个", "那个", "进行", "基于", "附带", "来源", "清单"}
    for part in parts:
        if part in stopwords:
            continue
        terms.append(part)
    return terms[:12]


def _estimate_relevance(query: str, text: str) -> float:
    terms = _extract_query_terms(query)
    if not terms:
        return 0.0
    haystack = text.lower()
    hits = sum(1 for term in terms if term in haystack)
    return hits / max(len(terms), 1)


def _is_bad_web_domain(domain: str) -> bool:
    value = domain.lower()
    blocked = ["datasheet", "bdtic", "doc88", "elecfans", "down"]
    return any(item in value for item in blocked)


def _filter_web_records(query: str, records: list[dict]) -> tuple[list[dict], dict]:
    kept = []
    stats = {"raw_count": len(records), "kept_count": 0, "dropped_irrelevant": 0, "dropped_domain": 0, "dropped_empty": 0}
    for record in records:
        title = str(record.get("title", ""))
        snippet = str(record.get("snippet", ""))
        domain = str(record.get("domain", ""))
        if not title and not snippet:
            stats["dropped_empty"] += 1
            continue
        if _is_bad_web_domain(domain):
            stats["dropped_domain"] += 1
            continue
        relevance = _estimate_relevance(query, f"{title}\n{snippet}")
        record["relevance_score"] = relevance
        if relevance < 0.2 and not _is_official_domain(domain):
            stats["dropped_irrelevant"] += 1
            continue
        kept.append(record)
    stats["kept_count"] = len(kept)
    return kept, stats


def _filter_local_records(query: str, records: list[dict]) -> tuple[list[dict], dict]:
    kept = []
    stats = {"raw_count": len(records), "kept_count": 0, "dropped_irrelevant": 0, "dropped_missing_doc": 0, "dropped_empty": 0}
    for record in records:
        title = str(record.get("title", ""))
        snippet = str(record.get("snippet", ""))
        doc_id = str(record.get("doc_id", "")).strip()
        if not snippet:
            stats["dropped_empty"] += 1
            continue
        relevance = _estimate_relevance(query, f"{title}\n{snippet}")
        record["relevance_score"] = relevance
        if not doc_id and relevance < 0.35:
            stats["dropped_missing_doc"] += 1
            continue
        if relevance < 0.2:
            stats["dropped_irrelevant"] += 1
            continue
        kept.append(record)
    stats["kept_count"] = len(kept)
    return kept, stats


def _format_raw_records(records: list[dict], source_type: str) -> str:
    if not records:
        return "[]"
    lines = []
    for record in records[:40]:
        locator = record.get("url") or record.get("doc_id") or ""
        lines.append(
            json.dumps(
                {
                    "source_id": record.get("source_id"),
                    "title": record.get("title"),
                    "url": record.get("url", ""),
                    "doc_id": record.get("doc_id", ""),
                    "snippet": str(record.get("snippet", ""))[:500],
                    "source_type": source_type,
                },
                ensure_ascii=False,
            )
        )
    return "\n".join(lines)


def _minimal_record_filter(records: list[dict], required_any: list[str]) -> list[dict]:
    kept: list[dict] = []
    for record in records:
        if any(str(record.get(field, "")).strip() for field in required_any):
            kept.append(record)
    return kept


def _assign_source_ids(records: list[dict], prefix: str) -> list[dict]:
    assigned: list[dict] = []
    for index, record in enumerate(records, 1):
        item = dict(record)
        item["source_id"] = f"{prefix}-{index}"
        assigned.append(item)
    return assigned


def _enrich_evidence_from_raw(evidence: list[dict], raw_records: list[dict]) -> list[dict]:
    """从原始记录中补充 evidence 中可能丢失的 url、domain 等字段"""
    raw_lookup = {str(r.get("source_id", "")).strip(): r for r in raw_records if r.get("source_id")}
    enriched = []
    for ev in evidence:
        item = dict(ev)
        sid = str(item.get("source_id", "")).strip()
        raw = raw_lookup.get(sid, {})
        # 补充 url（如 LLM 没有保留）
        if not item.get("url") and raw.get("url"):
            item["url"] = raw["url"]
        # 补充 domain
        if not item.get("domain") and raw.get("domain"):
            item["domain"] = raw["domain"]
        # 补充 title（如 LLM 没有保留）
        if not item.get("title") and raw.get("title"):
            item["title"] = raw["title"]
        enriched.append(item)
    return enriched


def _prune_evidence_to_allowed_sources(evidence: list[dict], allowed_source_ids: set[str]) -> list[dict]:
    kept: list[dict] = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("source_id", "")).strip()
        if source_id and source_id in allowed_source_ids:
            kept.append(item)
    return kept


def _summarize_records(records: list[dict]) -> list[dict]:
    summary: list[dict] = []
    for record in records[:5]:
        summary.append(
            {
                "source_id": record.get("source_id"),
                "title": record.get("title", ""),
                "locator": record.get("url") or record.get("doc_id") or "",
                "snippet": str(record.get("snippet", ""))[:160],
            }
        )
    return summary


def _normalize_source_ids(values) -> list[str]:
    normalized: list[str] = []
    for value in values or []:
        text = str(value).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _finalize_query_traces(query_traces: list[dict], kept_ids: set[str], rejected_ids: list[str], reject_reason: str) -> list[dict]:
    normalized_rejected = set(_normalize_source_ids(rejected_ids))
    finalized: list[dict] = []
    for trace in query_traces:
        raw_items = [item for item in trace.get("raw_records", []) if isinstance(item, dict)]
        kept_records = [item for item in raw_items if str(item.get("source_id", "")).strip() in kept_ids]
        rejected_records = [
            item
            for item in raw_items
            if str(item.get("source_id", "")).strip() in normalized_rejected or str(item.get("source_id", "")).strip() not in kept_ids
        ]
        trace_item = dict(trace)
        trace_item["raw_source_ids"] = _normalize_source_ids(item.get("source_id") for item in raw_items)
        trace_item["kept_source_ids"] = _normalize_source_ids(item.get("source_id") for item in kept_records)
        trace_item["rejected_source_ids"] = _normalize_source_ids(item.get("source_id") for item in rejected_records)
        trace_item["kept_count"] = len(trace_item["kept_source_ids"])
        trace_item["rejected_count"] = len(trace_item["rejected_source_ids"])
        trace_item["kept_records"] = kept_records[:3]
        trace_item["rejected_records"] = rejected_records[:3]
        if reject_reason:
            trace_item["reject_reason"] = reject_reason
        finalized.append(trace_item)
    return finalized


def _fallback_web_evidence(records: list[dict]) -> dict:
    evidence = []
    for record in records:
        evidence.append(
            {
                "source_id": record.get("source_id"),
                "title": record.get("title"),
                "url": record.get("url", ""),
                "snippet": record.get("snippet", ""),
                "domain": record.get("domain", ""),
                "source_type": "web",
                "reliability_hint": "official" if _is_official_domain(record.get("domain", "")) else "unknown",
                "supports": [],
                "notes": "",
            }
        )
    return {"summary": "完成网页证据采集。", "evidence": evidence, "gaps": []}


def _fallback_local_evidence(records: list[dict]) -> dict:
    evidence = []
    for record in records:
        evidence.append(
            {
                "source_id": record.get("source_id"),
                "doc_id": record.get("doc_id", ""),
                "title": record.get("title", "") or record.get("source_id", ""),
                "snippet": record.get("snippet", ""),
                "source_type": "local",
                "reliability_hint": "internal",
                "supports": [],
                "notes": "",
            }
        )
    return {"summary": "完成本地知识库证据采集。", "evidence": evidence, "gaps": []}


def _is_official_domain(domain: str) -> bool:
    value = domain.lower()
    return value.endswith(".gov.cn") or value.endswith(".gov") or value.endswith(".edu") or value.endswith(".edu.cn") or "gov" in value or "official" in value


def _score_evidence(record: dict) -> tuple[float, str]:
    source_type = record.get("source_type")
    if source_type == "local":
        return 0.92, "企业内部知识库证据，默认高可信"
    domain = str(record.get("domain", "")).lower()
    if _is_official_domain(domain):
        return 0.88, "官方或权威机构域名"
    if any(word in domain for word in ["news", "finance", "reuters", "bloomberg", "people", "xinhuanet"]):
        return 0.72, "主流媒体域名"
    if domain:
        return 0.58, "普通互联网来源，需要交叉验证"
    return 0.45, "来源信息不完整"


def _dedupe_sources(items: list[dict], key_fields: list[str]) -> list[dict]:
    seen = set()
    results = []
    for item in items:
        key = tuple(str(item.get(field, "")).strip() for field in key_fields)
        if key in seen:
            continue
        seen.add(key)
        results.append(item)
    return results


def _fallback_audit(state: ResearchState) -> dict:
    evidence_pool = []
    source_index = []
    audit_flags = []
    for record in state.get("web_evidence", []) + state.get("local_evidence", []):
        score, reason = _score_evidence(record)
        normalized = dict(record)
        normalized["reliability_score"] = score
        normalized["reliability_reason"] = reason
        normalized["source_label"] = record.get("title") or record.get("doc_id") or record.get("url") or record.get("source_id")
        normalized.setdefault("supports", [])
        normalized.setdefault("refutes", [])
        evidence_pool.append(normalized)
        locator = record.get("url") or record.get("doc_id") or ""
        if score < 0.6:
            audit_flags.append({"type": "low_confidence", "target": record.get("source_id"), "reason": reason})
        else:
            source_index.append(
                {
                    "source_id": record.get("source_id"),
                    "label": normalized["source_label"],
                    "locator": locator or "未提供定位信息",
                    "source_type": record.get("source_type", "source"),
                }
            )
    for hypo in state.get("hypotheses", []):
        hypo_id = hypo.get("id")
        related = [item for item in evidence_pool if hypo_id in item.get("supports", []) or hypo_id in item.get("refutes", [])]
        if not related:
            audit_flags.append({"type": "missing_evidence", "target": hypo_id, "reason": "缺少直接关联证据"})
    return {
        "summary": "完成证据评分与审计。",
        "evidence_pool": evidence_pool,
        "audit_flags": audit_flags,
        "source_index": _dedupe_sources(source_index, ["source_id"]),
    }


def _fallback_analysis(state: ResearchState) -> dict:
    source_ids = [item.get("source_id") for item in state.get("evidence_pool", [])[:3] if item.get("source_id")]
    findings = [
        {
            "claim_id": "c_1",
            "claim": f"围绕“{state['query']}”已完成多源检索，初步证据表明问题可以从网络与本地知识库双侧支撑。",
            "confidence": "medium" if source_ids else "low",
            "source_ids": source_ids,
        }
    ]
    hypothesis_status = []
    for hypo in state.get("hypotheses", []):
        hypothesis_status.append(
            {
                "id": hypo.get("id"),
                "status": "verified" if source_ids else "uncertain",
                "reason": "已有可用证据池" if source_ids else "证据不足",
                "source_ids": source_ids,
            }
        )
    return {
        "analysis_summary": "完成结论归纳与假设状态整理。",
        "hypothesis_status": hypothesis_status,
        "findings": findings,
        "claim_map": [{"claim_id": item["claim_id"], "source_ids": item["source_ids"]} for item in findings],
        "next_actions": [] if source_ids else ["补充更多高质量来源"],
    }


def _render_fallback_report(state: ResearchState) -> str:
    lines = ["# 调研结果", "", "## 执行摘要", state.get("analysis", "暂无分析结果"), ""]
    lines.append("## 任务规划与假设状态")
    for hypo in state.get("hypotheses", []):
        status = hypo.get("status", "unverified")
        lines.append(f"- {hypo.get('id', 'h')}: {hypo.get('content', '')} | 状态: {status}")
    lines.append("")
    lines.append("## 核心结论")
    for finding in state.get("findings", []):
        refs = "".join(f"[{source_id}]" for source_id in finding.get("source_ids", []))
        lines.append(f"- {finding.get('claim', '')} {refs}".rstrip())
    lines.append("")
    lines.append("## 风险与不确定性")
    if state.get("audit_flags"):
        for flag in state["audit_flags"]:
            lines.append(f"- {flag.get('type')}: {flag.get('reason')} ({flag.get('target')})")
    else:
        lines.append("- 当前未发现明显冲突。")
    lines.append("")
    lines.append("## 检索统计")
    web_stats = state.get("web_retrieval_stats", {})
    local_stats = state.get("local_retrieval_stats", {})
    if web_stats or local_stats:
        lines.append(f"- 网络检索：queries={web_stats.get('query_count', 0)} raw={web_stats.get('raw_count', 0)} kept={web_stats.get('kept_count', 0)} dropped={web_stats.get('dropped_count', 0)}")
        lines.append(f"- 本地检索：queries={local_stats.get('query_count', 0)} raw={local_stats.get('raw_count', 0)} kept={local_stats.get('kept_count', 0)} dropped={local_stats.get('dropped_count', 0)}")
    else:
        lines.append("- 未记录检索统计。")
    lines.append("")
    lines.append("## 引用列表")
    for source in state.get("source_index", []):
        source_type = source.get("source_type", "source")
        lines.append(f"- {source.get('source_id')} [{source_type}]: {source.get('label')} | {source.get('locator')}")
    return "\n".join(lines)


def _build_source_lookup(state: ResearchState) -> dict[str, dict]:
    lookup: dict[str, dict] = {}

    def _put(source_id: str, source_type: str, label: str, locator: str):
        if not source_id:
            return
        item = lookup.get(source_id)
        if not item:
            lookup[source_id] = {
                "source_id": source_id,
                "source_type": source_type or "source",
                "label": label or source_id,
                "locator": locator or "",
            }
            return
        if (not item.get("locator")) and locator:
            item["locator"] = locator
        if (not item.get("label")) and label:
            item["label"] = label
        if item.get("source_type") in {"source", ""} and source_type:
            item["source_type"] = source_type

    for source in state.get("source_index", []):
        _put(
            str(source.get("source_id", "")).strip(),
            str(source.get("source_type", "source")).strip(),
            str(source.get("label", "")).strip(),
            str(source.get("locator", "")).strip(),
        )
    for ev in state.get("evidence_pool", []):
        _put(
            str(ev.get("source_id", "")).strip(),
            str(ev.get("source_type", "source")).strip(),
            str(ev.get("title") or ev.get("source_label") or "").strip(),
            str(ev.get("url") or ev.get("doc_id") or "").strip(),
        )
    for ev in state.get("web_evidence", []):
        _put(
            str(ev.get("source_id", "")).strip(),
            "web",
            str(ev.get("title", "")).strip(),
            str(ev.get("url") or "").strip(),
        )
    for ev in state.get("local_evidence", []):
        _put(
            str(ev.get("source_id", "")).strip(),
            "local",
            str(ev.get("title") or ev.get("doc_id") or "").strip(),
            str(ev.get("doc_id") or "").strip(),
        )
    for key, item in lookup.items():
        if key.startswith("LOC"):
            item["source_type"] = "local"
        elif key.startswith("WEB"):
            item["source_type"] = "web"
    return lookup


def _extract_citation_ids(content: str) -> list[str]:
    """从正文中提取所有引用ID [XXX]"""
    pattern = r'\[([A-Z]+\d+_\d+-\d+)\]'
    matches = re.findall(pattern, content)
    return list(dict.fromkeys(matches))  # 去重保序


def _validate_and_fix_citations(content: str, valid_source_ids: set[str]) -> tuple[str, list[str]]:
    """校验正文中的引用ID，移除非法引用，返回修正后的内容和实际使用的合法引用列表"""
    pattern = r'\[([A-Z]+\d+_\d+-\d+)\]'
    
    def replace_citation(match):
        citation_id = match.group(1)
        if citation_id in valid_source_ids:
            return f"[{citation_id}]"
        else:
            # 非法引用，直接移除
            return ""
    
    fixed_content = re.sub(pattern, replace_citation, content)
    # 提取修正后实际使用的合法引用
    used_ids = [cid for cid in _extract_citation_ids(fixed_content) if cid in valid_source_ids]
    return fixed_content, used_ids


def _render_reference_list(state: ResearchState) -> str:
    lines = ["## 参考资料"]
    lookup = _build_source_lookup(state)
    
    # 1. 优先从正文 draft 中按出现顺序提取实际引用的 source_id
    draft_content = state.get("draft", "") or state.get("final", "")
    cited_ids: list[str] = []
    if draft_content:
        for sid in _extract_citation_ids(draft_content):
            if sid in lookup and sid not in cited_ids:
                cited_ids.append(sid)
    
    # 2. 如果正文无引用，降级到 findings
    if not cited_ids:
        for finding in state.get("findings", []):
            for sid in finding.get("source_ids", []):
                text = str(sid).strip()
                if text and text not in cited_ids and text in lookup:
                    cited_ids.append(text)
    
    # 3. 再降级：全量 lookup
    if not cited_ids:
        cited_ids = list(lookup.keys())
    
    # 4. 对 local 来源按 locator 去重展示（同一文件多个 chunk 只展示一次）
    seen_locators: set[str] = set()
    display_ids: list[str] = []
    web_ids: list[str] = []
    local_ids: list[str] = []
    
    for sid in cited_ids:
        source = lookup.get(sid)
        if not source:
            continue
        source_type = source.get("source_type", "")
        locator = source.get("locator", "").strip()
        
        if source_type == "local":
            # 同一文件路径只保留第一次出现的 source_id 做代表
            dedup_key = locator or sid
            if dedup_key in seen_locators:
                continue
            seen_locators.add(dedup_key)
            local_ids.append(sid)
        else:
            web_ids.append(sid)
    
    # 5. 排列顺序：WEB 在前（保持原始引用顺序），LOCAL 跟后
    display_ids = web_ids + local_ids
    
    if not display_ids:
        display_ids = cited_ids[:15]
    
    for sid in display_ids:
        source = lookup.get(sid)
        if not source:
            continue
        locator = source.get("locator", "").strip()
        label = source.get("label", "").strip()
        source_type = source.get("source_type", "source")
        source_id = source.get("source_id", sid)
        
        if not locator:
            locator = "链接暂不可用" if source_type == "web" else "本地知识库"
        
        lines.append(f"- [{source_id}] [{source_type}]: {label} | {locator}")
    
    if len(lines) == 1:
        lines.append("- 暂无参考资料")
    return "\n".join(lines)


def _render_execution_appendix(state: ResearchState) -> str:
    lines = ["## 规划与检索明细", "", "### 执行概览"]
    search_plan = state.get("search_plan", [])
    web_stats = state.get("web_retrieval_stats", {})
    local_stats = state.get("local_retrieval_stats", {})
    lines.append(f"- 规划生成研究问题数: {len(state.get('research_questions', []))}")
    lines.append(f"- 规划生成搜索步骤数: {len(search_plan)}")
    
    iteration = state.get("iteration", 0)
    lines.append(f"- 经过 {iteration + 1} 轮检索迭代")
    if state.get("needs_more_research"):
        lines.append(f"- 信息缺口: {state.get('missing_gaps', [])}")
        
    lines.append(
        f"- 实际执行网页检索问题数: {web_stats.get('query_count', 0)} | 原始命中: {web_stats.get('raw_count', 0)} | 保留证据: {web_stats.get('kept_count', 0)} | 丢弃: {web_stats.get('dropped_count', 0)}"
    )
    lines.append(
        f"- 实际执行本地检索问题数: {local_stats.get('query_count', 0)} | 原始命中: {local_stats.get('raw_count', 0)} | 保留证据: {local_stats.get('kept_count', 0)} | 丢弃: {local_stats.get('dropped_count', 0)}"
    )
    lines.append("")
    lines.append("### 问题拆解明细")
    for sq in state.get("sub_questions", []):
        lines.append(f"- {sq}")
    if not state.get("sub_questions"):
        lines.append("- 无")
    lines.append("")
    lines.append("### 规划输出")
    outline = state.get("outline", [])
    if outline:
        for section in outline:
            lines.append(
                f"- {section.get('id')}: {section.get('title')} | {section.get('description')} | search_queries={section.get('search_queries', [])}"
            )
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("### 研究问题")
    for index, question in enumerate(state.get("research_questions", []), 1):
        lines.append(f"- Q{index}: {question}")
    if not state.get("research_questions"):
        lines.append("- 无")
    lines.append("")
    lines.append("### 搜索计划")
    for index, item in enumerate(state.get("search_plan", []), 1):
        lines.append(
            f"- S{index}: section={item.get('section_id')} | query={item.get('query')} | source={item.get('source_preference')} | reason={item.get('reason')}"
        )
    if not state.get("search_plan"):
        lines.append("- 无")
    lines.append("")
    if state.get("supplementary_queries"):
        lines.append("### 补搜计划")
        for index, item in enumerate(state.get("supplementary_queries", []), 1):
            lines.append(f"- S{index} (补搜): query={item.get('query')} | reason={item.get('reason')}")
        lines.append("")
    lines.append("### 网页检索明细")
    for index, trace in enumerate(state.get("web_search_trace", []), 1):
        lines.append(
            f"- WQ{index}: section={trace.get('section_id')} | query={trace.get('query')} | reason={trace.get('reason')} | raw={trace.get('raw_count', 0)} | kept={trace.get('kept_count', 0)} | rejected={trace.get('rejected_count', 0)}"
        )
        lines.append(f"  - raw_ids={trace.get('raw_source_ids', [])}")
        lines.append(f"  - kept_ids={trace.get('kept_source_ids', [])}")
        lines.append(f"  - rejected_ids={trace.get('rejected_source_ids', [])}")
        if trace.get("reject_reason"):
            lines.append(f"  - reject_reason={trace.get('reject_reason')}")
        lines.append("  - raw_samples:")
        for item in trace.get("raw_records", [])[:3]:
            lines.append(f"    - {item.get('source_id')}: {item.get('title')} | {item.get('locator')}")
        if trace.get("kept_records"):
            lines.append("  - kept_samples:")
            for item in trace.get("kept_records", [])[:3]:
                lines.append(f"    - {item.get('source_id')}: {item.get('title')} | {item.get('locator')}")
        if trace.get("rejected_records"):
            lines.append("  - rejected_samples:")
            for item in trace.get("rejected_records", [])[:3]:
                lines.append(f"    - {item.get('source_id')}: {item.get('title')} | {item.get('locator')}")
    if not state.get("web_search_trace"):
        lines.append("- 无")
    lines.append("")
    lines.append("### 本地检索明细")
    for index, trace in enumerate(state.get("local_rag_trace", []), 1):
        lines.append(
            f"- LQ{index}: section={trace.get('section_id')} | query={trace.get('query')} | reason={trace.get('reason')} | raw={trace.get('raw_count', 0)} | kept={trace.get('kept_count', 0)} | rejected={trace.get('rejected_count', 0)}"
        )
        lines.append(f"  - raw_ids={trace.get('raw_source_ids', [])}")
        lines.append(f"  - kept_ids={trace.get('kept_source_ids', [])}")
        lines.append(f"  - rejected_ids={trace.get('rejected_source_ids', [])}")
        if trace.get("reject_reason"):
            lines.append(f"  - reject_reason={trace.get('reject_reason')}")
        lines.append("  - raw_samples:")
        for item in trace.get("raw_records", [])[:3]:
            lines.append(f"    - {item.get('source_id')}: {item.get('title')} | {item.get('locator')}")
        if trace.get("kept_records"):
            lines.append("  - kept_samples:")
            for item in trace.get("kept_records", [])[:3]:
                lines.append(f"    - {item.get('source_id')}: {item.get('title')} | {item.get('locator')}")
        if trace.get("rejected_records"):
            lines.append("  - rejected_samples:")
            for item in trace.get("rejected_records", [])[:3]:
                lines.append(f"    - {item.get('source_id')}: {item.get('title')} | {item.get('locator')}")
    if not state.get("local_rag_trace"):
        lines.append("- 无")
    return "\n".join(lines)


def _ensure_reference_section(content: str, state: ResearchState) -> str:
    base = content.rstrip()
    references = _render_reference_list(state)
    if "## 引用列表" in base or "## 来源清单" in base or "## 参考资料" in base:
        return base
    return f"{base}\n\n{references}"


def intent_node(state: ResearchState, agent, agent_name: str) -> ResearchState:
    logger.info("%s 开始 | agent=%s", colorize("[intent]", "cyan"), colorize(agent_name, "magenta"))
    rule_route = detect_intent(state["query"])
    prompt = (
        f"用户问题：{state['query']}\n"
        f"规则引擎初判：{rule_route}\n"
        "请输出 JSON：{\"route\":\"direct|multiagent\",\"reason\":\"...\"}"
    )
    payload, content, messages = _invoke_json_agent(
        state,
        prompt,
        agent,
        agent_name,
        "intent",
        {"route": rule_route, "reason": "rule"},
    )
    route = str(payload.get("route", rule_route)).strip().lower()
    if route not in {"direct", "multiagent"}:
        route = rule_route
    logger.info("%s 路由: %s", colorize("[intent]", "green"), route)
    return {"intent": route, "draft": content, "messages": messages}


def direct_answer_node(state: ResearchState, agent, agent_name: str) -> ResearchState:
    logger.info("%s 开始 | agent=%s", colorize("[direct_answer]", "cyan"), colorize(agent_name, "magenta"))
    prompt = f"用户问题：{state['query']}"
    human = HumanMessage(content=with_memory_context(state, prompt))
    result = agent.invoke({"messages": [human]})
    content = _last_content(result).strip()
    emit("direct_answer", content)
    return {
        "intent": "direct",
        "final": content,
        "draft": content,
        "analysis_summary": content,
        "needs_more_research": False,
        "messages": [human, result["messages"][-1]],
    }


def plan_node(state: ResearchState, agent, agent_name: str) -> ResearchState:
    logger.info("%s 开始 | agent=%s", colorize("[plan]", "cyan"), colorize(agent_name, "magenta"))
    log_inputs("plan", agent_name, {"query": state["query"]})
    fallback = _default_plan(state)
    payload, content, messages = _invoke_json_agent(
        state,
        f"用户需求：{state['query']}\n请先做大纲与问题拆解，再输出规划 JSON。",
        agent,
        agent_name,
        "plan",
        fallback,
    )
    outline = payload.get("outline") if isinstance(payload.get("outline"), list) else fallback["outline"]
    sub_questions = payload.get("sub_questions") if isinstance(payload.get("sub_questions"), list) else fallback["sub_questions"]
    research_questions = payload.get("research_questions") if isinstance(payload.get("research_questions"), list) else fallback["research_questions"]
    budget = payload.get("budget") if isinstance(payload.get("budget"), dict) else fallback["budget"]
    search_plan = _derive_search_plan(outline, sub_questions, research_questions, state["query"])
    plan_summary = payload.get("objective") or state["query"]
    return {
        "phase": "planning completed",
        "plan": plan_summary,
        "outline": outline,
        "sub_questions": sub_questions,
        "research_questions": research_questions,
        "search_plan": search_plan,
        "budget": budget,
        "messages": messages,
        "draft": content,
        "iteration": 0,
    }


def web_search_node(state: ResearchState, agent, agent_name: str) -> ResearchState:
    logger.info("%s 开始 | agent=%s", colorize("[web_search]", "cyan"), colorize(agent_name, "magenta"))
    queries = _build_queries(state, "web")
    logger.info("[web_search_node] 构建查询 | 查询数量=%s | queries=%s", len(queries), [q.get("query", "") for q in queries])
    
    raw_records = []
    query_traces = state.get("web_search_trace", [])
    
    iteration = state.get("iteration", 0)
    prefix = f"WEB{iteration+1}"
    logger.info("[web_search_node] 迭代信息 | iteration=%s | prefix=%s", iteration, prefix)
    
    for query_index, item in enumerate(queries, 1):
        query_text = str(item.get("query", ""))
        logger.info("[web_search_node] 执行第 %s/%s 个查询 | query=%s | section_id=%s", query_index, len(queries), query_text, item.get("section_id"))
        # 优化点：减少单词请求返回的数量，从 count=6 降至 count=4，大幅减少无用 Token 消耗
        records = bocha_web_search_records(query_text, count=4)
        logger.info("[web_search_node] 查询 %s 返回 | 记录数=%s", query_index, len(records))
        records = _assign_source_ids(records, f"{prefix}_{query_index}")
        for record in records:
            record["section_id"] = item.get("section_id")
            record["search_query"] = item.get("query")
        raw_records.extend(records)
        query_traces.append(
            {
                "iteration": iteration,
                "plan_step": query_index,
                "query": str(item.get("query", "")),
                "section_id": item.get("section_id"),
                "reason": item.get("reason", ""),
                "source_preference": item.get("source_preference", "web"),
                "raw_count": len(records),
                "raw_records": _summarize_records(records),
            }
        )
    raw_records = _dedupe_sources(raw_records, ["url", "title"])
    raw_records = _minimal_record_filter(raw_records, ["title", "snippet", "url"])
    logger.info("[web_search_node] 数据清洗后 | 去重过滤后记录数=%s", len(raw_records))
    
    web_retrieval_stats = state.get("web_retrieval_stats", {})
    web_retrieval_stats["query_count"] = web_retrieval_stats.get("query_count", 0) + len(queries)
    web_retrieval_stats["raw_count"] = web_retrieval_stats.get("raw_count", 0) + len(raw_records)
    
    log_inputs("web_search", agent_name, {"query_count": str(len(queries)), "raw_count": str(len(raw_records))})
    if not raw_records:
        logger.warning("[web_search_node] 无可用网页证据，跳过网页上下文注入 | 查询数=%s", len(queries))
        logger.info("%s 无可用网页证据，跳过网页上下文注入", colorize("[web_search]", "yellow"))
        return {
            "web_search": "未检索到可用网页证据，已跳过网页上下文注入。",
            "web_evidence": state.get("web_evidence", []),
            "web_retrieval_stats": web_retrieval_stats,
            "web_search_trace": query_traces,
        }
    logger.info("[web_search_node] 调用 LLM 整理证据 | raw_records=%s", len(raw_records))
    fallback = _fallback_web_evidence(raw_records)
    payload, content, messages = _invoke_json_agent(
        state,
        "请基于以下网页证据整理结构化 JSON。\n"
        f"原问题：{state['query']}\n"
        f"子问题：{json.dumps(state.get('sub_questions', []), ensure_ascii=False)}\n"
        f"原始网页证据：\n{_format_raw_records(raw_records, 'web')}",
        agent,
        agent_name,
        "web_search",
        fallback,
    )
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), list) else fallback["evidence"]
    logger.info("[web_search_node] LLM 返回证据 | evidence数量=%s", len(evidence))
    allowed_source_ids = {str(item.get("source_id")) for item in raw_records if item.get("source_id")}
    evidence = _prune_evidence_to_allowed_sources(evidence, allowed_source_ids)
    # 从原始记录补充 LLM 可能丢失的 url/domain/title 字段
    evidence = _enrich_evidence_from_raw(evidence, raw_records)
    
    web_retrieval_stats["kept_count"] = web_retrieval_stats.get("kept_count", 0) + len(evidence)
    web_retrieval_stats["dropped_count"] = web_retrieval_stats.get("dropped_count", 0) + max(len(raw_records) - len(evidence), 0)
    
    kept_ids = {str(item.get("source_id")) for item in evidence if item.get("source_id")}
    query_traces = _finalize_query_traces(
        query_traces,
        kept_ids,
        payload.get("rejected_source_ids", []),
        str(payload.get("reject_reason", "")).strip(),
    )
    
    existing_evidence = state.get("web_evidence", [])
    logger.info("[web_search_node] 节点完成 | 新增证据=%s | 累计证据=%s", len(evidence), len(existing_evidence) + len(evidence))
    return {
        "web_search": payload.get("summary", content),
        "web_evidence": existing_evidence + evidence,
        "web_retrieval_stats": web_retrieval_stats,
        "web_search_trace": query_traces,
        "messages": messages,
    }


def local_rag_node(state: ResearchState, agent, agent_name: str) -> ResearchState:
    logger.info("%s 开始 | agent=%s", colorize("[local_rag]", "cyan"), colorize(agent_name, "magenta"))
    queries = _build_queries(state, "local")
    raw_records = []
    query_traces = state.get("local_rag_trace", [])
    
    iteration = state.get("iteration", 0)
    prefix = f"LOC{iteration+1}"
    
    for query_index, item in enumerate(queries, 1):
        records = search_knowledge_base_records(str(item.get("query", "")), limit=4)
        records = _assign_source_ids(records, f"{prefix}_{query_index}")
        for record in records:
            record["section_id"] = item.get("section_id")
            record["search_query"] = item.get("query")
        raw_records.extend(records)
        query_traces.append(
            {
                "iteration": iteration,
                "plan_step": query_index,
                "query": str(item.get("query", "")),
                "section_id": item.get("section_id"),
                "reason": item.get("reason", ""),
                "source_preference": item.get("source_preference", "local"),
                "raw_count": len(records),
                "raw_records": _summarize_records(records),
            }
        )
    raw_records = _dedupe_sources(raw_records, ["doc_id", "snippet"])
    raw_records = _minimal_record_filter(raw_records, ["snippet", "title", "doc_id"])
    
    local_retrieval_stats = state.get("local_retrieval_stats", {})
    local_retrieval_stats["query_count"] = local_retrieval_stats.get("query_count", 0) + len(queries)
    local_retrieval_stats["raw_count"] = local_retrieval_stats.get("raw_count", 0) + len(raw_records)
    
    log_inputs("local_rag", agent_name, {"query_count": str(len(queries)), "raw_count": str(len(raw_records))})
    if not raw_records:
        logger.info("%s 无可用本地证据，跳过本地上下文注入", colorize("[local_rag]", "yellow"))
        return {
            "local_rag": "未检索到可用本地知识库证据，已跳过本地上下文注入。",
            "local_evidence": state.get("local_evidence", []),
            "local_retrieval_stats": local_retrieval_stats,
            "local_rag_trace": query_traces,
        }
    fallback = _fallback_local_evidence(raw_records)
    payload, content, messages = _invoke_json_agent(
        state,
        "请基于以下知识库证据整理结构化 JSON。\n"
        f"原问题：{state['query']}\n"
        f"子问题：{json.dumps(state.get('sub_questions', []), ensure_ascii=False)}\n"
        f"原始知识库证据：\n{_format_raw_records(raw_records, 'local')}",
        agent,
        agent_name,
        "local_rag",
        fallback,
    )
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), list) else fallback["evidence"]
    allowed_source_ids = {str(item.get("source_id")) for item in raw_records if item.get("source_id")}
    evidence = _prune_evidence_to_allowed_sources(evidence, allowed_source_ids)
    
    local_retrieval_stats["kept_count"] = local_retrieval_stats.get("kept_count", 0) + len(evidence)
    local_retrieval_stats["dropped_count"] = local_retrieval_stats.get("dropped_count", 0) + max(len(raw_records) - len(evidence), 0)
    
    kept_ids = {str(item.get("source_id")) for item in evidence if item.get("source_id")}
    query_traces = _finalize_query_traces(
        query_traces,
        kept_ids,
        payload.get("rejected_source_ids", []),
        str(payload.get("reject_reason", "")).strip(),
    )
    
    existing_evidence = state.get("local_evidence", [])
    return {
        "local_rag": payload.get("summary", content),
        "local_evidence": existing_evidence + evidence,
        "local_retrieval_stats": local_retrieval_stats,
        "local_rag_trace": query_traces,
        "messages": messages,
    }


def deep_dive_node(state: ResearchState, agent, agent_name: str) -> ResearchState:
    logger.info("%s 开始 | agent=%s", colorize("[deep_dive]", "cyan"), colorize(agent_name, "magenta"))
    if not state.get("web_evidence") and not state.get("local_evidence"):
        logger.info("%s 等待检索结果", colorize("[deep_dive]", "yellow"))
        return {}
    fallback = _fallback_audit(state)
    payload, content, messages = _invoke_json_agent(
        state,
        "请对 web 与 local 证据进行评分、去重、冲突审计，并只输出 JSON。\n"
        f"问题：{state['query']}\n"
        f"子问题：{json.dumps(state.get('sub_questions', []), ensure_ascii=False)}\n"
        f"web_evidence：{json.dumps(state.get('web_evidence', []), ensure_ascii=False)}\n"
        f"local_evidence：{json.dumps(state.get('local_evidence', []), ensure_ascii=False)}",
        agent,
        agent_name,
        "deep_dive",
        fallback,
    )
    payload_pool = payload.get("evidence_pool") if isinstance(payload.get("evidence_pool"), list) else []
    raw_evidence = state.get("web_evidence", []) + state.get("local_evidence", [])
    allowed_source_ids = {str(item.get("source_id", "")).strip() for item in raw_evidence if item.get("source_id")}
    evidence_pool = []
    for item in payload_pool:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("source_id", "")).strip()
        if sid and sid in allowed_source_ids:
            evidence_pool.append(item)
    if not evidence_pool:
        evidence_pool = fallback["evidence_pool"]
    existing_ids = {str(item.get("source_id", "")).strip() for item in evidence_pool if isinstance(item, dict)}
    for record in raw_evidence:
        sid = str(record.get("source_id", "")).strip()
        if not sid or sid in existing_ids:
            continue
        score, reason = _score_evidence(record)
        evidence_pool.append(
            {
                "source_id": sid,
                "source_type": record.get("source_type", "source"),
                "title": record.get("title") or sid,
                "url": record.get("url", ""),
                "doc_id": record.get("doc_id", ""),
                "snippet": record.get("snippet", ""),
                "supports_questions": record.get("supports_questions", []),
                "reliability_score": score,
                "reliability_reason": reason,
                "source_label": record.get("title") or record.get("doc_id") or record.get("url") or sid,
            }
        )
        existing_ids.add(sid)
    audit_flags = payload.get("audit_flags") if isinstance(payload.get("audit_flags"), list) else fallback["audit_flags"]
    source_index = []
    for item in evidence_pool:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("source_id", "")).strip()
        if not sid:
            continue
        source_index.append(
            {
                "source_id": sid,
                "label": item.get("title") or item.get("source_label") or sid,
                "locator": item.get("url") or item.get("doc_id") or "",
                "source_type": item.get("source_type", "source"),
            }
        )
    source_index = _dedupe_sources(source_index, ["source_id"])
    return {
        "deep_dive": payload.get("summary", content),
        "audit": payload.get("summary", content),
        "evidence_pool": evidence_pool,
        "audit_flags": audit_flags,
        "source_index": source_index,
        "messages": messages,
    }


def _fallback_analysis(state: ResearchState) -> dict:
    return {
        "analysis_summary": "默认分析结论",
        "needs_more_research": False,
        "missing_gaps": [],
        "findings": [],
        "claim_map": [],
        "next_actions": [],
    }

def analyze_node(state: ResearchState, agent, agent_name: str) -> ResearchState:
    logger.info("%s 开始 | agent=%s", colorize("[analyze]", "cyan"), colorize(agent_name, "magenta"))
    fallback = _fallback_analysis(state)
    payload, content, messages = _invoke_json_agent(
        state,
        "请基于证据池输出结论映射 JSON，并评估证据完备性：\n"
        f"原问题：{state['query']}\n"
        f"子问题：{json.dumps(state.get('sub_questions', []), ensure_ascii=False)}\n"
        f"证据池：{json.dumps(state.get('evidence_pool', []), ensure_ascii=False)}\n"
        f"审计标记：{json.dumps(state.get('audit_flags', []), ensure_ascii=False)}",
        agent,
        agent_name,
        "analyze",
        fallback,
    )
    findings = payload.get("findings") if isinstance(payload.get("findings"), list) else fallback["findings"]
    claim_map = payload.get("claim_map") if isinstance(payload.get("claim_map"), list) else fallback["claim_map"]
    needs_more_research = payload.get("needs_more_research", False)
    missing_gaps = payload.get("missing_gaps", [])
    analysis_summary = payload.get("analysis_summary", content)
    return {
        "analysis": analysis_summary,
        "findings": findings,
        "claim_map": claim_map,
        "needs_more_research": needs_more_research,
        "missing_gaps": missing_gaps,
        "messages": messages,
    }

def reflect_node(state: ResearchState, agent, agent_name: str) -> ResearchState:
    logger.info("%s 开始 | agent=%s", colorize("[reflect]", "cyan"), colorize(agent_name, "magenta"))
    
    missing_gaps = state.get("missing_gaps", [])
    log_inputs("reflect", agent_name, {"missing_gaps": str(missing_gaps)})
    
    fallback = {
        "reflection_summary": "默认补搜",
        "supplementary_queries": [{"section_id": "gap_1", "query": state["query"], "source_preference": "hybrid", "reason": "fallback"}]
    }
    
    prompt = (
        f"分析师指出当前证据不足以完全回答问题，存在以下信息缺口：\n{json.dumps(missing_gaps, ensure_ascii=False)}\n\n"
        f"原问题：{state['query']}\n"
        f"子问题：{json.dumps(state.get('sub_questions', []), ensure_ascii=False)}\n"
        f"已执行过的搜索计划：\n{json.dumps(state.get('search_plan', []), ensure_ascii=False)}\n"
        f"已执行过的补搜计划：\n{json.dumps(state.get('supplementary_queries', []), ensure_ascii=False)}\n\n"
        "请生成新的补搜计划以填补缺口。"
    )
    
    payload, content, messages = _invoke_json_agent(
        state,
        prompt,
        agent,
        agent_name,
        "reflect",
        fallback,
    )
    
    return {
        "iteration": state.get("iteration", 0) + 1,
        "supplementary_queries": payload.get("supplementary_queries", fallback["supplementary_queries"]),
        "messages": messages,
    }

def write_node(state: ResearchState, agent, agent_name: str) -> ResearchState:
    logger.info("%s 开始 | agent=%s", colorize("[write]", "cyan"), colorize(agent_name, "magenta"))
    valid_source_ids = [str(item.get("source_id", "")).strip() for item in state.get("source_index", []) if item.get("source_id")]
    valid_source_ids = [item for item in valid_source_ids if item][:80]
    valid_source_ids_set = set(valid_source_ids)
    
    prompt = (
        "请严格根据以下信息撰写最终的 Markdown 研报。请直接输出正文，绝对不要输出任何 JSON 结构，也不要复述你的指令。\n\n"
        f"核心问题：{state['query']}\n"
        f"子问题拆解：{json.dumps(state.get('sub_questions', []), ensure_ascii=False)}\n\n"
        "【分析结论 (Findings)】：\n"
        f"{json.dumps(state.get('findings', []), ensure_ascii=False)}\n\n"
        "【可用来源索引 (source_index)】：\n"
        f"{json.dumps(state.get('source_index', []), ensure_ascii=False)}\n\n"
        "【合法引用ID列表】：\n"
        f"{json.dumps(valid_source_ids, ensure_ascii=False)}\n\n"
        "【可能存在的风险/冲突 (Audit Flags)】：\n"
        f"{json.dumps(state.get('audit_flags', []), ensure_ascii=False)}\n\n"
        "要求：正文必须使用合法引用ID（例如 [WEB1_1-1]、[LOC1_1-3]）；禁止使用不存在的编号。"
        "结尾不需要你来列举引用列表，系统会自动拼接。"
    )
    human = HumanMessage(content=with_memory_context(state, prompt))
    
    # 彻底断开之前的 messages 累积，只给模型当前这一条指令，避免被前面的 JSON 带偏
    result = agent.invoke({"messages": [human]})
    content = _last_content(result)
    
    # 强制清理可能的错误 JSON 代码块
    content = re.sub(r"^```json\s*", "", content)
    content = re.sub(r"^```markdown\s*", "", content)
    content = re.sub(r"^```\s*", "", content)
    content = re.sub(r"```$", "", content.strip())
    
    # 校验并修正引用ID，移除非法引用
    content, used_citation_ids = _validate_and_fix_citations(content, valid_source_ids_set)
    
    final_content = _ensure_reference_section(content, state)
    emit("write", final_content)
    return {"draft": final_content, "final": final_content, "messages": [human, result["messages"][-1]]}
