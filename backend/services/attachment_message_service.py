"""Attachment-to-message conversion for backend proxy execution."""
from __future__ import annotations

import base64
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from models.chat import AttachedFile, ChatMessage

_PLAIN_TEXT_PREFIXES = (
    "text/",
    "application/json",
    "application/xml",
    "application/x-yaml",
    "application/dart",
)


class AttachmentMessageService:
    """Convert attached files into OpenAI-style multimodal message content."""

    def __init__(self, markdown_converter: Any | None = None):
        self._markdown_converter = markdown_converter
        self._converter_initialized = markdown_converter is not None

    def merge_files_into_messages(
        self,
        messages: list[ChatMessage],
        files: list[AttachedFile] | None,
    ) -> list[ChatMessage]:
        """Attach files to the last user message, matching current direct-chain semantics."""
        merged = [message.model_copy(deep=True) for message in messages]
        if not files or not merged or merged[-1].role != "user":
            return merged

        document_contents: list[str] = []
        image_contents: list[dict[str, Any]] = []

        for file in files:
            if file.mime_type.startswith("image/"):
                image_part = self._build_image_part(file)
                if image_part is not None:
                    image_contents.append(image_part)
                else:
                    document_contents.append(
                        f"// 文件 {file.name} 处理失败: 无法读取图片内容"
                    )
                continue

            try:
                text_content = self._extract_document_content(file)
                document_contents.append(
                    self._generate_file_prompt(file.name, file.mime_type, text_content)
                )
            except Exception as exc:  # pragma: no cover - defensive
                document_contents.append(f"// 文件 {file.name} 处理失败: {exc}")

        merged[-1] = merged[-1].model_copy(
            update={
                "content": self._merge_content(
                    merged[-1].content,
                    document_contents=document_contents,
                    image_contents=image_contents,
                )
            }
        )
        return merged

    def _merge_content(
        self,
        current_content: str | list[dict[str, Any]] | None,
        *,
        document_contents: list[str],
        image_contents: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if isinstance(current_content, list):
            content = deepcopy(current_content)
            if document_contents:
                self._prepend_document_text(content, "\n\n".join(document_contents))
            content.extend(image_contents)
            return content

        text_content = current_content or ""
        if document_contents:
            document_text = "\n\n".join(document_contents)
            if text_content:
                text_content = f"{document_text}\n\n---\n\n{text_content}"
            else:
                text_content = document_text

        content: list[dict[str, Any]] = [{"type": "text", "text": text_content}]
        content.extend(image_contents)
        return content

    @staticmethod
    def _prepend_document_text(
        content: list[dict[str, Any]], document_text: str
    ) -> None:
        for part in content:
            if part.get("type") == "text":
                existing = str(part.get("text") or "")
                part["text"] = (
                    f"{document_text}\n\n---\n\n{existing}"
                    if existing
                    else document_text
                )
                return

        content.insert(0, {"type": "text", "text": document_text})

    def _get_bytes(self, file: AttachedFile) -> bytes | None:
        """Unified byte retrieval: prefer ``data`` (remote), fall back to ``path`` (local)."""
        if file.data:
            return base64.b64decode(file.data)
        if file.path:
            path = Path(file.path)
            if path.exists():
                return path.read_bytes()
        return None

    def _build_image_part(self, file: AttachedFile) -> dict[str, Any] | None:
        raw = self._get_bytes(file)
        if raw is None:
            return None

        encoded = base64.b64encode(raw).decode("ascii")
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{file.mime_type};base64,{encoded}"},
        }

    def _extract_document_content(self, file: AttachedFile) -> str:
        raw = self._get_bytes(file)
        if raw is None:
            raise FileNotFoundError(f"No data or valid path for {file.name}")

        # Plain text types: decode directly, skip MarkItDown
        if any(file.mime_type.startswith(p) for p in _PLAIN_TEXT_PREFIXES):
            return self._decode_text(raw)

        # Complex formats: try MarkItDown (needs a file path)
        converter = self._get_markdown_converter()
        if converter is not None:
            return self._extract_via_converter(converter, file, raw)

        # No converter available: best-effort text decode
        return self._decode_text(raw)

    def _extract_via_converter(
        self, converter: Any, file: AttachedFile, raw: bytes
    ) -> str:
        """Run MarkItDown on file content, using temp file when content is remote."""
        # If local path exists, use it directly
        if file.path:
            path = Path(file.path)
            if path.exists():
                result = converter.convert(str(path))
                markdown = getattr(result, "markdown", None) or getattr(
                    result, "text_content", None
                )
                if isinstance(markdown, str) and markdown.strip():
                    return markdown
                return self._decode_text(raw)

        # Remote content: write to temp file for MarkItDown
        suffix = Path(file.name).suffix or ""
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(raw)
            tmp_path = tmp.name
        try:
            result = converter.convert(tmp_path)
            markdown = getattr(result, "markdown", None) or getattr(
                result, "text_content", None
            )
            if isinstance(markdown, str) and markdown.strip():
                return markdown
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        return self._decode_text(raw)

    def _get_markdown_converter(self) -> Any | None:
        if self._converter_initialized:
            return self._markdown_converter

        self._converter_initialized = True
        try:
            from markitdown import MarkItDown
        except ImportError:
            self._markdown_converter = None
            return None

        self._markdown_converter = MarkItDown(enable_plugins=False)
        return self._markdown_converter

    @staticmethod
    def _decode_text(raw: bytes) -> str:
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode(errors="replace")

    @staticmethod
    def _generate_file_prompt(file_name: str, mime_type: str, content: str) -> str:
        return (
            f'以下是文件 "{file_name}" ({mime_type}) 的内容:\n'
            "---\n"
            f"{content}\n"
            "---\n\n"
            "请基于上述文件内容回答用户的问题。"
        )


_attachment_message_service: AttachmentMessageService | None = None


def get_attachment_message_service() -> AttachmentMessageService:
    """Get singleton attachment conversion service."""
    global _attachment_message_service
    if _attachment_message_service is None:
        _attachment_message_service = AttachmentMessageService()
    return _attachment_message_service
