"""Environment-backed configuration with conservative validated defaults."""

from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Optional BOOKBRIDGE_ settings; no .env file is required."""

    model_config = SettingsConfigDict(env_prefix="BOOKBRIDGE_", env_file=".env", extra="ignore")
    upstream_base_url: str = "https://books.toscrape.com"
    user_agent: str = "BookBridgeAPI/1.0 (educational demo; contact: akshattayal8622@gmail.com)"
    connect_timeout_seconds: float = Field(default=3, gt=0)
    read_timeout_seconds: float = Field(default=8, gt=0)
    max_retries: int = Field(default=2, ge=0, le=5)
    retry_backoff_seconds: float = Field(default=0.5, ge=0)
    max_concurrent_requests: int = Field(default=4, ge=1, le=4)
    min_request_interval_seconds: float = Field(default=0.1, ge=0)
    detail_cache_ttl_seconds: float = Field(default=300, ge=0)
    index_ttl_seconds: float = Field(default=900, ge=0)
    index_warmup_on_startup: bool = False
    respect_robots_txt: bool = True
    log_level: str = "INFO"

    @field_validator("upstream_base_url")
    @classmethod
    def validate_base(cls, value: str) -> str:
        """Reject credentials, query strings and non-HTTP source origins."""
        parts = urlsplit(value)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
            or parts.path not in {"", "/"}
        ):
            raise ValueError("upstream_base_url must be an HTTP(S) origin without credentials")
        _ = parts.port
        return value.rstrip("/")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        """Accept only standard logging levels."""
        value = value.upper()
        if value not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("Invalid logging level")
        return value
