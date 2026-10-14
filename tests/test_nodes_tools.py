"""节点与数据工具的纯函数测试（不访问网络、不调用 LLM）。"""

import pytest

pytest.importorskip("pymilvus")  # nodes/tools 依赖 Milvus 相关包，缺失时整模块跳过

from app.mult_agents.nodes import (  # noqa: E402
    _extract_citation_ids,
    _extract_json_block,
    _is_bad_web_domain,
    _is_greeting_query,
    _is_official_domain,
    _load_json,
    _score_evidence,
    _validate_and_fix_citations,
    detect_intent,
)
from app.mult_agents.tools import (  # noqa: E402
    _detect_stock_code,
    _detect_stock_code_from_name,
    _extract_domain,
    _detect_hk_code,
    _detect_us_ticker,
    _normalize_stock_code,
    _parse_pct,
)


def test_detect_intent_routes():
    assert detect_intent("你好") == "direct"
    assert detect_intent("你是谁") == "direct"
    assert detect_intent("比亚迪 002594 估值分析") == "multiagent"
    assert detect_intent("帮我调研一下 openclaw 的最新使用趋势") == "multiagent"
    assert detect_intent("2026 年新能源汽车行业趋势分析") == "multiagent"


def test_greeting_query():
    assert _is_greeting_query("你好") is True
    assert _is_greeting_query("Hello") is True
    assert _is_greeting_query("谢谢你的帮助") is True
    assert _is_greeting_query("比亚迪 002594 估值分析") is False
    assert _is_greeting_query("") is False
    assert _is_greeting_query("帮我分析一下新能源汽车板块趋势，顺便对比宁德时代和比亚迪") is False


def test_detect_stock_code_context():
    assert _detect_stock_code("比亚迪（002594）估值") == "sz002594"
    assert _detect_stock_code("请分析宁德时代 300750") == "sz300750"
    assert _detect_stock_code("分析一下新能源汽车行业") is None


def test_detect_stock_code_from_name():
    assert _detect_stock_code_from_name("分析一下比亚迪") == "sz002594"
    assert _detect_stock_code_from_name("宁德时代怎么样") == "sz300750"
    assert _detect_stock_code_from_name("帮我看看贵州茅台的估值") == "sh600519"
    assert _detect_stock_code_from_name("分析一下新能源汽车行业") is None


def test_detect_hk_code():
    assert _detect_hk_code("港股 腾讯控股") == "00700"
    assert _detect_hk_code("美团 03690") == "03690"
    assert _detect_hk_code("分析一下小米集团") == "01810"
    assert _detect_hk_code("分析一下新能源汽车行业") is None


def test_detect_us_ticker():
    assert _detect_us_ticker("美股 特斯拉") == "TSLA"
    assert _detect_us_ticker("美股 AAPL 怎么样") == "AAPL"
    assert _detect_us_ticker("分析一下英伟达") == "NVDA"
    assert _detect_us_ticker("分析一下新能源汽车行业") is None


def test_search_plan_prefers_outline_queries():
    from app.mult_agents.nodes import _derive_search_plan

    outline = [{"id": "sec_1", "title": "估值", "search_queries": ["比亚迪 002594 机构评级"]}]
    plan = _derive_search_plan(outline, ["宏观-测试"], [], "比亚迪 002594 估值分析")
    assert plan[0]["query"] == "比亚迪 002594 机构评级"
    assert len(plan) <= 4


def test_extract_json_block():
    assert _extract_json_block('```json\n{"a":1}\n```') == '{"a":1}'
    assert _extract_json_block('prefix {"a": 1} suffix') == '{"a": 1}'


def test_load_json_fallback():
    assert _load_json("这不是 JSON", {"fallback": True}) == {"fallback": True}
    assert _load_json('{"route": "direct"}', {}) == {"route": "direct"}


def test_normalize_stock_code():
    assert _normalize_stock_code("002594") == "sz002594"
    assert _normalize_stock_code("600519") == "sh600519"
    assert _normalize_stock_code("sz000001") == "sz000001"
    assert _normalize_stock_code("000001") == "sz000001"


def test_parse_pct():
    assert _parse_pct("55.38%") == 55.38
    assert _parse_pct("-11.82%") == -11.82
    assert _parse_pct("40.85亿") == 4085000000.0
    assert _parse_pct("1502.25万") == 15022500.0
    assert _parse_pct("") == 0.0
    assert _parse_pct("None") == 0.0


def test_extract_domain():
    assert _extract_domain("https://www.baidu.com/a/b") == "www.baidu.com"
    assert _extract_domain("") == ""


def test_domain_heuristics():
    assert _is_bad_web_domain("www.doc88.com")
    assert not _is_bad_web_domain("www.sse.com.cn")
    assert _is_official_domain("www.pbc.gov.cn")
    assert not _is_official_domain("www.sina.com.cn")


def test_score_evidence():
    assert _score_evidence({"source_type": "local"})[0] == 0.92
    assert _score_evidence({"source_type": "web", "domain": "www.pbc.gov.cn"})[0] == 0.88
    assert _score_evidence({"source_type": "web", "domain": "finance.sina.com.cn"})[0] == 0.72
    assert _score_evidence({"source_type": "web", "domain": "blog.example.com"})[0] == 0.58
    assert _score_evidence({"source_type": "web", "domain": ""})[0] == 0.45


def test_citation_validation():
    valid = {"WEB1_1-1", "LOC1_1-3"}
    content = "结论一[WEB1_1-1]来自网络，结论二[WEB9_9-9]是编造的。"
    fixed, used = _validate_and_fix_citations(content, valid)
    assert "[WEB1_1-1]" in fixed
    assert "WEB9_9-9" not in fixed
    assert used == ["WEB1_1-1"]
    assert _extract_citation_ids(fixed) == ["WEB1_1-1"]
