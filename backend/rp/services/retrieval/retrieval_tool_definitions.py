"""Pure OpenAI function-schema declarations for writer retrieval tools; no logic.

INPUT: visible tool names requested by the runtime harness.
OUTPUT: filtered OpenAI tool definitions for writer retrieval.
POS: pure tool-schema declarations for writer retrieval tools; no logic.
"""

from __future__ import annotations

from typing import Any


WRITER_RETRIEVAL_SEARCH_TOOL = "retrieval.search"
WRITER_RETRIEVAL_EXPAND_TOOL = "retrieval.expand"
WRITER_RETRIEVAL_USAGE_TOOL = "retrieval.usage"


WRITER_RETRIEVAL_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": WRITER_RETRIEVAL_SEARCH_TOOL,
            "description": (
                "Search runtime memory with a concise query and return clean RAG "
                "results. Use entity for one concrete subject; when comparing two "
                "entities, prefer separate entity searches for each entity first. "
                "Use relation for relationship questions with explicit anchors, "
                "Use semantic for abstract background, rules, or broad context."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "query": {"type": "string"},
                    "mode": {
                        "type": "string",
                        "enum": [
                            "entity",
                            "relation",
                            "semantic",
                        ],
                    },
                    "lexical_anchors": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "semantic_predicates": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": WRITER_RETRIEVAL_EXPAND_TOOL,
            "description": "Expand already returned retrieval cards by short id.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "card_short_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    }
                },
                "required": ["card_short_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": WRITER_RETRIEVAL_USAGE_TOOL,
            "description": (
                "Record which retrieval cards and expansions were used before final output."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "used_card_short_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "used_expanded_short_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "missed_query_short_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "knowledge_gaps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "gap_id": {"type": ["string", "null"]},
                                "query": {"type": "string"},
                                "status": {"type": "string"},
                                "impact": {"type": ["string", "null"]},
                                "mode_policy_resolution": {
                                    "type": ["string", "null"]
                                },
                            },
                            "required": ["query", "status"],
                        },
                    },
                },
                "required": [],
            },
        },
    },
]


def writer_retrieval_tool_definitions(
    *,
    visible_tool_names: tuple[str, ...],
) -> list[dict[str, Any]]:
    if not visible_tool_names:
        return []
    allowed = set(visible_tool_names)
    return [
        definition
        for definition in WRITER_RETRIEVAL_TOOL_DEFINITIONS
        if definition["function"]["name"] in allowed
    ]
