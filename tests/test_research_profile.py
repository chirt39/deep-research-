from app.backend.schemas.research import ResearchRequest
from app.mult_agents.research_profile import resolve_research_domain, source_summary


def test_domain_auto_detects_general_research():
    assert resolve_research_domain("auto", "比较两个开源 RAG 框架的部署方式") == "general"
    assert resolve_research_domain("auto", "分析比亚迪估值和现金流") == "finance"


def test_request_exposes_research_domain():
    request = ResearchRequest(query="比较 FastAPI 和 Flask", research_domain="general")
    assert request.research_domain == "general"


def test_source_summary_is_stable():
    summary = source_summary(
        [{"source_type": "web", "reliability_score": 0.9}, {"source_type": "local", "reliability_score": 0.7}],
        [{"source_id": "WEB-1"}, {"source_id": "LOC-1"}],
    )
    assert summary == {
        "evidence_count": 2,
        "source_count": 2,
        "source_types": ["local", "web"],
        "avg_reliability": 0.8,
        "high_confidence_count": 1,
    }
