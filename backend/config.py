"""Backend configuration management."""
from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Server
    host: str = "127.0.0.1"
    port: int = 8765
    debug: bool = False

    # Storage
    storage_dir: Path = Path("storage")

    # LLM Proxy
    llm_request_timeout: float = 120.0
    llm_connect_timeout: float = 30.0
    llm_max_tool_iterations: int = 10

    # LiteLLM toggle (False = fallback to httpx direct proxy)
    use_litellm: bool = True

    # Version
    version: str = "0.1.0"

    def ensure_dirs(self) -> None:
        """Create required directories."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    class Config:
        env_prefix = "CHATBOX_BACKEND_"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
