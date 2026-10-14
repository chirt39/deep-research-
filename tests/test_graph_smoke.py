"""Graph 级冒烟测试：mock 掉 LLM 与搜索，验证整条工作流。

覆盖：多智能体全链路、补搜循环终止、直接回答路径、用量统计与质量自检。
"""

import json

import pytest

pytest.importorskip("pymilvus")
pytest.importorskip("langgraph")

from langchain_core.messages import AIMessage  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

from app.mult_agents import nodes  # noqa: E402
from app.mult_agents.graph import build_app  # noqa: E402
from app.mult_agents.main import AgentBundle  # noqa: E402
from app.mult_agents.state import create_initial_state  # noqa: E402


class FakeAgent:
    def __init__(self, response: str):
        self.response = response
        self.calls = 0

    def invoke(self, payload):
        self.calls += 1
        return {"messages": [AIMessage(content=self.response)]}


PLAN_JSON = json.dumps(
    {
        "objective": "测试目标",
        "sub_questions": ["宏观-测试", "公司-测试"],
        "outline": [
            {
                "id": "sec_1",
                "title": "投资摘要",
                "section_type": "summary",
                "priority": 1,
                "search_queries": ["比亚迪 002594 估值"],
                "status": "pending",
            }
        ],
        "research_questions": ["比亚迪 002594 估值"],
        "budget": {"max_rounds": 2, "max_sources": 8, "max_tokens": 12000, "max_seconds": 45},
    }
)

ANALYST_DONE_JSON = json.dumps(
    {
        "analysis_summary": "比亚迪估值合理",
        "needs_more_research": False,
        "missing_gaps": [],
        "findings": [
            {
                "claim_id": "c_1",
                "dimension": "company",
                "claim": "比亚迪当前 PE 约 25 倍",
                "confidence": "medium",
                "source_ids": ["WEB1_1-1"],
            }
        ],
        "claim_map": [{"claim_id": "c_1", "source_ids": ["WEB1_1-1"]}],
        "next_actions": [],
    }
)

ANALYST_GAP_JSON = json.dumps(
    {
        "analysis_summary": "机构评级数据缺失",
        "needs_more_research": True,
        "missing_gaps": ["机构评级"],
        "findings": [],
        "claim_map": [],
        "next_actions": [],
    }
)

REFLECT_JSON = json.dumps(
    {
        "reflection_summary": "补搜机构评级",
        "supplementary_queries": [
            {
                "section_id": "gap_1",
                "query": "比亚迪 002594 机构评级",
                "source_preference": "hybrid",
                "reason": "补齐评级数据",
            }
        ],
    }
)

JUDGE_JSON = json.dumps(
    {
        "score": 85,
        "summary": "数据密度和结构都不错，风险提示到位",
        "issues": ["可补充经营现金流分析"],
    }
)

WRITER_TEXT = (
    "## 投资摘要\n比亚迪当前 PE 25x，详见 [WEB1_1-1]。\n\n"
    "## 宏观环境分析\n略。\n\n"
    "## 行业竞争格局\n略。\n\n"
    "## 公司深度分析\n略。\n\n"
    "## 估值分析\n略。\n\n"
    "## 风险提示\n略。"
)

WEB_RECORD = {
    "title": "比亚迪估值分析",
    "url": "https://finance.sina.com.cn/byd",
    "snippet": "比亚迪 002594 当前 PE 25 倍，处于行业合理区间",
    "domain": "finance.sina.com.cn",
    "source_type": "web",
}


def _build_bundle(writer, analyst, direct, reflect=None, judge=None):
    return AgentBundle(
        intent_router=FakeAgent("{}"),
        planner=FakeAgent(PLAN_JSON),
        scout_web=FakeAgent("{}"),
        scout_local=FakeAgent("{}"),
        evidence_judge=FakeAgent("{}"),
        analyst=analyst,
        reflect_planner=reflect or FakeAgent(REFLECT_JSON),
        direct_responder=direct,
        writer=writer,
        judge=judge or FakeAgent(JUDGE_JSON),
    )


