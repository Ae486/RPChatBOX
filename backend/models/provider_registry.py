"""Provider registry models."""
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from models.chat import CircuitBreakerConfig, ProviderConfig as RuntimeProviderConfig


class ProviderRegistryEntry(BaseModel):
    """Persistent provider record stored by the backend registry."""

    id: str
    name: str
    type: str
    api_key: str
    api_url: str
    is_enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    custom_headers: dict[str, str] = Field(default_factory=dict)
    description: str | None = None
    backend_mode: Literal["direct", "proxy", "auto"] | None = None
    fallback_enabled: bool | None = None
    fallback_timeout_ms: int | None = None
    circuit_breaker: CircuitBreakerConfig | None = None

    def _normalized_routing_hints(self) -> dict[str, object | None]:
        """Normalize implicit/default Flutter routing hints back to legacy semantics."""
        backend_mode = self.backend_mode
        fallback_enabled = self.fallback_enabled
        fallback_timeout_ms = self.fallback_timeout_ms
        circuit_breaker = self.circuit_breaker

        # Phase 3 first cut initially persisted Flutter's default routing config
        # (`direct` + fallback enabled + 5000ms + no circuit breaker), which
        # unintentionally changed the backend's legacy "implicit auto" behavior.
        # Treat that exact default bundle as "no explicit routing hints".
        if (
            backend_mode == "direct"
            and fallback_enabled is True
            and fallback_timeout_ms == 5000
            and circuit_breaker is None
        ):
            backend_mode = None
            fallback_enabled = None
            fallback_timeout_ms = None

        return {
            "backend_mode": backend_mode,
            "fallback_enabled": fallback_enabled,
            "fallback_timeout_ms": fallback_timeout_ms,
            "circuit_breaker": circuit_breaker,
        }

    def with_timestamps(self, *, existing: "ProviderRegistryEntry | None" = None) -> "ProviderRegistryEntry":
        """Fill creation/update timestamps for storage."""
        now = datetime.now(timezone.utc)
        created_at = self.created_at or (existing.created_at if existing else None) or now
        updated_at = self.updated_at or now
        return self.model_copy(
            update={
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )

    def to_runtime_provider(self) -> RuntimeProviderConfig:
        """Convert registry data into the runtime provider config used by chat routes."""
        routing_hints = self._normalized_routing_hints()
        return RuntimeProviderConfig(
            type=self.type,
            api_key=self.api_key,
            api_url=self.api_url,
            custom_headers=self.custom_headers,
            backend_mode=routing_hints["backend_mode"],
            fallback_enabled=routing_hints["fallback_enabled"],
            fallback_timeout_ms=routing_hints["fallback_timeout_ms"],
            circuit_breaker=routing_hints["circuit_breaker"],
        )

    @property
    def masked_api_key(self) -> str:
        """Return a masked API key for debug/list responses."""
        if not self.api_key:
            return ""
        if len(self.api_key) <= 8:
            return "••••••••"
        return f"{self.api_key[:4]}••••{self.api_key[-4:]}"


class ProviderRegistrySummary(BaseModel):
    """Safe provider metadata returned by registry list/read endpoints."""

    id: str
    name: str
    type: str
    api_url: str
    is_enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    custom_headers: dict[str, str] = Field(default_factory=dict)
    description: str | None = None
    backend_mode: Literal["direct", "proxy", "auto"] | None = None
    fallback_enabled: bool | None = None
    fallback_timeout_ms: int | None = None
    circuit_breaker: CircuitBreakerConfig | None = None
    has_api_key: bool = False
    masked_api_key: str = ""

    @classmethod
    def from_entry(cls, entry: ProviderRegistryEntry) -> "ProviderRegistrySummary":
        """Build a safe summary from a stored registry entry."""
        return cls(
            id=entry.id,
            name=entry.name,
            type=entry.type,
            api_url=entry.api_url,
            is_enabled=entry.is_enabled,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
            custom_headers=entry.custom_headers,
            description=entry.description,
            backend_mode=entry.backend_mode,
            fallback_enabled=entry.fallback_enabled,
            fallback_timeout_ms=entry.fallback_timeout_ms,
            circuit_breaker=entry.circuit_breaker,
            has_api_key=bool(entry.api_key),
            masked_api_key=entry.masked_api_key,
        )
