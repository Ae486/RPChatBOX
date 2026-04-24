"""Load eval cases from local JSON/YAML files."""

from __future__ import annotations

import json
from pathlib import Path

from .models import EvalCase


_YAML_SUFFIXES = {".yaml", ".yml"}
_JSON_SUFFIXES = {".json"}


def load_case(path: str | Path) -> EvalCase:
    case_path = Path(path)
    payload = _load_payload(case_path)
    return EvalCase.model_validate(payload)


def load_cases(path: str | Path) -> list[EvalCase]:
    base_path = Path(path)
    if base_path.is_file():
        return [load_case(base_path)]

    if not base_path.exists():
        raise FileNotFoundError(f"Eval case path does not exist: {base_path}")

    case_paths = sorted(
        item
        for item in base_path.rglob("*")
        if item.is_file() and item.suffix.lower() in (_JSON_SUFFIXES | _YAML_SUFFIXES)
    )
    return [load_case(item) for item in case_paths]


def _load_payload(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Eval case file does not exist: {path}")

    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if suffix in _JSON_SUFFIXES:
        return json.loads(text)
    if suffix in _YAML_SUFFIXES:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                f"YAML support requires PyYAML to load {path.name}"
            ) from exc
        payload = yaml.safe_load(text)
        if not isinstance(payload, dict):
            raise ValueError(f"Eval case YAML must deserialize to an object: {path}")
        return payload
    raise ValueError(f"Unsupported eval case format: {path}")
