"""Model-free query analysis helpers for structured retrieval.

The retrieval layer mostly searches structured RP/setup material where entity
names, section labels, and intent words are first-class signals.  This module
keeps that analysis deterministic so sparse retrieval can use the structure
without adding an LLM rewrite step or dataset-specific rules.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

_ASCII_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+", re.UNICODE)
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]{2,}")
_CJK_SPLIT_RE = re.compile(r"[和与及跟同对给在是为有把将由从到的了着过中里上下一些以及、，。！？；：\s]+")

_INTENT_TERMS: dict[str, tuple[str, ...]] = {
    "relationship": (
        "关系",
        "关联",
        "互动",
        "羁绊",
        "同盟",
        "敌对",
        "搭档",
        "亲属",
        "阵营",
    ),
    "appearance": ("外貌", "长相", "样貌", "衣着", "装束", "形象", "特征"),
    "speech": ("说话", "口癖", "语气", "台词", "称呼", "表达", "语言"),
    "history": ("经历", "过去", "历史", "背景", "来历", "前史", "回忆"),
    "weakness": ("弱点", "缺陷", "限制", "代价", "短板", "禁忌"),
    "motivation": ("动机", "目标", "愿望", "执念", "目的", "追求"),
    "rule": ("规则", "设定", "机制", "限制", "条件", "法则"),
}

_QUESTION_STOP_TERMS = {
    "什么",
    "哪个",
    "哪些",
    "如何",
    "怎么",
    "为什么",
    "是否",
    "有没有",
    "介绍",
    "说明",
    "设定",
    "信息",
    "内容",
}


def _dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _intent_for_text(text: str) -> tuple[str | None, list[str], list[str]]:
    matched: list[tuple[int, str, list[str], tuple[str, ...]]] = []
    for intent_name, terms in _INTENT_TERMS.items():
        matched_terms = [term for term in terms if term in text]
        positions = [text.find(term) for term in matched_terms]
        if matched_terms and positions:
            matched.append((min(positions), intent_name, matched_terms, terms))
    if not matched:
        return None, [], []
    _, intent_name, matched_terms, terms = sorted(matched, key=lambda item: item[0])[0]
    expansion_terms = [term for term in terms if term not in set(matched_terms)]
    return intent_name, matched_terms, expansion_terms


def _candidate_entity_terms(text: str, *, intent_terms: list[str]) -> list[str]:
    candidates: list[str] = []
    intent_term_set = set(intent_terms)
    stop_terms = _QUESTION_STOP_TERMS | intent_term_set

    def add_segment(segment: str) -> None:
        for part in _CJK_SPLIT_RE.split(segment):
            if 2 <= len(part) <= 16 and part not in stop_terms:
                candidates.append(part)

    for ascii_token in _ASCII_TOKEN_RE.findall(text):
        if len(ascii_token) >= 2:
            candidates.append(ascii_token)

    for run in _CJK_RUN_RE.findall(text):
        add_segment(run)
        for intent_term in intent_terms:
            if intent_term not in run or run == intent_term:
                continue
            before, _, after = run.partition(intent_term)
            for segment in (before, after):
                add_segment(segment)
        for question_term in _QUESTION_STOP_TERMS:
            if question_term not in run or run == question_term:
                continue
            before, _, after = run.partition(question_term)
            for segment in (before, after):
                add_segment(segment)
    return _dedupe_preserve_order(candidates)


def build_query_analysis(text_query: str | None) -> dict[str, Any]:
    """Return deterministic retrieval hints derived from the raw query text."""

    normalized_text = str(text_query or "").strip()
    intent, intent_terms, intent_expansion_terms = _intent_for_text(normalized_text)
    entity_terms = _candidate_entity_terms(
        normalized_text,
        intent_terms=intent_terms,
    )
    sparse_terms = _dedupe_preserve_order([*entity_terms, *intent_terms])
    return {
        "version": "structured_query_analysis_v1",
        "intent": intent,
        "entity_terms": entity_terms,
        "intent_terms": intent_terms,
        "intent_expansion_terms": intent_expansion_terms,
        "sparse_terms": sparse_terms,
    }
