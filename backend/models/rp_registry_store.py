"""SQLModel storage records for managed RP memory registry/profile inputs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint, inspect, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


_JSON_VARIANT = JSON().with_variant(JSONB(), "postgresql")


class MemoryDomainDescriptorRecord(SQLModel, table=True):  # type: ignore[call-arg]
    """Versioned persistent override/extension for one memory domain descriptor."""

    __tablename__ = "rp_memory_domain_descriptors"
    __table_args__ = (
        UniqueConstraint(
            "domain_id",
            "version",
            name="uq_rp_memory_domain_descriptors_domain_version",
        ),
    )

    descriptor_record_id: str = Field(primary_key=True, index=True)
    domain_id: str = Field(index=True)
    version: int = Field(index=True)
    lifecycle: str = Field(index=True)
    config_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    actor: str = Field(index=True)
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class MemoryWorkerDescriptorRecord(SQLModel, table=True):  # type: ignore[call-arg]
    """Versioned persistent override/extension for one runtime worker descriptor."""

    __tablename__ = "rp_memory_worker_descriptors"
    __table_args__ = (
        UniqueConstraint(
            "worker_id",
            "version",
            name="uq_rp_memory_worker_descriptors_worker_version",
        ),
    )

    descriptor_record_id: str = Field(primary_key=True, index=True)
    worker_id: str = Field(index=True)
    version: int = Field(index=True)
    lifecycle: str = Field(index=True)
    config_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    actor: str = Field(index=True)
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class MemoryBlockTemplateDescriptorRecord(SQLModel, table=True):  # type: ignore[call-arg]
    """Versioned persistent override/extension for one block template descriptor."""

    __tablename__ = "rp_memory_block_template_descriptors"
    __table_args__ = (
        UniqueConstraint(
            "block_template_id",
            "version",
            name="uq_rp_memory_block_template_descriptors_template_version",
        ),
    )

    descriptor_record_id: str = Field(primary_key=True, index=True)
    block_template_id: str = Field(index=True)
    domain_id: str = Field(index=True)
    version: int = Field(index=True)
    lifecycle: str = Field(index=True)
    config_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    actor: str = Field(index=True)
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class MemoryModeProfileRecord(SQLModel, table=True):  # type: ignore[call-arg]
    """Managed mode/profile config that future snapshots compile from."""

    __tablename__ = "rp_memory_mode_profiles"

    profile_id: str = Field(primary_key=True, index=True)
    mode: str = Field(index=True)
    version: int = Field(index=True)
    status: str = Field(index=True)
    config_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    actor: str = Field(index=True)
    published_at: datetime | None = Field(default=None, index=True)
    activated_at: datetime | None = Field(default=None, index=True)
    superseded_at: datetime | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


def ensure_registry_store_compatible_schema(engine: Engine) -> None:
    """Apply lightweight indexes for managed registry/profile records."""

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        if "rp_memory_domain_descriptors" in tables:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_rp_memory_domain_descriptors_id_lifecycle "
                    "ON rp_memory_domain_descriptors (domain_id, lifecycle)"
                )
            )
        if "rp_memory_worker_descriptors" in tables:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_rp_memory_worker_descriptors_id_lifecycle "
                    "ON rp_memory_worker_descriptors (worker_id, lifecycle)"
                )
            )
        if "rp_memory_block_template_descriptors" in tables:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_rp_memory_block_template_descriptors_domain_lifecycle "
                    "ON rp_memory_block_template_descriptors (domain_id, lifecycle)"
                )
            )
        if "rp_memory_mode_profiles" in tables:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_rp_memory_mode_profiles_mode_status "
                    "ON rp_memory_mode_profiles (mode, status)"
                )
            )
