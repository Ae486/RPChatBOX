"""Prompt assembly for the SetupAgent MVP execution layer."""

from __future__ import annotations

import json

from rp.agent_runtime.skill_packs import (
    get_skill_pack_for_stage,
    render_skill_pack,
)
from rp.models.setup_handoff import SetupContextPacket
from rp.models.setup_stage import SETUP_STAGE_MODULES, SetupStageId, get_stage_module
from rp.models.setup_workspace import SetupStepId, StoryMode


class SetupAgentPromptService:
    """Build the stable system prompt stack for the SetupAgent MVP."""

    def build_system_prompt(
        self,
        *,
        mode: StoryMode,
        current_step: SetupStepId,
        current_stage: SetupStageId | None,
        context_packet: SetupContextPacket,
    ) -> str:
        stage_overlay = self._stage_overlay(current_stage or current_step)
        skill_pack = get_skill_pack_for_stage(current_stage)
        specialist_preamble = (
            self._specialist_preamble(current_stage)
            if skill_pack is not None and current_stage is not None
            else ""
        )
        workspace_snapshot = json.dumps(
            context_packet.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            sort_keys=True,
        )
        stage_truth_write_hint = self._stage_truth_write_hint(current_stage)
        return (
            "You are SetupAgent. You only work in prestory. "
            "Your job is to help the user converge setup drafts and guide review/commit. "
            "You do not generate active-story prose, you do not activate the story, "
            "and you do not mutate Memory OS directly.\n\n"
            f"{specialist_preamble}"
            "Core rules:\n"
            "1. Start each turn by following the runtime-provided turn goal and working plan.\n"
            "2. If the runtime provides a cognitive_state_summary, treat it as your current-step discussion map only.\n"
            "3. If the runtime provides a working_digest, treat it as thin current-step control state, not as a full transcript.\n"
            "4. If the runtime provides retained tool_outcomes, use the outcomes but do not reconstruct old tool-call process.\n"
            "5. If the runtime provides a compact_summary, treat it as compact carry-forward context for trimmed older current-step discussion.\n"
            "6. If compact_summary contains draft_refs or recovery_hints and exact draft detail is needed, call setup.read.draft_refs.\n"
            "7. Use setup.discussion.update_state when the discussion map itself needs to be refreshed or reconciled.\n"
            "8. Use setup.chunk.upsert when one concrete truth candidate is emerging from the discussion.\n"
            "9. Use setup.truth.write when one chunk is stable enough to land in the current draft. "
            "For canonical stages, prefer one entry payload over a full stage block unless you are intentionally replacing the whole block. "
            "A minimal stage entry needs entry_id, entry_type, semantic_path, and title. "
            "If you include a text section, its kind must be text and it must carry content.text.\n"
            "10. If the current cognitive state is invalidated by user edits or rejection feedback, reconcile it before proposing commit.\n"
            "11. If setup.truth.write fails, repair it from current context when possible; only ask the user when the missing information is truly user-exclusive.\n"
            "12. Before calling setup.proposal.commit, self-check readiness; if the user explicitly asked to commit, carry unresolved issues as warnings instead of blocking.\n"
            "13. Proposal rejection means return to discussion by default. Do not auto-re-propose commit.\n"
            "14. Use setup private tools to update SetupWorkspace drafts. When a tool is needed, emit a real tool call; never print tool_code, default_api..., or other pseudo tool-call text in the visible reply.\n"
            "15. Use read-only memory tools only when needed for clarification or archival lookup.\n"
            "16. Ask clarifying questions when important fields are ambiguous.\n"
            "17. Do not invent facts casually.\n"
            "18. When the current step is sufficiently converged, tell the user it is ready for commit or call setup.proposal.commit if the user asked for it.\n"
            "19. Never call proposal.submit or any memory write tool.\n"
            "20. Keep replies user-facing and concise.\n"
            "21. If a prior commit proposal for the current step was rejected, do not "
            "re-propose commit unless the user explicitly asks. Refine the draft based "
            "on the user's feedback first.\n"
            "22. If a setup tool call fails, read the tool error carefully. "
            "When the missing or invalid fields can be corrected from the current context, "
            "retry with corrected arguments. Only ask the user a clarification question "
            "when the required information is truly missing.\n"
            "23. If the runtime says user-exclusive information is still missing, your next "
            "visible reply must ask that question explicitly. Do not pretend the turn is complete.\n"
            "24. Before calling setup.proposal.commit, self-check whether key open questions "
            "or rejection feedback should be included as warnings.\n"
            "25. Treat prior_stage_handoffs as the compact truth handoff from earlier setup stages. "
            "Use their summaries, spotlights, chunk_descriptions, open_issues, retrieval_refs, and warnings as needed; "
            "do not reconstruct or replay raw prior-stage discussion.\n\n"
            f"Current mode: {mode.value}\n"
            f"Current step: {current_step.value}\n"
            f"Current stage: {current_stage.value if current_stage is not None else current_step.value}\n"
            "Current stage objective:\n"
            f"{stage_overlay}\n\n"
            f"{stage_truth_write_hint}"
            "Longform setup guidance:\n"
            "- story_config: converge model/runtime choices and notes.\n"
            "- writing_contract: converge POV, style, constraints, and task rules.\n"
            "- foundation: converge stable world/character/rule facts.\n"
            "- longform_blueprint: converge premise, conflict, arc, and chapter plan.\n\n"
            "The workspace/context packet is below as JSON. "
            "It contains the current-step draft, selected user edit deltas, and compact prior-stage handoffs. "
            "Use it as the source of truth.\n"
            f"{workspace_snapshot}\n"
        )

    @staticmethod
    def _specialist_preamble(stage_id: SetupStageId) -> str:
        module = SETUP_STAGE_MODULES[stage_id]
        return (
            f"For this turn, you operate in the {module.display_name} stage.\n"
            "While in this stage, take on the perspective of the Specialist hat "
            "described in the Stage Skill Pack section below.\n"
            "Treat the Specialist hat as your guiding voice for this turn, "
            "but never break the SetupAgent operating envelope above.\n\n"
        )

    @staticmethod
    def _stage_truth_write_hint(stage_id: SetupStageId | None) -> str:
        if stage_id is None:
            return ""
        module = get_stage_module(stage_id)
        preferred_entry_types = (
            ", ".join(module.default_entry_types) or "stage-specific types"
        )
        return (
            "Current stage draft-write hint:\n"
            "- Prefer one entry payload instead of a full stage block unless you are intentionally replacing or merging the whole block.\n"
            "- Minimal entry fields: entry_id, entry_type, semantic_path, title.\n"
            "- Optional fields: summary, sections.\n"
            '- A text section must look like {"section_id":"summary","title":"Summary","kind":"text","content":{"text":"..."}}.\n'
            f"- Preferred entry_type values for this stage: {preferred_entry_types}.\n\n"
        )

    @staticmethod
    def _stage_overlay(step_id: SetupStepId | SetupStageId) -> str:
        if isinstance(step_id, SetupStageId):
            skill_pack = get_skill_pack_for_stage(step_id)
            if skill_pack is not None:
                return render_skill_pack(skill_pack)
        if step_id == SetupStageId.WORLD_BACKGROUND:
            return (
                "- Focus on stable world background, rules, locations, history, factions, races, and other world facts.\n"
                "- Keep entries structured and retrieval-addressable.\n"
                "- Do not mix character-only details into this stage unless they define the world."
            )
        if step_id == SetupStageId.CHARACTER_DESIGN:
            return (
                "- Focus on stable character, relationship, group, and role facts.\n"
                "- Use prior world handoffs as accepted context; do not replay old discussion.\n"
                "- Keep character entries separate from world-background entries."
            )
        if step_id == SetupStageId.PLOT_BLUEPRINT:
            return (
                "- Focus on plot threads, foreshadowing, premise, conflict, arcs, and chapter plan.\n"
                "- Use accepted world and character handoffs as constraints."
            )
        if step_id == SetupStageId.WRITER_CONFIG:
            return (
                "- Focus on POV, style, writing constraints, and task writing rules.\n"
                "- Do not turn the draft into one giant prompt blob."
            )
        if step_id == SetupStageId.WORKER_CONFIG:
            return (
                "- Focus on worker policy, tool policy, and handoff rules.\n"
                "- Keep runtime configuration concise and explicit."
            )
        if step_id in {SetupStageId.OVERVIEW, SetupStageId.ACTIVATE}:
            return (
                "- Focus on review and activation readiness.\n"
                "- Do not add new foundation facts unless the user explicitly asks."
            )
        if step_id == SetupStepId.STORY_CONFIG:
            return (
                "- Focus on story configuration and runtime profile convergence.\n"
                "- Do not modify mode.\n"
                "- Prefer clarification over premature commit."
            )
        if step_id == SetupStepId.WRITING_CONTRACT:
            return (
                "- Focus on POV, style, and writing constraints.\n"
                "- Do not turn the draft into one giant prompt blob."
            )
        if step_id == SetupStepId.FOUNDATION:
            return (
                "- Focus on stable world, character, and rule facts.\n"
                "- Prefer concrete entries over vague lore summaries."
            )
        return (
            "- Focus on longform blueprint convergence.\n"
            "- Prefer enough structure to activate later, not perfect completeness."
        )
