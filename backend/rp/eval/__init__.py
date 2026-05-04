"""RP eval module entrypoints.

The package root is intentionally lazy. Online observability paths import
lightweight submodules such as ``rp.eval.diagnostics`` during API requests;
eagerly importing the root exports would also load optional RAGAS/LangChain
dependencies and their background analytics threads.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS: dict[str, tuple[str, str]] = {
    "EvalCase": ("rp.eval.models", "EvalCase"),
    "EvalRunResult": ("rp.eval.models", "EvalRunResult"),
    "EvalRunner": ("rp.eval.runner", "EvalRunner"),
    "EvalSuiteRunner": ("rp.eval.suite", "EvalSuiteRunner"),
    "RagasRunConfig": ("rp.eval.ragas_adapter", "RagasRunConfig"),
    "compare_suite_outputs": ("rp.eval.comparison", "compare_suite_outputs"),
    "evaluate_suite_thresholds": ("rp.eval.comparison", "evaluate_suite_thresholds"),
    "ensure_registry_fixtures": ("rp.eval.fixtures", "ensure_registry_fixtures"),
    "load_case": ("rp.eval.case_loader", "load_case"),
    "load_cases": ("rp.eval.case_loader", "load_cases"),
    "load_replay": ("rp.eval.replay", "load_replay"),
    "parse_ragas_metrics": ("rp.eval.ragas_adapter", "parse_ragas_metrics"),
    "ragas_available": ("rp.eval.ragas_adapter", "ragas_available"),
    "resolve_metric_objects": ("rp.eval.ragas_adapter", "resolve_metric_objects"),
    "save_replay": ("rp.eval.replay", "save_replay"),
    "summarize_suite": ("rp.eval.comparison", "summarize_suite"),
}


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value


__all__ = [
    "EvalCase",
    "EvalRunResult",
    "EvalRunner",
    "EvalSuiteRunner",
    "RagasRunConfig",
    "compare_suite_outputs",
    "evaluate_suite_thresholds",
    "ensure_registry_fixtures",
    "load_case",
    "load_cases",
    "load_replay",
    "parse_ragas_metrics",
    "ragas_available",
    "resolve_metric_objects",
    "save_replay",
    "summarize_suite",
]
