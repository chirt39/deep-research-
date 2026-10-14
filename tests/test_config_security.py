"""配置回退与安全限流器的单元测试（轻量依赖，无需网络）。"""

from pathlib import Path

import pytest


def test_config_env_only_defaults(monkeypatch):
    from app.mult_agents.config import AppConfig

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.delenv("MAX_ITERATIONS", raising=False)
    monkeypatch.delenv("ENABLE_MEMORY", raising=False)
    monkeypatch.delenv("ENABLE_MILVUS", raising=False)
    monkeypatch.delenv("CHECKPOINTER_BACKEND", raising=False)
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)

    cfg = AppConfig.from_env()
    assert cfg.api_key == "sk-test"
    assert cfg.max_iterations == 2
    assert cfg.enable_memory is False
    assert cfg.enable_milvus is False
    assert cfg.checkpointer_backend == "memory"
    assert cfg.embedding_provider == "huggingface"
    assert cfg.embedding_model == "BAAI/bge-small-zh-v1.5"


def test_config_load_falls_back_to_env(monkeypatch):
    from app.mult_agents.config import AppConfig

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.delenv("MAX_ITERATIONS", raising=False)
    monkeypatch.delenv("ENABLE_MEMORY", raising=False)
    monkeypatch.delenv("ENABLE_MILVUS", raising=False)
    monkeypatch.delenv("CHECKPOINTER_BACKEND", raising=False)
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    real_default = AppConfig._default_config_path()
    if real_default.exists():
        monkeypatch.setattr(
            AppConfig,
            "_default_config_path",
            staticmethod(lambda: real_default.with_name("config.nonexistent.json")),
        )
    cfg = AppConfig.load(None)
    assert cfg.api_key == "sk-test"
    assert cfg.max_iterations == 2


def test_config_load_raises_for_missing_explicit_path(monkeypatch):
    from app.mult_agents.config import AppConfig

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    missing = Path(__file__).resolve().parent / "does-not-exist.json"
    with pytest.raises(FileNotFoundError):
        AppConfig.load(missing)


def test_rate_limiter_window():
    from app.backend.security import SlidingWindowRateLimiter

    limiter = SlidingWindowRateLimiter(limit=3, window_seconds=60)
    assert limiter.allow("client-a") is True
    assert limiter.allow("client-a") is True
    assert limiter.allow("client-a") is True
    assert limiter.allow("client-a") is False
    assert limiter.allow("client-b") is True


def test_auth_token_uses_documented_env_name(monkeypatch):
    from app.backend.config import AppSettings

    monkeypatch.setenv("AUTH_TOKEN", "test-token")
    assert AppSettings().api_token == "test-token"


def test_rate_limiter_disabled_when_zero():
    from app.backend.security import SlidingWindowRateLimiter

    limiter = SlidingWindowRateLimiter(limit=0)
    for _ in range(100):
        assert limiter.allow("any") is True


def test_backend_app_imports():
    """冒烟测试：FastAPI 应用（含鉴权/限流依赖）可正常导入构建。"""
    from app.app_main import app

    assert app.title == "DeepResearch Multi-Agent Assistant"
    paths = app.openapi()["paths"]
    assert "/api/v1/research/run" in paths
    assert "/api/v1/research/stream" in paths
    assert "/api/v1/research/history" in paths
    assert "/health" in paths
