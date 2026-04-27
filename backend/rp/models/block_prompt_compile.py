"""Compile result model for cached Block-backed internal prompt overlays."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from rp.models.block_prompt_context import RpBlockPromptContextView


BlockPromptCompileMode = Literal["rebuilt", "reused"]


class RpBlockPromptCompileView(BaseModel):
    """Current Block prompt compile output plus cache/rebuild metadata."""

    model_config = ConfigDict(extra="forbid")

    context: RpBlockPromptContextView
    prompt_overlay: str
    compile_mode: BlockPromptCompileMode
    compile_reasons: list[str] = Field(default_factory=list)
    compiled_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
