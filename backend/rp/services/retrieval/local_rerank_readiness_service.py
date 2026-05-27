"""Readiness checks for optional local retrieval rerank backends."""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import importlib.util
import sys
from pathlib import Path

from rp.models.retrieval_local_rerank import (
    LocalRerankDependencyStatus,
    LocalRerankReadiness,
)
from rp.retrieval.reranker_resolver import LocalCrossEncoderResolver, LocalCrossEncoderTarget
from services.model_registry import ModelRegistryService, get_model_registry_service
from services.provider_registry import ProviderRegistryService, get_provider_registry_service

_REQUIRED_PACKAGES: tuple[tuple[str, str], ...] = (
    ("sentence-transformers", "sentence_transformers"),
    ("torch", "torch"),
    ("transformers", "transformers"),
)


class LocalRerankReadinessService:
    """Inspect environment + registry state for local cross-encoder reranking."""

    def __init__(
        self,
        *,
        model_registry_service: ModelRegistryService | None = None,
        provider_registry_service: ProviderRegistryService | None = None,
        dependency_inspector=None,
        model_loader=None,
    ) -> None:
        self._model_registry_service = model_registry_service or get_model_registry_service()
        self._provider_registry_service = provider_registry_service or get_provider_registry_service()
        self._dependency_inspector = dependency_inspector or self._inspect_dependencies
        self._model_loader = model_loader or self._default_model_loader

    def get_readiness(
        self,
        *,
        model_id: str | None = None,
        provider_id: str | None = None,
        include_model_load: bool = False,
    ) -> LocalRerankReadiness:
        dependencies = self._dependency_inspector()
        target = self._resolve_target(model_id=model_id, provider_id=provider_id)
        requirements_path = self._requirements_path()
        warnings: list[str] = []

        if target is None:
            return LocalRerankReadiness(
                status="unconfigured",
                configured=False,
                python_version=sys.version.split()[0],
                include_model_load=include_model_load,
                model_load_attempted=False,
                model_load_ok=False,
                requirements_path=requirements_path.as_posix(),
                dependencies=dependencies,
                warnings=["local_rerank_unconfigured:no_local_cross_encoder_model"],
            )

        missing_dependencies = [item.package for item in dependencies if not item.installed]
        if missing_dependencies:
            warnings.append(
                "local_rerank_dependency_missing:" + ",".join(missing_dependencies)
            )
            return LocalRerankReadiness(
                status="dependency_missing",
                configured=True,
                provider_id=target.provider_id,
                model_id=target.model_id,
                model_name=target.model_name,
                resolution_source=target.resolution_source,
                python_version=sys.version.split()[0],
                include_model_load=include_model_load,
                model_load_attempted=False,
                model_load_ok=False,
                requirements_path=requirements_path.as_posix(),
                dependencies=dependencies,
                warnings=warnings,
            )

        if not include_model_load:
            return LocalRerankReadiness(
                status="ready",
                configured=True,
                provider_id=target.provider_id,
                model_id=target.model_id,
                model_name=target.model_name,
                resolution_source=target.resolution_source,
                python_version=sys.version.split()[0],
                include_model_load=False,
                model_load_attempted=False,
                model_load_ok=False,
                requirements_path=requirements_path.as_posix(),
                dependencies=dependencies,
                warnings=warnings,
            )

        try:
            self._model_loader(target.model_name)
        except Exception as exc:
            warnings.append(f"local_rerank_model_load_failed:{type(exc).__name__}")
            return LocalRerankReadiness(
                status="load_failed",
                configured=True,
                provider_id=target.provider_id,
                model_id=target.model_id,
                model_name=target.model_name,
                resolution_source=target.resolution_source,
                python_version=sys.version.split()[0],
                include_model_load=True,
                model_load_attempted=True,
                model_load_ok=False,
                load_error=f"{type(exc).__name__}: {exc}",
                requirements_path=requirements_path.as_posix(),
                dependencies=dependencies,
                warnings=warnings,
            )

        return LocalRerankReadiness(
            status="ready",
            configured=True,
            provider_id=target.provider_id,
            model_id=target.model_id,
            model_name=target.model_name,
            resolution_source=target.resolution_source,
            python_version=sys.version.split()[0],
            include_model_load=True,
            model_load_attempted=True,
            model_load_ok=True,
            requirements_path=requirements_path.as_posix(),
            dependencies=dependencies,
            warnings=warnings,
        )

    def _resolve_target(
        self,
        *,
        model_id: str | None,
        provider_id: str | None,
    ) -> LocalCrossEncoderTarget | None:
        resolver = LocalCrossEncoderResolver(
            model_registry_service=self._model_registry_service,
            provider_registry_service=self._provider_registry_service,
            model_id=model_id,
            provider_id=provider_id,
        )
        return resolver.resolve_target()

    @staticmethod
    def _inspect_dependencies() -> list[LocalRerankDependencyStatus]:
        items: list[LocalRerankDependencyStatus] = []
        for package_name, module_name in _REQUIRED_PACKAGES:
            installed = importlib.util.find_spec(module_name) is not None
            version = None
            if installed:
                try:
                    version = importlib_metadata.version(package_name)
                except importlib_metadata.PackageNotFoundError:
                    version = None
            items.append(
                LocalRerankDependencyStatus(
                    package=package_name,
                    module=module_name,
                    installed=installed,
                    version=version,
                )
            )
        return items

    @staticmethod
    def _default_model_loader(model_name: str):
        from sentence_transformers import CrossEncoder  # type: ignore

        return CrossEncoder(model_name)

    @staticmethod
    def _requirements_path() -> Path:
        return Path(__file__).resolve().parents[2] / "requirements-rerank-local.txt"
