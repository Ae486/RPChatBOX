"""Rebuildable structural index over committed setup foundation truth."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import ValidationError

from rp.models.setup_drafts import (
    SetupDraftEntry,
    SetupDraftSection,
    SetupStageDraftBlock,
)
from rp.models.setup_stage import SetupStageId
from rp.models.setup_truth_index import (
    SetupTruthIndex,
    SetupTruthIndexFilters,
    SetupTruthIndexReadItem,
    SetupTruthIndexReadResult,
    SetupTruthIndexRow,
    SetupTruthIndexSearchItem,
    SetupTruthIndexSearchResult,
)
from rp.models.setup_workspace import AcceptedCommit, SetupWorkspace


class SetupTruthIndexService:
    """Build and query deterministic committed setup truth rows."""

    _MAX_LIMIT = 100
    _MAX_READ_CHARS = 20000

    def rebuild(
        self,
        *,
        workspace: SetupWorkspace,
        commit_id: str | None = None,
    ) -> SetupTruthIndex:
        commits = self._selected_commits(workspace=workspace, commit_id=commit_id)
        rows: list[SetupTruthIndexRow] = []
        for commit in commits:
            rows.extend(self._rows_from_commit(workspace=workspace, commit=commit))
        return SetupTruthIndex(rows=rows)

    def search(
        self,
        *,
        workspace: SetupWorkspace,
        query: str = "",
        filters: SetupTruthIndexFilters | None = None,
        limit: int = 20,
    ) -> SetupTruthIndexSearchResult:
        filters = filters or SetupTruthIndexFilters()
        index = self.rebuild(workspace=workspace, commit_id=filters.commit_id)
        query_tokens = self._query_tokens(query)
        scored: list[tuple[int, SetupTruthIndexRow]] = []
        for row in index.rows:
            if not self._matches_filters(row=row, filters=filters):
                continue
            score = self._score(row=row, query_tokens=query_tokens)
            if query_tokens and score <= 0:
                continue
            scored.append((score, row))
        scored.sort(
            key=lambda item: (
                -item[0],
                item[1].stage_id.value,
                item[1].semantic_path,
                item[1].ref,
            )
        )
        bounded_limit = max(1, min(int(limit or 20), self._MAX_LIMIT))
        return SetupTruthIndexSearchResult(
            items=[
                self._search_item(row=row, score=score)
                for score, row in scored[:bounded_limit]
            ]
        )

    def read_refs(
        self,
        *,
        workspace: SetupWorkspace,
        refs: list[str],
        detail: str = "summary",
        max_chars: int = 4000,
        commit_id: str | None = None,
    ) -> SetupTruthIndexReadResult:
        index = self.rebuild(workspace=workspace, commit_id=commit_id)
        row_by_ref: dict[str, SetupTruthIndexRow] = {}
        for row in index.rows:
            row_by_ref[row.ref] = row
            for alias in self._ref_aliases(row.ref):
                row_by_ref.setdefault(alias, row)

        bounded_chars = max(1, min(int(max_chars or 4000), self._MAX_READ_CHARS))
        items: list[SetupTruthIndexReadItem] = []
        missing_refs: list[str] = []
        for raw_ref in refs:
            ref = str(raw_ref or "").strip()
            if not ref:
                continue
            found_row = row_by_ref.get(ref)
            if found_row is None:
                missing_refs.append(ref)
                items.append(SetupTruthIndexReadItem(ref=ref, found=False))
                continue
            items.append(
                self._read_item(
                    requested_ref=ref,
                    row=found_row,
                    detail=detail,
                    max_chars=bounded_chars,
                )
            )
        return SetupTruthIndexReadResult(
            success=not missing_refs,
            items=items,
            missing_refs=missing_refs,
        )

    def _rows_from_commit(
        self,
        *,
        workspace: SetupWorkspace,
        commit: AcceptedCommit,
    ) -> list[SetupTruthIndexRow]:
        rows: list[SetupTruthIndexRow] = []
        for snapshot in commit.snapshots:
            stage_id = self._coerce_stage_id(snapshot.block_type)
            if stage_id is None:
                continue
            try:
                block = SetupStageDraftBlock.model_validate(snapshot.payload)
            except ValidationError:
                continue
            if block.stage_id != stage_id:
                continue
            rows.extend(
                self._rows_from_stage_block(
                    workspace=workspace,
                    commit=commit,
                    stage_id=stage_id,
                    block=block,
                )
            )
        return rows

    def _rows_from_stage_block(
        self,
        *,
        workspace: SetupWorkspace,
        commit: AcceptedCommit,
        stage_id: SetupStageId,
        block: SetupStageDraftBlock,
    ) -> list[SetupTruthIndexRow]:
        rows: list[SetupTruthIndexRow] = [
            self._stage_row(
                workspace=workspace,
                commit=commit,
                stage_id=stage_id,
                block=block,
            )
        ]
        for entry in block.entries:
            rows.append(
                self._entry_row(
                    workspace=workspace,
                    commit=commit,
                    stage_id=stage_id,
                    entry=entry,
                )
            )
            rows.extend(
                self._section_row(
                    workspace=workspace,
                    commit=commit,
                    stage_id=stage_id,
                    entry=entry,
                    section=section,
                )
                for section in entry.sections
            )
        return rows

    def _stage_row(
        self,
        *,
        workspace: SetupWorkspace,
        commit: AcceptedCommit,
        stage_id: SetupStageId,
        block: SetupStageDraftBlock,
    ) -> SetupTruthIndexRow:
        payload = block.model_dump(mode="json", exclude_none=True)
        title = stage_id.value.replace("_", " ").title()
        preview = self._stage_preview(block)
        return self._row(
            workspace=workspace,
            commit=commit,
            stage_id=stage_id,
            ref=f"foundation:{stage_id.value}",
            row_type="stage",
            semantic_path=stage_id.value,
            title=title,
            summary=preview,
            preview_text=preview,
            payload=payload,
        )

    def _entry_row(
        self,
        *,
        workspace: SetupWorkspace,
        commit: AcceptedCommit,
        stage_id: SetupStageId,
        entry: SetupDraftEntry,
    ) -> SetupTruthIndexRow:
        payload = entry.model_dump(mode="json", exclude_none=True)
        preview = self._entry_preview(entry)
        return self._row(
            workspace=workspace,
            commit=commit,
            stage_id=stage_id,
            ref=f"foundation:{stage_id.value}:{entry.entry_id}",
            row_type="entry",
            entry_id=entry.entry_id,
            semantic_path=entry.semantic_path,
            parent_path=self._parent_path(entry.semantic_path),
            entry_type=entry.entry_type,
            title=entry.title,
            display_label=entry.display_label,
            summary=entry.summary or preview,
            aliases=list(entry.aliases),
            tags=list(entry.tags),
            preview_text=preview,
            payload=payload,
        )

    def _section_row(
        self,
        *,
        workspace: SetupWorkspace,
        commit: AcceptedCommit,
        stage_id: SetupStageId,
        entry: SetupDraftEntry,
        section: SetupDraftSection,
    ) -> SetupTruthIndexRow:
        payload = section.model_dump(mode="json", exclude_none=True)
        preview = self._section_preview(section)
        return self._row(
            workspace=workspace,
            commit=commit,
            stage_id=stage_id,
            ref=f"foundation:{stage_id.value}:{entry.entry_id}:{section.section_id}",
            row_type="section",
            entry_id=entry.entry_id,
            section_id=section.section_id,
            semantic_path=f"{entry.semantic_path}.{section.section_id}",
            parent_path=entry.semantic_path,
            entry_type=entry.entry_type,
            title=entry.title,
            display_label=entry.display_label,
            summary=preview,
            aliases=list(entry.aliases),
            tags=list(dict.fromkeys([*entry.tags, *section.tags])),
            section_title=section.title,
            section_kind=str(section.kind.value),
            retrieval_role=str(section.retrieval_role),
            preview_text=preview,
            payload=payload,
        )

    def _row(
        self,
        *,
        workspace: SetupWorkspace,
        commit: AcceptedCommit,
        stage_id: SetupStageId,
        ref: str,
        row_type: Literal["stage", "entry", "section"],
        semantic_path: str,
        payload: dict[str, Any],
        parent_path: str | None = None,
        entry_id: str | None = None,
        section_id: str | None = None,
        entry_type: str | None = None,
        title: str | None = None,
        display_label: str | None = None,
        summary: str | None = None,
        aliases: list[str] | None = None,
        tags: list[str] | None = None,
        section_title: str | None = None,
        section_kind: str | None = None,
        retrieval_role: str | None = None,
        preview_text: str | None = None,
    ) -> SetupTruthIndexRow:
        canonical_payload = self._canonical_json(payload)
        search_text = self._join_search_text(
            [
                ref,
                stage_id.value,
                semantic_path,
                parent_path,
                entry_type,
                title,
                display_label,
                summary,
                aliases,
                tags,
                section_title,
                section_kind,
                retrieval_role,
                preview_text,
            ]
        )
        return SetupTruthIndexRow(
            workspace_id=workspace.workspace_id,
            story_id=workspace.story_id,
            mode=workspace.mode.value,
            stage_id=stage_id,
            commit_id=commit.commit_id,
            ref=ref,
            row_type=row_type,
            entry_id=entry_id,
            section_id=section_id,
            semantic_path=semantic_path,
            parent_path=parent_path,
            entry_type=entry_type,
            title=title,
            display_label=display_label,
            summary=summary,
            aliases=list(aliases or []),
            tags=list(tags or []),
            section_title=section_title,
            section_kind=section_kind,
            retrieval_role=retrieval_role,
            preview_text=preview_text,
            content_hash=hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest(),
            token_count=self._estimate_tokens(
                preview_text or summary or canonical_payload
            ),
            created_at=commit.created_at,
            search_text=search_text,
            payload=payload,
        )

    def _selected_commits(
        self,
        *,
        workspace: SetupWorkspace,
        commit_id: str | None,
    ) -> list[AcceptedCommit]:
        if commit_id:
            return [
                commit
                for commit in workspace.accepted_commits
                if commit.commit_id == commit_id
            ]
        latest_by_stage: dict[SetupStageId, AcceptedCommit] = {}
        for commit in sorted(
            workspace.accepted_commits, key=lambda item: item.created_at
        ):
            stage_id = self._commit_stage_id(commit)
            if stage_id is not None:
                latest_by_stage[stage_id] = commit
        return sorted(latest_by_stage.values(), key=lambda item: item.created_at)

    def _commit_stage_id(self, commit: AcceptedCommit) -> SetupStageId | None:
        stage_id = self._coerce_stage_id(str(commit.step_id))
        if stage_id is not None:
            return stage_id
        for snapshot in commit.snapshots:
            stage_id = self._coerce_stage_id(snapshot.block_type)
            if stage_id is not None:
                return stage_id
        return None

    @staticmethod
    def _coerce_stage_id(value: str | None) -> SetupStageId | None:
        if not value:
            return None
        try:
            return SetupStageId(value)
        except ValueError:
            return None

    @staticmethod
    def _ref_aliases(ref: str) -> list[str]:
        parts = ref.split(":")
        if len(parts) >= 3 and parts[0] == "foundation":
            return [":".join(["stage", *parts[1:]])]
        return []

    @staticmethod
    def _parent_path(path: str) -> str | None:
        if "." not in path:
            return None
        return path.rsplit(".", 1)[0]

    @classmethod
    def _stage_preview(cls, block: SetupStageDraftBlock) -> str | None:
        parts = [cls._entry_preview(entry) for entry in block.entries[:3]]
        if block.notes:
            parts.append(block.notes)
        return cls._join_preview(parts)

    @classmethod
    def _entry_preview(cls, entry: SetupDraftEntry) -> str | None:
        if entry.summary:
            return entry.summary.strip()
        for section in entry.sections:
            if section.retrieval_role == "summary":
                preview = cls._section_preview(section)
                if preview:
                    return preview
        return cls._join_preview([entry.title, entry.semantic_path])

    @classmethod
    def _section_preview(cls, section: SetupDraftSection) -> str | None:
        content = section.content
        text = content.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        items = content.get("items")
        if isinstance(items, list):
            return cls._join_preview([str(item) for item in items])
        values = content.get("values")
        if isinstance(values, dict):
            return cls._join_preview(
                [f"{key}: {value}" for key, value in values.items()]
            )
        return section.title

    @staticmethod
    def _join_preview(parts: list[Any]) -> str | None:
        text_parts = [str(part).strip() for part in parts if str(part or "").strip()]
        if not text_parts:
            return None
        return " | ".join(text_parts)

    @classmethod
    def _join_search_text(cls, parts: list[Any]) -> str:
        flat: list[str] = []
        for part in parts:
            if part is None:
                continue
            if isinstance(part, (list, tuple, set)):
                flat.extend(str(item) for item in part if str(item or "").strip())
            else:
                text = str(part).strip()
                if text:
                    flat.append(text)
        return " ".join(flat).lower()

    @staticmethod
    def _canonical_json(payload: dict[str, Any]) -> str:
        return json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        if not text:
            return 0
        return max(1, (len(text) + 3) // 4)

    @staticmethod
    def _query_tokens(query: str) -> list[str]:
        text = str(query or "").lower()
        return [token for token in re.split(r"[\s\.:/_#-]+", text) if token]

    @staticmethod
    def _matches_filters(
        *,
        row: SetupTruthIndexRow,
        filters: SetupTruthIndexFilters,
    ) -> bool:
        if filters.stage_ids and row.stage_id not in filters.stage_ids:
            return False
        entry_types = {item.lower() for item in filters.entry_types}
        if entry_types and str(row.entry_type or "").lower() not in entry_types:
            return False
        filter_tags = {item.lower() for item in filters.tags}
        row_tags = {item.lower() for item in row.tags}
        if filter_tags and not filter_tags.issubset(row_tags):
            return False
        prefix = str(filters.semantic_path_prefix or "").strip()
        if prefix and not row.semantic_path.startswith(prefix):
            return False
        return True

    @staticmethod
    def _score(*, row: SetupTruthIndexRow, query_tokens: list[str]) -> int:
        if not query_tokens:
            return 1
        return sum(1 for token in query_tokens if token in row.search_text)

    @staticmethod
    def _search_item(
        *,
        row: SetupTruthIndexRow,
        score: int,
    ) -> SetupTruthIndexSearchItem:
        return SetupTruthIndexSearchItem(
            ref=row.ref,
            stage_id=row.stage_id,
            commit_id=row.commit_id,
            row_type=row.row_type,
            title=row.section_title or row.title,
            summary=row.summary,
            semantic_path=row.semantic_path,
            entry_id=row.entry_id,
            section_id=row.section_id,
            entry_type=row.entry_type,
            tags=list(row.tags),
            preview_text=row.preview_text,
            score=score,
        )

    def _read_item(
        self,
        *,
        requested_ref: str,
        row: SetupTruthIndexRow,
        detail: str,
        max_chars: int,
    ) -> SetupTruthIndexReadItem:
        payload: dict[str, Any] | None = None
        truncated = False
        if detail == "full":
            payload, truncated = self._bounded_payload(
                payload=row.payload,
                max_chars=max_chars,
            )
        return SetupTruthIndexReadItem(
            ref=requested_ref,
            found=True,
            source=row.source,
            stage_id=row.stage_id,
            commit_id=row.commit_id,
            row_type=row.row_type,
            title=row.section_title or row.title,
            summary=row.summary,
            semantic_path=row.semantic_path,
            payload=payload,
            truncated=truncated,
        )

    def _bounded_payload(
        self,
        *,
        payload: dict[str, Any],
        max_chars: int,
    ) -> tuple[dict[str, Any], bool]:
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if len(text) <= max_chars:
            return payload, False
        return {"_truncated": True, "preview": text[:max_chars]}, True
