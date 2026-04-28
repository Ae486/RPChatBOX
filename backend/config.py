"""Backend configuration management."""
from pathlib import Path
from functools import lru_cache
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Server
    host: str = "127.0.0.1"
    port: int = 8765
    debug: bool = False

    # Storage
    storage_dir: Path = Path("storage")
    database_url: str | None = None

    # LLM Proxy
    llm_request_timeout: float = 120.0
    llm_connect_timeout: float = 30.0
    llm_max_tool_iterations: int = 10
    llm_num_retries: int = 2
    llm_stream_timeout: float = 30.0
    llm_stream_idle_timeout: float = 60.0
    llm_allowed_fails: int = 0
    llm_cooldown_time: float = 0.0
    llm_enable_httpx_fallback: bool = True
    llm_enable_gemini_native: bool = True

    # LiteLLM toggle (False = fallback to httpx direct proxy)
    use_litellm: bool = True
    use_litellm_router: bool = True
    rp_memory_core_state_store_write_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "CHATBOX_BACKEND_RP_MEMORY_CORE_STATE_STORE_WRITE_ENABLED",
            "RP_MEMORY_CORE_STATE_STORE_WRITE_ENABLED",
        ),
    )
    rp_memory_core_state_store_read_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "CHATBOX_BACKEND_RP_MEMORY_CORE_STATE_STORE_READ_ENABLED",
            "RP_MEMORY_CORE_STATE_STORE_READ_ENABLED",
        ),
    )
    rp_memory_core_state_store_write_switch_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "CHATBOX_BACKEND_RP_MEMORY_CORE_STATE_STORE_WRITE_SWITCH_ENABLED",
            "RP_MEMORY_CORE_STATE_STORE_WRITE_SWITCH_ENABLED",
        ),
    )

    # Langfuse observability
    langfuse_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "CHATBOX_BACKEND_LANGFUSE_ENABLED",
            "LANGFUSE_ENABLED",
        ),
    )
    langfuse_public_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "CHATBOX_BACKEND_LANGFUSE_PUBLIC_KEY",
            "LANGFUSE_PUBLIC_KEY",
        ),
    )
    langfuse_secret_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "CHATBOX_BACKEND_LANGFUSE_SECRET_KEY",
            "LANGFUSE_SECRET_KEY",
        ),
    )
    langfuse_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "CHATBOX_BACKEND_LANGFUSE_BASE_URL",
            "LANGFUSE_BASE_URL",
        ),
    )
    langfuse_environment: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "CHATBOX_BACKEND_LANGFUSE_ENVIRONMENT",
            "LANGFUSE_ENVIRONMENT",
        ),
    )
    langfuse_release: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "CHATBOX_BACKEND_LANGFUSE_RELEASE",
            "LANGFUSE_RELEASE",
        ),
    )
    langfuse_sample_rate: float | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "CHATBOX_BACKEND_LANGFUSE_SAMPLE_RATE",
            "LANGFUSE_SAMPLE_RATE",
        ),
    )
    langfuse_debug: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "CHATBOX_BACKEND_LANGFUSE_DEBUG",
            "LANGFUSE_DEBUG",
        ),
    )

    # Version
    version: str = "0.1.0"

    @property
    def resolved_database_url(self) -> str:
        """Return the SQLAlchemy database URL used by backend persistence."""
        if not self.database_url:
            db_path = (self.storage_dir / "chatbox.db").resolve()
            return f"sqlite:///{db_path.as_posix()}"

        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace(
                "postgresql://",
                "postgresql+psycopg://",
                1,
            )
        return self.database_url

    @property
    def is_postgres_database(self) -> bool:
        """Whether the durable store is PostgreSQL-backed."""
        return self.resolved_database_url.startswith("postgresql+psycopg://")

    @property
    def langgraph_checkpoint_url(self) -> str | None:
        """Return a psycopg-compatible DSN for LangGraph Postgres checkpointers."""
        if not self.is_postgres_database:
            return None
        return self.resolved_database_url.replace(
            "postgresql+psycopg://",
            "postgresql://",
            1,
        )

    @property
    def langgraph_sqlite_path(self) -> Path:
        """Return the SQLite checkpoint path used outside PostgreSQL mode."""
        return (self.storage_dir / "langgraph-checkpoints.sqlite").resolve()

    def ensure_dirs(self) -> None:
        """Create required directories."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    class Config:
        env_prefix = "CHATBOX_BACKEND_"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
