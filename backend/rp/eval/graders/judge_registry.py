"""Structured registry for RP eval subjective judge rubrics."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JudgeRubricSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rubric_ref: str
    judge_family: str = "llm_judge"
    title: str
    task: str
    criteria: list[str] = Field(default_factory=list)
    pass_anchor: str
    warn_anchor: str
    fail_anchor: str
    prompt_version: str = "llm-judge/v2"
    response_schema_version: str = "judge-response/v2"
    score_bands: dict[str, list[float]] = Field(
        default_factory=lambda: {
            "pass": [0.8, 1.0],
            "warn": [0.4, 0.79],
            "fail": [0.0, 0.39],
        }
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


_RUBRICS: dict[str, JudgeRubricSpec] = {
    "setup/clarification-quality/v1": JudgeRubricSpec(
        rubric_ref="setup/clarification-quality/v1",
        title="Setup Clarification Quality",
        task=(
            "Judge whether the assistant asked a targeted clarification question "
            "that directly helps setup convergence."
        ),
        criteria=[
            "The question should target missing user intent or constraints, not ask filler questions.",
            "It should avoid premature review or commit language when information is still missing.",
            "It should be actionable for the user to answer in one short response.",
        ],
        pass_anchor="The clarification is specific, necessary, and clearly moves setup toward readiness.",
        warn_anchor="The clarification is partially relevant but vague, repetitive, or missing one key angle.",
        fail_anchor="The clarification is filler, premature, or does not help setup converge.",
        metadata={"scope": "setup", "target_type": "assistant_text"},
    ),
    "retrieval/query-quality/v1": JudgeRubricSpec(
        rubric_ref="retrieval/query-quality/v1",
        title="Retrieval Query Quality",
        task=(
            "Judge whether the retrieval query is specific, relevant, and likely to retrieve "
            "useful RP context."
        ),
        criteria=[
            "The query should mention concrete story concepts instead of generic filler terms.",
            "It should be neither too broad nor too narrow for retrieval.",
            "It should align with the intended retrieval target and be useful for downstream generation.",
        ],
        pass_anchor="The query is concrete, discriminative, and well aligned with the intended retrieval target.",
        warn_anchor="The query is relevant but could be sharpened with more discriminative concepts or scope control.",
        fail_anchor="The query is too vague, misaligned, or unlikely to retrieve useful RP context.",
        metadata={"scope": "retrieval", "target_type": "query_text"},
    ),
    "activation/handoff-quality/v1": JudgeRubricSpec(
        rubric_ref="activation/handoff-quality/v1",
        title="Activation Handoff Quality",
        task=(
            "Judge whether the activation handoff contains a coherent and usable runtime seed "
            "for starting the story session."
        ),
        criteria=[
            "The handoff should include concrete runtime story config and writer contract data, not placeholders.",
            "It should reference the necessary setup outputs for foundation and blueprint continuity.",
            "It should look sufficient for the runtime to bootstrap the first chapter without obvious missing essentials.",
        ],
        pass_anchor="The handoff is coherent, concrete, and looks sufficient to bootstrap runtime safely.",
        warn_anchor="The handoff is mostly usable but has notable omissions, ambiguity, or weak continuity references.",
        fail_anchor="The handoff is incomplete, placeholder-heavy, or not usable for runtime bootstrap.",
        metadata={"scope": "activation", "target_type": "activation_handoff"},
    ),
}


def get_judge_rubric(rubric_ref: str) -> JudgeRubricSpec | None:
    return _RUBRICS.get(rubric_ref)


def list_judge_rubrics() -> list[JudgeRubricSpec]:
    return list(_RUBRICS.values())
