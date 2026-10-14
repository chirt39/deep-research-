"""token / 成本估算工具测试。"""


def test_estimate_tokens_basic():
    from app.mult_agents.usage import estimate_tokens

    assert estimate_tokens("") == 0
    assert estimate_tokens("你好") == 2  # 2 字 × 0.7 → ceil(1.4)
    assert estimate_tokens("hello world") == 3  # 11 字符 × 0.25 → ceil(2.75)


def test_estimate_cost_and_aggregate(monkeypatch):
    from app.mult_agents.usage import aggregate_usage, estimate_cost

    monkeypatch.setenv("DEEPSEEK_INPUT_PRICE_PER_M", "1")
    monkeypatch.setenv("DEEPSEEK_OUTPUT_PRICE_PER_M", "2")
    assert estimate_cost(1_000_000, 0) == 1.0
    assert estimate_cost(0, 500_000) == 1.0

    agg = aggregate_usage(
        [
            {"input_tokens": 100, "output_tokens": 50, "cost_yuan": 0.0002, "elapsed_seconds": 1.2},
            {"input_tokens": 200, "output_tokens": 100, "cost_yuan": 0.0004, "elapsed_seconds": 2.3},
        ]
    )
    assert agg["calls"] == 2
    assert agg["input_tokens"] == 300
    assert agg["output_tokens"] == 150
    assert agg["cost_yuan"] == 0.0006
    assert agg["elapsed_seconds"] == 3.5


def test_aggregate_empty():
    from app.mult_agents.usage import aggregate_usage

    agg = aggregate_usage([])
    assert agg["calls"] == 0
    assert agg["cost_yuan"] == 0.0
