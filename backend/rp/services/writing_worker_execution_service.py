"""WritingWorker execution on top of the existing LiteLLM stack."""

from __future__ import annotations

import json
from typing import AsyncIterator

from models.chat import ChatMessage
from rp.models.writing_runtime import WritingPacket
from .story_llm_gateway import StoryLlmGateway


class WritingWorkerExecutionService:
    """Render a WritingPacket into prompts and execute the writer model."""

    def __init__(self, *, llm_gateway: StoryLlmGateway | None = None) -> None:
        self._llm_gateway = llm_gateway or StoryLlmGateway()

    async def run(
        self,
        *,
        packet: WritingPacket,
        model_id: str,
        provider_id: str | None,
    ) -> str:
        return await self._llm_gateway.complete_text(
            model_id=model_id,
            provider_id=provider_id,
            messages=self._render_messages(packet),
            temperature=0.7,
            max_tokens=1600,
        )

    async def run_stream(
        self,
        *,
        packet: WritingPacket,
        model_id: str,
        provider_id: str | None,
    ) -> AsyncIterator[str]:
        async for line in self._llm_gateway.stream_text(
            model_id=model_id,
            provider_id=provider_id,
            messages=self._render_messages(packet),
            temperature=0.7,
            max_tokens=1600,
        ):
            yield line

    @staticmethod
    def extract_text_delta(line: str) -> str:
        raw = line.strip()
        if not raw.startswith("data: "):
            return ""
        payload = raw[6:]
        if payload == "[DONE]":
            return ""
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return ""
        if parsed.get("type") == "text_delta":
            return str(parsed.get("delta") or "")
        return ""

    @staticmethod
    def _render_messages(packet: WritingPacket) -> list[ChatMessage]:
        system_prompt = "\n\n".join(section for section in packet.system_sections if section)
        context_blocks = []
        for section in packet.context_sections:
            label = section.get("label")
            items = section.get("items") or []
            if not items:
                continue
            context_blocks.append(
                f"{label}:\n" + "\n".join(f"- {item}" for item in items)
            )
        user_prompt = "\n\n".join(
            block
            for block in (
                f"output_kind: {packet.output_kind}",
                f"phase: {packet.phase}",
                "\n\n".join(context_blocks),
                f"user_instruction:\n{packet.user_instruction}",
            )
            if block
        )
        return [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]
