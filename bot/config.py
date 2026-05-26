from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_COMPETENCIES = [
    "Стратегическое мышление",
    "Лидерство и влияние",
    "Принятие решений",
    "Коммуникация",
    "Управление командой",
    "Ориентация на результат",
    "Адаптивность",
    "Эмоциональный интеллект",
]


class Settings(BaseSettings):
    bot_token: str = Field(validation_alias="BOT_TOKEN")
    yandex_speechkit_api_key: str = Field(validation_alias="YANDEX_SPEECHKIT_API_KEY")
    yandex_gpt_api_key: str = Field(validation_alias="YANDEX_GPT_API_KEY")
    yandex_folder_id: str = Field(validation_alias="YANDEX_FOLDER_ID")
    yandex_storage_bucket: str | None = Field(default=None, validation_alias="YANDEX_STORAGE_BUCKET")
    yandex_storage_access_key_id: str | None = Field(default=None, validation_alias="YANDEX_STORAGE_ACCESS_KEY_ID")
    yandex_storage_secret_access_key: str | None = Field(
        default=None,
        validation_alias="YANDEX_STORAGE_SECRET_ACCESS_KEY",
    )
    yandex_storage_endpoint: str = Field(
        default="https://storage.yandexcloud.net",
        validation_alias="YANDEX_STORAGE_ENDPOINT",
    )
    yandex_storage_prefix: str = Field(default="interviews", validation_alias="YANDEX_STORAGE_PREFIX")

    database_url: str = Field(default="sqlite+aiosqlite:///./data/app.db", validation_alias="DATABASE_URL")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    download_dir: Path = Field(default=Path("./data/uploads"), validation_alias="DOWNLOAD_DIR")

    speechkit_stt_url: str = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
    speechkit_async_stt_url: str = "https://transcribe.api.cloud.yandex.net/speech/stt/v2/longRunningRecognize"
    yandex_operation_url: str = "https://operation.api.cloud.yandex.net/operations"
    yandex_gpt_url: str = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    yandex_gpt_model_uri: str | None = Field(default=None, validation_alias="YANDEX_GPT_MODEL_URI")
    speechkit_sync_max_bytes: int = Field(default=1_000_000, validation_alias="SPEECHKIT_SYNC_MAX_BYTES")
    speechkit_async_poll_interval_seconds: int = Field(
        default=10,
        validation_alias="SPEECHKIT_ASYNC_POLL_INTERVAL_SECONDS",
    )
    speechkit_async_timeout_seconds: int = Field(
        default=7200,
        validation_alias="SPEECHKIT_ASYNC_TIMEOUT_SECONDS",
    )
    admin_username: str = Field(default="admin", validation_alias="ADMIN_USERNAME")
    admin_password: str | None = Field(default=None, validation_alias="ADMIN_PASSWORD")
    admin_bot_password: str = Field(default="1172", validation_alias="ADMIN_BOT_PASSWORD")
    web_host: str = Field(default="127.0.0.1", validation_alias="WEB_HOST")
    web_port: int = Field(default=8080, validation_alias="WEB_PORT")
    competencies: list[str] = Field(default_factory=lambda: DEFAULT_COMPETENCIES.copy())

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def resolved_yandex_gpt_model_uri(self) -> str:
        return self.yandex_gpt_model_uri or f"gpt://{self.yandex_folder_id}/yandexgpt/rc"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
