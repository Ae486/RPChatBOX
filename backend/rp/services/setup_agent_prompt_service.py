"""Prompt assembly for the SetupAgent MVP execution layer."""

from __future__ import annotations

import json

from rp.agent_runtime.contracts import SetupCapabilityPlan
from rp.agent_runtime.profiles import build_setup_agent_capability_plan
from rp.agent_runtime.skill_packs import (
    get_skill_pack_for_stage,
    render_skill_pack,
)
from rp.models.setup_handoff import SetupContextPacket
from rp.models.setup_stage import SETUP_STAGE_MODULES, SetupStageId
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
        capability_plan: SetupCapabilityPlan | None = None,
    ) -> str:
        capability_plan = capability_plan or build_setup_agent_capability_plan(
            current_step.value,
            current_stage=current_stage.value if current_stage is not None else None,
        )
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
        capability_guidance = self._capability_guidance(capability_plan)
        return (
            "You are SetupAgent. You only work in prestory. "
            "Your job is to help the user converge setup drafts and guide review/commit. "
            "You do not generate active-story prose, you do not activate the story, "
            "and you do not mutate Memory OS directly.\n\n"
            f"{specialist_preamble}"
            "Core rules:\n"
            "1. Start each turn by following the runtime-provided turn goal and working plan.\n"
            "2. Use runtime overlay material as turn-local execution guidance only; "
            "do not treat it as workspace truth or replay old tool-call process.\n"
            "3. Treat compact carry-forward context as a thin recovery aid for "
            "trimmed older current-step discussion, not as a replacement for drafts.\n"
            "4. If the current cognitive state is invalidated by user edits or rejection feedback, reconcile it before proposing commit.\n"
            "5. Proposal rejection means return to discussion by default. Do not auto-re-propose commit.\n"
            "6. When a tool is needed, emit a real tool call; never print tool_code, default_api..., or other pseudo tool-call text in the visible reply.\n"
            "7. Ask clarifying questions when important fields are ambiguous.\n"
            "8. Do not invent facts casually.\n"
            "9. Keep replies user-facing and concise.\n"
            "10. If a prior commit proposal for the current step was rejected, do not "
            "re-propose commit unless the user explicitly asks. Refine the draft based "
            "on the user's feedback first.\n"
            "11. If a setup tool call fails, read the tool error carefully. "
            "When the missing or invalid fields can be corrected from the current context, "
            "retry with corrected arguments. Only ask the user a clarification question "
            "when the required information is truly missing.\n"
            "12. If the runtime says user-exclusive information is still missing, your next "
            "visible reply must ask that question explicitly. Do not pretend the turn is complete.\n"
            "13. Treat prior_stage_handoffs as the compact truth handoff from earlier setup stages. "
            "Use their summaries, spotlights, chunk_descriptions, open_issues, retrieval_refs, and warnings as needed; "
            "do not reconstruct or replay raw prior-stage discussion.\n"
            "14. Do not call tools outside the current active capability plan.\n\n"
            "Active capability guidance:\n"
            f"{capability_guidance}\n\n"
            f"Current mode: {mode.value}\n"
            f"Current step: {current_step.value}\n"
            f"Current stage: {current_stage.value if current_stage is not None else current_step.value}\n"
            "Current stage objective:\n"
            f"{stage_overlay}\n\n"
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
    def _capability_guidance(capability_plan: SetupCapabilityPlan) -> str:
        active_tools = set(capability_plan.active_tool_names)
        fragments = [
            f"- {fragment.text}"
            for fragment in capability_plan.prompt_guidance_fragments
            if fragment.text.strip()
            and set(fragment.tool_names).issubset(active_tools)
        ]
        if not fragments:
            return "- No setup tools are active for this turn; continue with visible text only."
        return "\n".join(fragments)

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
