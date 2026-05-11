"""WritingWorker execution on top of the existing LiteLLM stack."""

from __future__ import annotations

import json
from typing import AsyncIterator

from models.chat import ChatMessage
from rp.models.worker_memory import WorkerSourceRefBundle
from rp.services.runtime_retrieval_card_service import RuntimeRetrievalCardService
from rp.models.writing_worker_contracts import (
    WritingWorkerExecutionRequest,
    WritingWorkerExecutionResult,
)
from rp.models.writing_runtime import WritingPacket
from .story_llm_gateway import StoryLlmGateway
from .writing_worker_retrieval_loop_service import (
    WritingWorkerRetrievalLoopService,
)


class WritingWorkerExecutionService:
    """Render a WritingPacket into prompts and execute the writer transport."""

    def __init__(
        self,
        *,
        llm_gateway: StoryLlmGateway | None = None,
        runtime_retrieval_card_service: RuntimeRetrievalCardService | None = None,
    ) -> None:
        self._llm_gateway = llm_gateway or StoryLlmGateway()
        self._runtime_retrieval_card_service = runtime_retrieval_card_service

    async def run(
        self,
        *,
        packet: WritingPacket,
        model_id: str,
        provider_id: str | None,
    ) -> str:
        request = self.build_request(
            packet=packet,
            model_id=model_id,
            provider_id=provider_id,
            request_id=f"writer-exec:{packet.packet_id}",
        )
        result = await self.execute(request=request)
        return result.output_text

    def build_request(
        self,
        *,
        packet: WritingPacket,
        model_id: str,
        provider_id: str | None,
        request_id: str,
    ) -> WritingWorkerExecutionRequest:
        return WritingWorkerExecutionRequest(
            request_id=request_id,
            identity=packet.identity,
            operation_mode=packet.operation_mode,
            packet_ref=str(packet.metadata.get("runtime_workspace_packet_material_id") or "")
            or None,
            packet=packet,
            writer_model_id=model_id,
            writer_provider_id=provider_id,
            retrieval_allowed=self._default_retrieval_allowed(packet=packet),
            max_retrieval_attempts=self._default_max_retrieval_attempts(packet=packet),
        )

    async def execute(
        self,
        *,
        request: WritingWorkerExecutionRequest,
    ) -> WritingWorkerExecutionResult:
        messages = self._render_messages(request.packet)
        metadata_json = {
            **dict(request.metadata_json),
            "writer_model_id": request.writer_model_id,
            "writer_provider_id": request.writer_provider_id,
            "packet_ref": request.packet_ref,
        }
        if self._should_use_retrieval_loop(request=request):
            identity = request.identity
            if identity is None:
                raise ValueError("Runtime identity is required for retrieval loop")
            loop_result = await self._retrieval_loop().run(
                identity=identity,
                model_id=request.writer_model_id,
                provider_id=request.writer_provider_id,
                messages=messages,
                max_retrieval_attempts=request.max_retrieval_attempts,
                temperature=0.7,
                max_tokens=1600,
            )
            text = loop_result.output_text
            usage_metadata = loop_result.usage_metadata
            writer_tool_trace_refs = list(loop_result.tool_trace_refs)
            retrieval_source_ref_bundle = loop_result.source_ref_bundle
            metadata_json["retrieval_loop_mode"] = "bounded_tool_loop"
        else:
            text, usage_metadata = await self._llm_gateway.complete_text_with_usage(
                model_id=request.writer_model_id,
                provider_id=request.writer_provider_id,
                messages=messages,
                temperature=0.7,
                max_tokens=1600,
            )
            writer_tool_trace_refs = []
            retrieval_source_ref_bundle = self._packet_source_ref_bundle(
                packet=request.packet
            )
            metadata_json["retrieval_loop_mode"] = "disabled"
        turn_id = request.identity.turn_id if request.identity is not None else None
        return WritingWorkerExecutionResult(
            request_id=request.request_id,
            packet_id=request.packet.packet_id,
            turn_id=turn_id,
            operation_mode=request.operation_mode,
            output_text=text,
            output_kind=request.packet.output_kind,
            usage_metadata=usage_metadata,
            writer_tool_trace_refs=writer_tool_trace_refs,
            retrieval_source_ref_bundle=retrieval_source_ref_bundle,
            result_status="completed",
            metadata_json=metadata_json,
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

    def should_buffer_stream(
        self,
        *,
        packet: WritingPacket,
        model_id: str,
        provider_id: str | None,
    ) -> bool:
        request = self.build_request(
            packet=packet,
            model_id=model_id,
            provider_id=provider_id,
            request_id=f"writer-stream-check:{packet.packet_id}",
        )
        return self._should_use_retrieval_loop(request=request)

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

    def _should_use_retrieval_loop(
        self,
        *,
        request: WritingWorkerExecutionRequest,
    ) -> bool:
        if request.identity is None:
            return False
        if not request.retrieval_allowed or request.max_retrieval_attempts <= 0:
            return False
        if self._runtime_retrieval_card_service is None:
            return False
        supports_tools = getattr(self._llm_gateway, "supports_tools", None)
        if not callable(supports_tools):
            return False
        return bool(
            supports_tools(
                model_id=request.writer_model_id,
                provider_id=request.writer_provider_id,
            )
        )

    def _retrieval_loop(self) -> WritingWorkerRetrievalLoopService:
        runtime_retrieval_card_service = self._runtime_retrieval_card_service
        if runtime_retrieval_card_service is None:
            raise ValueError("Runtime retrieval card service is required")
        return WritingWorkerRetrievalLoopService(
            llm_gateway=self._llm_gateway,
            runtime_retrieval_card_service=runtime_retrieval_card_service,
        )

    @staticmethod
    def _packet_source_ref_bundle(
        *,
        packet: WritingPacket,
    ) -> WorkerSourceRefBundle:
        payload = packet.metadata.get("worker_source_ref_bundle")
        if isinstance(payload, dict):
            return WorkerSourceRefBundle.model_validate(payload)
        return WorkerSourceRefBundle()

    @staticmethod
    def _default_retrieval_allowed(*, packet: WritingPacket) -> bool:
        configured = packet.metadata.get("writer_retrieval_allowed")
        if isinstance(configured, bool):
            return configured
        return False

    @classmethod
    def _default_max_retrieval_attempts(cls, *, packet: WritingPacket) -> int:
        configured = packet.metadata.get("writer_max_retrieval_attempts")
        if isinstance(configured, int):
            return max(0, min(configured, 3))
        return 2 if cls._default_retrieval_allowed(packet=packet) else 0

    @staticmethod
    def _render_messages(packet: WritingPacket) -> list[ChatMessage]:
        system_prompt = "\n\n".join(section for section in packet.system_sections if section)
        context_blocks = []
        context_sections = packet.context_sections or packet.flattened_context_sections()
        for section in context_sections:
            label = section.get("label")
            items = section.get("items") or []
            if not items:
                continue
            context_blocks.append(
                f"{label}:\n" + "\n".join(f"- {item}" for item in items)
            )
        mandatory_rewrite_instruction = ""
        if packet.operation_mode == "rewrite" and packet.review_overlay_sections:
            mandatory_rewrite_instruction = str(
                packet.metadata.get("mandatory_rewrite_instruction") or ""
            ).strip() or (
                "Mandatory rewrite instruction:\n"
                "- Apply every listed review constraint exactly.\n"
                "- Treat active comments and tracked changes as required edits.\n"
                "- Do not ignore or soften the requested changes."
            )
        user_prompt = "\n\n".join(
            block
            for block in (
                f"output_kind: {packet.output_kind}",
                f"phase: {packet.phase}",
                "\n\n".join(context_blocks),
                mandatory_rewrite_instruction,
                f"user_instruction:\n{packet.user_instruction}",
            )
            if block
        )
        return [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]
