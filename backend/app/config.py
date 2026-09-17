"""Application settings, loaded from environment / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Relationship CRM"
    environment: str = "development"
    api_prefix: str = "/api/v1"

    database_url: str = "sqlite+pysqlite:///./relationship_crm.db"

    session_cookie_name: str = "rcrm_session"
    session_ttl_hours: int = 8
    session_cookie_secure: bool = False
    session_cookie_samesite: str = "lax"

    cors_origins: list[str] = ["http://localhost:5173"]

    secret_key: str = "dev-insecure-change-me"

    # AI extraction. With no base URL, a deterministic offline stub is used so the
    # pipeline stays testable; set these to point at any OpenAI-compatible endpoint
    # (Ollama, vLLM, NVIDIA NIM, a hosted gateway).
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str = "stub"
    llm_timeout_seconds: float = 30.0

    # Background jobs: nightly score recompute + overdue-task sweep.
    enable_scheduler: bool = True
    overdue_escalation_days: int = 3

    # Engagement moments. enable_moments is the kill switch — turning it off
    # stops all detection and drafting without a deploy.
    enable_moments: bool = True
    moment_lookahead_days: int = 7
    moment_inactivity_days: int = 35
    moment_fatigue_days: int = 21
    moment_promotion_recent_days: int = 30

    # Autonomous agent (observe + recommend only — it never writes a real
    # domain object itself; a human must approve every recommendation).
    # enable_agent is the kill switch, same pattern as enable_moments.
    enable_agent: bool = True
    agent_portfolio_scan_limit: int = 20
    agent_max_relationships_per_run: int = 10
    agent_recommendation_ttl_days: int = 14
    # episodic memory: how long an explicit human rejection of a
    # recommendation type is respected before the agent may propose that
    # type again for the same relationship.
    agent_rejection_cooldown_days: int = 14

    # Automated backups. enable_backups is the kill switch. backup_dir is
    # relative to the database file's own directory (so it lands inside the
    # same Docker volume with zero extra config); backup_retention_count
    # caps how many nightly snapshots are kept.
    enable_backups: bool = True
    backup_dir: str = "backups"
    backup_retention_count: int = 7

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
