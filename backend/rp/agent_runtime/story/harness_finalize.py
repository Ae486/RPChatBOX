"""Story-owned harness finalize-guard contract over the generic runtime graph substrate.

INPUT: story harness final assistant text before completion.
OUTPUT: runtime-checkable finalize guard contract and decision DTO.
POS: story-zone finalize guard contract; setup-free; stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class FinalizeGuardDecision:
    allowed: bool
    reason_code: str | None = None


@runtime_checkable
class RuntimeFinalizeGuard(Protocol):
    def evaluate_final_output(self, *, assistant_text: str) -> FinalizeGuardDecision:
        ...
