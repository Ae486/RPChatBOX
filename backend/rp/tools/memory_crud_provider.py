"""Backend-local provider exposing RP memory CRUD tools."""
from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from models.mcp_config import McpToolInfo
from rp.models.memory_crud import (
    MemoryGetStateInput,
    MemoryGetSummaryInput,
    MemoryListVersionsInput,
    MemoryReadProvenanceInput,
    MemorySearchArchivalInput,
    MemorySearchRecallInput,
    ProposalSubmitInput,
)
from rp.services.memory_crud_serialization_service import MemoryCrudSerializationService
from rp.services.memory_crud_validation_service import MemoryCrudValidationService
from rp.services.memory_os_service import MemoryOsService
from rp.services.proposal_service import ProposalService


class MemoryCrudToolProvider:
    """Expose Phase A memory CRUD/query/proposal tools via McpManager."""

    def __init__(
        self,
        *,
        memory_os_service: MemoryOsService | None = None,
        proposal_service: ProposalService | None = None,
        validation_service: MemoryCrudValidationService | None = None,
        serialization_service: MemoryCrudSerializationService | None = None,
        allowed_tools: set[str] | None = None,
        provider_id: str = "rp_memory",
        server_name: str = "RP Memory",
    ) -> None:
        self.provider_id = provider_id
        self.server_name = server_name
        self._memory_os_service = memory_os_service or MemoryOsService()
        self._proposal_service = proposal_service or ProposalService()
        self._validation_service = validation_service or MemoryCrudValidationService()
        self._serialization_service = (
            serialization_service or MemoryCrudSerializationService()
        )
        self._allowed_tools = set(allowed_tools) if allowed_tools is not None else None
        self._schemas = {
            "memory.get_state": MemoryGetStateInput,
            "memory.get_summary": MemoryGetSummaryInput,
            "memory.search_recall": MemorySearchRecallInput,
            "memory.search_archival": MemorySearchArchivalInput,
            "proposal.submit": ProposalSubmitInput,
            "memory.list_versions": MemoryListVersionsInput,
            "memory.read_provenance": MemoryReadProvenanceInput,
        }

    def list_tools(self) -> list[McpToolInfo]:
        tool_specs = [
            McpToolInfo(
                server_id=self.provider_id,
                server_name=self.server_name,
                name=tool_name,
                description=description,
                input_schema=model.model_json_schema(),
            )
            for tool_name, description, model in (
                ("memory.get_state", "Read authoritative state for a coarse memory domain.", MemoryGetStateInput),
                ("memory.get_summary", "Read summary/projection entries for one or more domains.", MemoryGetSummaryInput),
                ("memory.search_recall", "Search recall memory using the unified retrieval surface.", MemorySearchRecallInput),
                ("memory.search_archival", "Search archival knowledge using the unified retrieval surface.", MemorySearchArchivalInput),
                ("proposal.submit", "Submit a pending state patch proposal without applying it.", ProposalSubmitInput),
                ("memory.list_versions", "List versions for a memory object reference.", MemoryListVersionsInput),
                ("memory.read_provenance", "Read provenance references for a memory object.", MemoryReadProvenanceInput),
            )
        ]
        if self._allowed_tools is None:
            return tool_specs
        return [tool for tool in tool_specs if tool.name in self._allowed_tools]

    async def call_tool(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        model = self._schemas.get(tool_name)
        if model is None:
            return {
                "success": False,
                "content": self._serialization_service.serialize_error(
                    code="unknown_tool",
                    message=f"Unknown local tool: {tool_name}",
                ),
                "error_code": "UNKNOWN_TOOL",
            }

        try:
            input_model = model.model_validate(arguments)
            result = await self._dispatch(tool_name=tool_name, input_model=input_model)
            return {
                "success": True,
                "content": self._serialization_service.serialize_result(result),
                "error_code": None,
            }
        except ValidationError as exc:
            return {
                "success": False,
                "content": self._serialization_service.serialize_error(
                    code="schema_validation_failed",
                    message="Tool arguments failed validation",
                    details={"errors": exc.errors()},
                ),
                "error_code": "SCHEMA_VALIDATION_FAILED",
            }
        except ValueError as exc:
            return {
                "success": False,
                "content": self._serialization_service.serialize_error(
                    code="validation_failed",
                    message=str(exc),
                ),
                "error_code": "VALIDATION_FAILED",
            }
        except Exception as exc:  # pragma: no cover - defensive surface
            return {
                "success": False,
                "content": self._serialization_service.serialize_error(
                    code="execution_error",
                    message=f"Tool execution failed: {exc}",
                ),
                "error_code": "EXECUTION_ERROR",
            }

    async def _dispatch(self, *, tool_name: str, input_model: Any) -> Any:
        if tool_name == "memory.get_state":
            self._validation_service.validate_get_state(input_model)
            return await self._memory_os_service.get_state(input_model)
        if tool_name == "memory.get_summary":
            self._validation_service.validate_get_summary(input_model)
            return await self._memory_os_service.get_summary(input_model)
        if tool_name == "memory.search_recall":
            self._validation_service.validate_search_recall(input_model)
            return await self._memory_os_service.search_recall(input_model)
        if tool_name == "memory.search_archival":
            self._validation_service.validate_search_archival(input_model)
            return await self._memory_os_service.search_archival(input_model)
        if tool_name == "proposal.submit":
            self._validation_service.validate_proposal_submit(input_model)
            return await self._proposal_service.submit(input_model)
        if tool_name == "memory.list_versions":
            self._validation_service.validate_list_versions(input_model)
            return await self._memory_os_service.list_versions(input_model)
        if tool_name == "memory.read_provenance":
            self._validation_service.validate_read_provenance(input_model)
            return await self._memory_os_service.read_provenance(input_model)
        raise ValueError(f"Unknown local tool: {tool_name}")