def _patch_tools(monkeypatch, records=None):
    records = records or [dict(WEB_RECORD)]
    def fake_search(query, count=8):
        # 只让大纲定向查询返回结果，保证证据来源 id 确定（WEB1_1-1）
        if query == "比亚迪 002594 估值":
            return [dict(r) for r in records]
        return []

    monkeypatch.setattr(nodes, "bocha_web_search_records", fake_search)
    monkeypatch.setattr(nodes, "collect_finance_data_records", lambda query, context="": [])
    monkeypatch.setattr(nodes, "search_knowledge_base_records", lambda query, limit=5: [])


def _run(bundle, query, max_iterations=2):
    app = build_app(bundle, InMemorySaver())
    state = create_initial_state(
        query=query, max_iterations=max_iterations, user_id="user_1", tenant_id="tenant_1"
    )
    return app.invoke(state, {"configurable": {"thread_id": "smoke"}})


def test_multiagent_full_flow(monkeypatch):
    _patch_tools(monkeypatch)
    writer = FakeAgent(WRITER_TEXT)
    bundle = _build_bundle(
        writer=writer,
        analyst=FakeAgent(ANALYST_DONE_JSON),
        direct=FakeAgent("你好"),
    )
    result = _run(bundle, "比亚迪 002594 估值分析")

    assert result["intent"] == "multiagent"
    assert "## 投资摘要" in result["final"]
    assert "[WEB1_1-1]" in result["final"]
    assert "## 参考资料" in result["final"]
    assert "生成时间：" in result["final"]
    assert result["source_index"]
    assert writer.calls == 1
    assert len(result["usage_log"]) >= 3  # plan / analyze / write
    assert result["quality_report"]["score"] > 0


def test_research_loop_terminates(monkeypatch):
    _patch_tools(monkeypatch)
    reflect = FakeAgent(REFLECT_JSON)
    bundle = _build_bundle(
        writer=FakeAgent(WRITER_TEXT),
        analyst=FakeAgent(ANALYST_GAP_JSON),  # 永远报告证据不足
        direct=FakeAgent("hi"),
        reflect=reflect,
    )
    result = _run(bundle, "比亚迪 002594 估值分析", max_iterations=1)

    assert result["iteration"] == 1
    assert reflect.calls == 1
    assert "## 投资摘要" in result["final"]


def test_direct_answer_path(monkeypatch):
    _patch_tools(monkeypatch)
    direct = FakeAgent("你好！我是 DeepResearch 金融投研助手。")
    bundle = _build_bundle(
        writer=FakeAgent(WRITER_TEXT),
        analyst=FakeAgent(ANALYST_DONE_JSON),
        direct=direct,
    )
    result = _run(bundle, "你好")

    assert result["intent"] == "direct"
    assert "你好！" in result["final"]
    assert bundle.planner.calls == 0  # 不走多智能体链路
    assert len(result["usage_log"]) == 1  # 仅 direct_answer 一次 LLM 调用


def test_route_after_write(monkeypatch):
    from app.mult_agents.graph import route_after_write

    monkeypatch.delenv("LLM_AS_JUDGE", raising=False)
    assert route_after_write({}) == "end"
    monkeypatch.setenv("LLM_AS_JUDGE", "true")
    assert route_after_write({}) == "judge"


def test_llm_judge_enabled(monkeypatch):
    _patch_tools(monkeypatch)
    monkeypatch.setenv("LLM_AS_JUDGE", "true")
    judge = FakeAgent(JUDGE_JSON)
    bundle = _build_bundle(
        writer=FakeAgent(WRITER_TEXT),
        analyst=FakeAgent(ANALYST_DONE_JSON),
        direct=FakeAgent("hi"),
        judge=judge,
    )
    result = _run(bundle, "比亚迪 002594 估值分析")

    assert judge.calls == 1
    assert result["quality_report"]["llm_score"] == 85
    assert result["quality_report"]["llm_issues"]
    # judge 调用计入用量
    assert any(item.get("node") == "judge" for item in result["usage_log"])
