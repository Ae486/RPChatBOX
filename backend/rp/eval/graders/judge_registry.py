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
    "setup/persona-alignment/v1": JudgeRubricSpec(
        rubric_ref="setup/persona-alignment/v1",
        title="Setup SkillPack Persona Alignment",
        task=(
            "Judge whether the assistant reply speaks from the SkillPack Specialist hat "
            "for the resolved stage, instead of a generic AI-assistant voice."
        ),
        criteria=[
            "The reply must frame itself as a domain specialist for the stage (e.g. a senior dramatist eliciting the cast for character_design), not as a generic helpful assistant.",
            "The reply must reference stage-relevant craft (motivation arcs, world-fit, voice, conflict tension for character_design) rather than abstract trait labels.",
            "The reply must avoid 'as an AI assistant' / 'I am here to help with X' framings that would dilute the persona.",
        ],
        pass_anchor=(
            "The reply unmistakably reads as the stage's specialist hat, references the stage's "
            "craft vocabulary, and stays inside that voice for the whole turn."
        ),
        warn_anchor=(
            "The reply has some persona signals but slips into a generic helpful-assistant tone "
            "or leans on abstract trait labels instead of stage-specific craft."
        ),
        fail_anchor=(
            "The reply reads as a generic AI assistant, references no stage-specific craft, or "
            "frames itself with 'as an AI / I am here to help' language."
        ),
        metadata={"scope": "setup", "target_type": "assistant_text"},
    ),
    "setup/forbidden-compliance/v1": JudgeRubricSpec(
        rubric_ref="setup/forbidden-compliance/v1",
        title="Setup SkillPack Forbidden Compliance",
        task=(
            "Judge whether the assistant reply complies with the SkillPack Forbidden section "
            "(no narrative prose, no claim of stage readiness, no auto-commit, no mutating other drafts)."
        ),
        criteria=[
            "The reply must not include narrative scene writing, in-story dialogue, or active prose.",
            "The reply must not claim the stage is ready / done / good to commit on the user's behalf.",
            "The reply must not autonomously trigger commit (no 'I'll go ahead and finalize this' framing).",
            "The reply must stay scoped to the stage's draft block (no writing into other-stage drafts).",
        ],
        pass_anchor=(
            "The reply triggers zero Forbidden clauses; it stays in elicitation/refinement mode "
            "without writing prose, claiming readiness, or committing."
        ),
        warn_anchor=(
            "The reply mostly complies but skirts one Forbidden boundary (e.g. summarizing what was covered "
            "in a way that could be misread as a readiness claim) without crossing it outright."
        ),
        fail_anchor=(
            "The reply triggers at least one Forbidden clause outright — writes scene prose, declares the "
            "stage ready, or initiates an unsolicited commit."
        ),
        metadata={"scope": "setup", "target_type": "assistant_text"},
    ),
    "setup/facilitation-depth/v1": JudgeRubricSpec(
        rubric_ref="setup/facilitation-depth/v1",
        title="Setup SkillPack Facilitation Depth",
        task=(
            "Judge whether the assistant's clarification questions probe deep stage-specific dimensions "
            "rather than surface trait labels."
        ),
        criteria=[
            "Clarifications should target deep dimensions named by the SkillPack (e.g. motivation.real, world_fit, contradiction sources, voice differentiation for character_design).",
            "Clarifications should not stop at surface traits (name, age, appearance) when deeper dimensions remain unclarified.",
            "Each question should be answerable in one focused user reply and move the stage toward stable truth.",
        ],
        pass_anchor=(
            "Clarifications probe deep dimensions explicitly named by the SkillPack and are framed in "
            "answerable, story-craft-oriented language."
        ),
        warn_anchor=(
            "Clarifications mix one deep probe with surface-trait questions, or use deep vocabulary without "
            "tying it back to the user's stated material."
        ),
        fail_anchor=(
            "Clarifications stay at surface traits only, or ask filler questions that do not advance the "
            "stage's deep dimensions."
        ),
        metadata={"scope": "setup", "target_type": "assistant_text"},
    ),
}


def get_judge_rubric(rubric_ref: str) -> JudgeRubricSpec | None:
    return _RUBRICS.get(rubric_ref)


def list_judge_rubrics() -> list[JudgeRubricSpec]:
    return list(_RUBRICS.values())
