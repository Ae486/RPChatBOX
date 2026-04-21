"""Canonical JSON serialization for memory CRUD tool results."""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from rp.models.memory_crud import ToolErrorPayload


class MemoryCrudSerializationService:
    """Serialize pydantic results and errors into canonical JSON strings."""

    @staticmethod
    def serialize_result(result: BaseModel | dict[str, Any] | list[Any]) -> str:
        payload: Any
        if isinstance(result, BaseModel):
            payload = result.model_dump(mode="json", exclude_none=True)
        else:
            payload = result
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    @classmethod
    def serialize_error(
        cls,
        *,
        code: str,
        message: str,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> str:
        return cls.serialize_result(
            ToolErrorPayload(
                code=code,
                message=message,
                retryable=retryable,
                details=details,
            )
        )

