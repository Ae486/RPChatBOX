"""Structured readiness models for local retrieval rerank backends."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LocalRerankDependencyStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package: str
    module: str
    installed: bool
    version: str | None = None


class LocalRerankReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ready", "dependency_missing", "unconfigured", "load_failed"]
    configured: bool = False
    provider_id: str | None = None
    model_id: str | None = None
    model_name: str | None = None
    resolution_source: str | None = None
    python_version: str
    include_model_load: bool = False
    model_load_attempted: bool = False
    model_load_ok: bool = False
    load_error: str | None = None
    requirements_path: str | None = None
    dependencies: list[LocalRerankDependencyStatus] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
