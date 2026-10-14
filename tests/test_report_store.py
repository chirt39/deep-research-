"""报告历史存储的读写测试。"""


def test_report_store_roundtrip(tmp_path):
    from app.backend.report_store import ReportStore

    store = ReportStore(tmp_path / "reports.jsonl")
    report_id = store.save(
        {
            "query": "比亚迪估值分析",
            "thread_id": "t1",
            "user_id": "u1",
            "tenant_id": "default_tenant",
            "final": "## 投资摘要\n测试报告",
            "usage": {"calls": 3, "cost_yuan": 0.01},
            "quality": {"score": 80},
        }
    )

    listed = store.list_reports()
    assert listed and listed[0]["id"] == report_id
    assert listed[0]["query"] == "比亚迪估值分析"
    assert "final" not in listed[0]  # 列表不含正文

    detail = store.get_report(report_id)
    assert detail is not None
    assert detail["final"] == "## 投资摘要\n测试报告"
    assert detail["usage"]["calls"] == 3

    assert store.get_report("missing-id") is None


def test_report_store_limit_and_order(tmp_path):
    from app.backend.report_store import ReportStore

    store = ReportStore(tmp_path / "reports.jsonl")
    for index in range(5):
        store.save({"query": f"query-{index}", "final": "x"})

    listed = store.list_reports(limit=2)
    assert [item["query"] for item in listed] == ["query-4", "query-3"]
