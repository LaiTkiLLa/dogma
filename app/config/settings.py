"""Application configuration loaded from environment."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings from environment / `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = ""

    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_timeout_seconds: int = 30

    dogma_base_url: str = "https://service.dogma.ru/api/layouts-filter"
    dogma_public_base_url: str = "https://dogma.ru"
    dogma_request_timeout: int = 30
    dogma_page_limit: int = 100
    dogma_request_delay_seconds: float = 2
    dogma_sync_interval_seconds: int = 3600
    dogma_retry_delay_seconds: int = 10

    worker_interval_seconds: int = 3600
    worker_enabled: bool = True

    app_log_level: str = "INFO"
    chat_max_tool_iterations: int = 3

    # Через запятую; пусто — CORS middleware не включается
    cors_origins: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
