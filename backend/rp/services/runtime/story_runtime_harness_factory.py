"""Factory wiring the kernel-graph StoryHarness for writer retrieval.

INPUT: runtime identity, story llm gateway, retrieval card service, and writer model config.
OUTPUT: a StoryHarness driven by the runtime model gateway plus its retrieval tool provider.
POS: production wiring for the writer-retrieval harness; setup-free; reuses committed ports.
"""

from __future__ import annotations

from rp.agent_runtime.story.story_harness import StoryHarness, StoryHarnessProfile
from rp.models.memory.contract_registry import MemoryRuntimeIdentity
from rp.services.retrieval.retrieval_tool_definitions import (
    WRITER_RETRIEVAL_EXPAND_TOOL,
    WRITER_RETRIEVAL_SEARCH_TOOL,
    WRITER_RETRIEVAL_USAGE_TOOL,
)
from rp.services.retrieval.runtime_card_service import RuntimeRetrievalCardService
from rp.services.retrieval.runtime_retrieval_tool_provider import (
    RuntimeRetrievalToolProvider,
)
from rp.services.story.llm_gateway import StoryLlmGateway
from rp.services.story.runtime_model_gateway import RuntimeStoryModelGateway


def build_writer_retrieval_harness(
    *,
    identity: MemoryRuntimeIdentity,
    llm_gateway: StoryLlmGateway,
    runtime_retrieval_card_service: RuntimeRetrievalCardService,
    model_id: str,
    provider_id: str | None,
    max_retrieval_attempts: int,
    temperature: float | None,
    max_tokens: int | None,
    include_reasoning: bool | None = None,
) -> tuple[StoryHarness, RuntimeRetrievalToolProvider]:
    """Wire a kernel-graph harness for the bounded writer-retrieval loop."""

    provider = RuntimeRetrievalToolProvider(
        identity=identity,
        runtime_retrieval_card_service=runtime_retrieval_card_service,
        max_retrieval_attempts=max_retrieval_attempts,
    )
    model_gateway = RuntimeStoryModelGateway(
        llm_gateway=llm_gateway,
        model_id=model_id,
        provider_id=provider_id,
        temperature=temperature,
        max_tokens=max_tokens,
        include_reasoning=include_reasoning,
    )
    profile = StoryHarnessProfile(
        profile_id="writer-retrieval",
        visible_tool_names=(
            WRITER_RETRIEVAL_SEARCH_TOOL,
            WRITER_RETRIEVAL_EXPAND_TOOL,
            WRITER_RETRIEVAL_USAGE_TOOL,
        ),
        max_rounds=max(4, (max_retrieval_attempts * 3) + 1),
    )
    harness = StoryHarness(
        profile=profile,
        model_gateway=model_gateway,
        tool_executor=provider,
        finalize_guard=provider,
    )
    return harness, provider
