from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MasterPTIT Observability Portal"
    api_prefix: str = "/api"
    app_timezone: str = Field(default="Asia/Ho_Chi_Minh", alias="APP_TIMEZONE")
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    postgres_host: str = Field(default="postgres", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="observability_portal", alias="POSTGRES_DB")
    postgres_user: str = Field(default="obs_user", alias="POSTGRES_USER")
    postgres_password: str = Field(default="ChangeMe_StrongPassword_123", alias="POSTGRES_PASSWORD")
    jwt_secret: str = Field(default="ChangeMe_Very_Long_Random_JWT_Secret", alias="JWT_SECRET")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    server_secret: str = Field(default="ChangeMe_Server_Secret_For_Agent_Token_Hmac", alias="SERVER_SECRET")
    public_portal_url: str = Field(default="http://localhost:8080", alias="PUBLIC_PORTAL_URL")
    public_grafana_url: str = Field(default="http://localhost:3000", alias="PUBLIC_GRAFANA_URL")
    public_ingest_url: str = Field(default="http://localhost:18080/api/v1/write", alias="PUBLIC_INGEST_URL")
    agent_package_dir: Path = Field(default=Path("/app/packages/agent"), alias="APP_AGENT_PACKAGE_DIR")
    agent_source_dir: Path = Field(default=Path("/app/packages"), alias="APP_AGENT_SOURCE_DIR")
    grafana_internal_url: str = Field(default="http://grafana:3000", alias="GRAFANA_INTERNAL_URL")
    grafana_admin_user: str = Field(default="admin", alias="GRAFANA_ADMIN_USER")
    grafana_admin_password: str = Field(default="admin", alias="GRAFANA_ADMIN_PASSWORD")
    victoriametrics_internal_url: str = Field(default="http://victoriametrics:8428", alias="VICTORIAMETRICS_INTERNAL_URL")
    alertmanager_internal_url: str = Field(default="http://vmalertmanager:9093", alias="ALERTMANAGER_INTERNAL_URL")
    receiver_otp_expire_minutes: int = Field(default=10, alias="RECEIVER_OTP_EXPIRE_MINUTES")
    receiver_webhook_timeout_seconds: float = Field(default=5.0, alias="RECEIVER_WEBHOOK_TIMEOUT_SECONDS")
    alert_dispatch_timeout_seconds: float = Field(default=10.0, alias="ALERT_DISPATCH_TIMEOUT_SECONDS")
    vmalert_rules_file: Path = Field(default=Path("configs/vmalert/rules/portal-alert-rules.yml"), alias="VMALERT_RULES_FILE")
    vmalert_reload_url: str | None = Field(default="http://vmalert:8880/-/reload", alias="VMALERT_RELOAD_URL")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def async_database_url(self) -> str:
        """Build the async SQLAlchemy URL from DATABASE_URL or POSTGRES_* variables."""
        if self.database_url:
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)
        return f"postgresql+asyncpg://{user}:{password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def sync_database_url(self) -> str:
        """Build the sync SQLAlchemy URL used by Alembic and psycopg."""
        return self.async_database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings loaded from environment variables."""
    return Settings()
