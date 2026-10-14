from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    app_name: str = "DeepResearch Multi-Agent Assistant"
    app_env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    cors_allow_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    config_path: str = str(Path(__file__).resolve().parents[3] / "config.json")
    # 安全：配置 AUTH_TOKEN 后，/api/v1/research/* 需要携带 Bearer Token
    api_token: str = ""
    # 每个客户端 IP 每分钟最大请求数，0 表示不限流
    rate_limit_per_minute: int = 30

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[3] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def cors_origins(self) -> list[str]:
        values = [item.strip() for item in self.cors_allow_origins.split(",")]
        return [item for item in values if item]
