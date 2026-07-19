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
    # Defaults to "" so the shared services can be imported by the web backend without
    # bot-only credentials. The Telegram bot still reads real values from the environment.
    bot_token: str = Field(default="", validation_alias="BOT_TOKEN")
    yandex_speechkit_api_key: str = Field(default="", validation_alias="YANDEX_SPEECHKIT_API_KEY")
    yandex_gpt_api_key: str = Field(default="", validation_alias="YANDEX_GPT_API_KEY")
    yandex_folder_id: str = Field(default="", validation_alias="YANDEX_FOLDER_ID")
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
    telegram_download_max_bytes: int = Field(default=20_000_000, validation_alias="TELEGRAM_DOWNLOAD_MAX_BYTES")
    telegram_file_request_timeout_seconds: int = Field(
        default=900,
        validation_alias="TELEGRAM_FILE_REQUEST_TIMEOUT_SECONDS",
    )
    # get_file only fetches metadata, so it should fail fast when the local Bot API stalls
    # (a hung attempt then retries on a fresh connection) instead of blocking for minutes.
    telegram_get_file_timeout_seconds: int = Field(
        default=120,
        validation_alias="TELEGRAM_GET_FILE_TIMEOUT_SECONDS",
    )
    telegram_file_download_timeout_seconds: int = Field(
        default=900,
        validation_alias="TELEGRAM_FILE_DOWNLOAD_TIMEOUT_SECONDS",
    )
    telegram_file_download_attempts: int = Field(default=3, validation_alias="TELEGRAM_FILE_DOWNLOAD_ATTEMPTS")
    telegram_file_download_retry_delay_seconds: int = Field(
        default=15,
        validation_alias="TELEGRAM_FILE_DOWNLOAD_RETRY_DELAY_SECONDS",
    )
    # Per-attempt timeout for sending result documents (notebook/report/IPR/transcript).
    # Files are small, so keep this short: a stalled local Bot API fails fast and the
    # retry opens a fresh connection instead of blocking for the long download timeout.
    telegram_file_send_timeout_seconds: int = Field(
        default=180,
        validation_alias="TELEGRAM_FILE_SEND_TIMEOUT_SECONDS",
    )
    telegram_api_base_url: str | None = Field(default=None, validation_alias="TELEGRAM_API_BASE_URL")
    telegram_api_is_local: bool = Field(default=False, validation_alias="TELEGRAM_API_IS_LOCAL")
    telegram_drop_pending_updates_on_start: bool = Field(
        default=False,
        validation_alias="TELEGRAM_DROP_PENDING_UPDATES_ON_START",
    )

    speechkit_stt_url: str = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
    speechkit_async_stt_url: str = "https://transcribe.api.cloud.yandex.net/speech/stt/v2/longRunningRecognize"
    speechkit_async_stt_v3_url: str = Field(
        default="https://stt.api.cloud.yandex.net/stt/v3/recognizeFileAsync",
        validation_alias="SPEECHKIT_ASYNC_STT_V3_URL",
    )
    speechkit_async_stt_v3_result_url: str = Field(
        default="https://stt.api.cloud.yandex.net/stt/v3/getRecognition",
        validation_alias="SPEECHKIT_ASYNC_STT_V3_RESULT_URL",
    )
    yandex_operation_url: str = "https://operation.api.cloud.yandex.net/operations"
    yandex_gpt_url: str = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    yandex_gpt_model_uri: str | None = Field(default=None, validation_alias="YANDEX_GPT_MODEL_URI")
    speechkit_sync_max_bytes: int = Field(default=1_000_000, validation_alias="SPEECHKIT_SYNC_MAX_BYTES")
    speechkit_async_api_version: str = Field(default="v3", validation_alias="SPEECHKIT_ASYNC_API_VERSION")
    speechkit_v3_model: str = Field(default="general:rc", validation_alias="SPEECHKIT_V3_MODEL")
    speechkit_v3_enable_speaker_labeling: bool = Field(
        default=True,
        validation_alias="SPEECHKIT_V3_ENABLE_SPEAKER_LABELING",
    )
    speechkit_v3_fallback_to_v2: bool = Field(default=True, validation_alias="SPEECHKIT_V3_FALLBACK_TO_V2")
    speechkit_async_poll_interval_seconds: int = Field(
        default=10,
        validation_alias="SPEECHKIT_ASYNC_POLL_INTERVAL_SECONDS",
    )
    speechkit_async_timeout_seconds: int = Field(
        default=7200,
        validation_alias="SPEECHKIT_ASYNC_TIMEOUT_SECONDS",
    )
    speechkit_deduplicate_transcript: bool = Field(
        default=True,
        validation_alias="SPEECHKIT_DEDUPLICATE_TRANSCRIPT",
    )
    speechkit_dedup_similarity_threshold: float = Field(
        default=0.88,
        validation_alias="SPEECHKIT_DEDUP_SIMILARITY_THRESHOLD",
    )
    transcript_export_include_timestamps: bool = Field(
        default=False,
        validation_alias="TRANSCRIPT_EXPORT_INCLUDE_TIMESTAMPS",
    )
    transcript_export_merge_same_role: bool = Field(
        default=True,
        validation_alias="TRANSCRIPT_EXPORT_MERGE_SAME_ROLE",
    )
    aitunnel_api_key: str | None = Field(default=None, validation_alias="AITUNNEL_API_KEY")
    aitunnel_base_url: str = Field(default="https://api.aitunnel.ru/v1", validation_alias="AITUNNEL_BASE_URL")
    aitunnel_whisper_model: str = Field(
        default="whisper-large-v3-turbo",
        validation_alias="AITUNNEL_WHISPER_MODEL",
    )
    aitunnel_language: str | None = Field(default="ru", validation_alias="AITUNNEL_LANGUAGE")
    aitunnel_response_format: str = Field(default="json", validation_alias="AITUNNEL_RESPONSE_FORMAT")
    aitunnel_timeout_seconds: int = Field(default=1800, validation_alias="AITUNNEL_TIMEOUT_SECONDS")
    aitunnel_force_ipv4: bool = Field(default=True, validation_alias="AITUNNEL_FORCE_IPV4")
    aitunnel_max_upload_bytes: int = Field(default=25_000_000, validation_alias="AITUNNEL_MAX_UPLOAD_BYTES")
    neuroapi_api_key: str | None = Field(default=None, validation_alias="NEUROAPI_API_KEY")
    neuroapi_base_url: str = Field(default="https://neuroapi.host/v1", validation_alias="NEUROAPI_BASE_URL")
    neuroapi_whisper_model: str = Field(default="whisper-1", validation_alias="NEUROAPI_WHISPER_MODEL")
    neuroapi_language: str | None = Field(default="ru", validation_alias="NEUROAPI_LANGUAGE")
    neuroapi_response_format: str = Field(default="json", validation_alias="NEUROAPI_RESPONSE_FORMAT")
    neuroapi_timeout_seconds: int = Field(default=1800, validation_alias="NEUROAPI_TIMEOUT_SECONDS")
    neuroapi_force_ipv4: bool = Field(default=True, validation_alias="NEUROAPI_FORCE_IPV4")
    neuroapi_max_upload_bytes: int = Field(default=25_000_000, validation_alias="NEUROAPI_MAX_UPLOAD_BYTES")
    ffmpeg_binary: str = Field(default="ffmpeg", validation_alias="FFMPEG_BINARY")
    ffprobe_binary: str = Field(default="ffprobe", validation_alias="FFPROBE_BINARY")
    whisper_compression_bitrates_kbps: str = Field(
        default="32,24,16",
        validation_alias="WHISPER_COMPRESSION_BITRATES_KBPS",
    )
    whisper_chunk_enabled: bool = Field(default=True, validation_alias="WHISPER_CHUNK_ENABLED")
    whisper_chunk_bitrate_kbps: int = Field(default=32, validation_alias="WHISPER_CHUNK_BITRATE_KBPS")
    whisper_chunk_overlap_seconds: int = Field(default=15, validation_alias="WHISPER_CHUNK_OVERLAP_SECONDS")
    whisper_chunk_min_seconds: int = Field(default=60, validation_alias="WHISPER_CHUNK_MIN_SECONDS")
    whisper_chunk_size_safety: float = Field(default=0.85, validation_alias="WHISPER_CHUNK_SIZE_SAFETY")
    # Max audio seconds per Whisper request. A long recording can fit under the size
    # limit yet still exceed the provider's gateway timeout (AI Tunnel returns HTTP 524),
    # so we also split by duration. ~10 min keeps each request well under the timeout.
    whisper_chunk_max_seconds: int = Field(default=600, validation_alias="WHISPER_CHUNK_MAX_SECONDS")
    role_labeling_enabled: bool = Field(default=True, validation_alias="ROLE_LABELING_ENABLED")
    role_labeling_provider: str = Field(default="aitunnel", validation_alias="ROLE_LABELING_PROVIDER")
    role_labeling_model: str = Field(default="gpt-5-mini", validation_alias="ROLE_LABELING_MODEL")
    role_labeling_timeout_seconds: int = Field(default=900, validation_alias="ROLE_LABELING_TIMEOUT_SECONDS")
    role_labeling_chunk_chars: int = Field(default=14000, validation_alias="ROLE_LABELING_CHUNK_CHARS")
    role_labeling_max_tokens: int = Field(default=16000, validation_alias="ROLE_LABELING_MAX_TOKENS")
    role_labeling_temperature: float = Field(default=0.0, validation_alias="ROLE_LABELING_TEMPERATURE")
    role_labeling_json_mode: bool = Field(default=True, validation_alias="ROLE_LABELING_JSON_MODE")
    analysis_llm_provider: str = Field(default="aitunnel", validation_alias="ANALYSIS_LLM_PROVIDER")
    analysis_llm_model: str = Field(default="gpt-4o-mini", validation_alias="ANALYSIS_LLM_MODEL")
    analysis_llm_timeout_seconds: int = Field(default=900, validation_alias="ANALYSIS_LLM_TIMEOUT_SECONDS")
    analysis_llm_temperature: float = Field(default=0.05, validation_alias="ANALYSIS_LLM_TEMPERATURE")
    analysis_llm_max_tokens: int = Field(default=8000, validation_alias="ANALYSIS_LLM_MAX_TOKENS")
    analysis_llm_json_mode: bool = Field(default=True, validation_alias="ANALYSIS_LLM_JSON_MODE")
    notebook_analysis_batch_size: int = Field(default=20, validation_alias="NOTEBOOK_ANALYSIS_BATCH_SIZE")
    analysis_llm_max_concurrency: int = Field(default=5, validation_alias="ANALYSIS_LLM_MAX_CONCURRENCY")
    pdf_export_enabled: bool = Field(default=True, validation_alias="PDF_EXPORT_ENABLED")
    libreoffice_binary: str = Field(default="soffice", validation_alias="LIBREOFFICE_BINARY")
    pdf_export_timeout_seconds: int = Field(default=120, validation_alias="PDF_EXPORT_TIMEOUT_SECONDS")
    admin_bot_password: str = Field(default="1172", validation_alias="ADMIN_BOT_PASSWORD")
    # Web sign-in. The password falls back to ADMIN_BOT_PASSWORD when WEB_PASSWORD is unset.
    web_login: str = Field(default="HR40", validation_alias="WEB_LOGIN")
    web_password: str = Field(default="", validation_alias="WEB_PASSWORD")
    # Signing key for session cookies. Generated and persisted next to the DB when unset.
    session_secret: str = Field(default="", validation_alias="SESSION_SECRET")
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
