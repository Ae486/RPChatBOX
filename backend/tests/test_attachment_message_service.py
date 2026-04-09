"""Tests for backend attachment-to-message conversion."""
import base64
from pathlib import Path

from models.chat import AttachedFile, ChatMessage
from services.attachment_message_service import AttachmentMessageService


class _FakeMarkItDownResult:
    def __init__(self, markdown: str):
        self.markdown = markdown


class _FakeMarkItDown:
    def convert(self, path: str):
        name = Path(path).name
        return _FakeMarkItDownResult(f"# Extracted\n\ncontent from {name}")


# ---------------------------------------------------------------------------
# Existing tests (local path mode)
# ---------------------------------------------------------------------------

def test_merges_document_and_image_files_into_last_user_message(tmp_path):
    text_file = tmp_path / "notes.docx"
    text_file.write_text("ignored because fake converter is used", encoding="utf-8")
    image_file = tmp_path / "image.png"
    image_file.write_bytes(b"\x89PNG")

    service = AttachmentMessageService(markdown_converter=_FakeMarkItDown())

    messages = [
        ChatMessage(role="system", content=""),
        ChatMessage(role="user", content="Summarize the files"),
    ]
    files = [
        AttachedFile(
            path=str(text_file),
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            name="notes.docx",
        ),
        AttachedFile(
            path=str(image_file),
            mime_type="image/png",
            name="image.png",
        ),
    ]

    merged = service.merge_files_into_messages(messages, files)

    user_message = merged[-1]
    assert isinstance(user_message.content, list)
    assert user_message.content[0]["type"] == "text"
    assert '以下是文件 "notes.docx"' in user_message.content[0]["text"]
    assert "content from notes.docx" in user_message.content[0]["text"]
    assert "Summarize the files" in user_message.content[0]["text"]
    assert user_message.content[1]["type"] == "image_url"
    assert user_message.content[1]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )


def test_falls_back_to_plain_text_read_when_markitdown_is_unavailable(tmp_path):
    text_file = tmp_path / "notes.txt"
    text_file.write_text("Alpha content", encoding="utf-8")

    service = AttachmentMessageService(markdown_converter=None)
    service._converter_initialized = True

    messages = [ChatMessage(role="user", content="Use the file")]
    files = [
        AttachedFile(
            path=str(text_file),
            mime_type="text/plain",
            name="notes.txt",
        )
    ]

    merged = service.merge_files_into_messages(messages, files)

    assert isinstance(merged[-1].content, list)
    assert "Alpha content" in merged[-1].content[0]["text"]


# ---------------------------------------------------------------------------
# Remote upload tests (base64 data mode)
# ---------------------------------------------------------------------------

def test_image_from_base64_data_without_path():
    """Image attachment via remote base64 data, no local path."""
    raw_bytes = b"\x89PNG\r\n\x1a\nfake-image-data"
    encoded = base64.b64encode(raw_bytes).decode("ascii")

    service = AttachmentMessageService()
    messages = [ChatMessage(role="user", content="Describe this")]
    files = [
        AttachedFile(
            data=encoded,
            mime_type="image/png",
            name="remote.png",
        )
    ]

    merged = service.merge_files_into_messages(messages, files)

    user_msg = merged[-1]
    assert isinstance(user_msg.content, list)
    assert user_msg.content[1]["type"] == "image_url"
    url = user_msg.content[1]["image_url"]["url"]
    assert url == f"data:image/png;base64,{encoded}"


def test_plain_text_document_from_base64_data():
    """Plain text document via base64 data, decoded directly without MarkItDown."""
    content_str = "Hello from remote"
    encoded = base64.b64encode(content_str.encode("utf-8")).decode("ascii")

    service = AttachmentMessageService(markdown_converter=None)
    service._converter_initialized = True

    messages = [ChatMessage(role="user", content="Read this")]
    files = [
        AttachedFile(
            data=encoded,
            mime_type="text/plain",
            name="notes.txt",
        )
    ]

    merged = service.merge_files_into_messages(messages, files)

    text = merged[-1].content[0]["text"]
    assert "Hello from remote" in text
    assert "Read this" in text


def test_complex_document_from_base64_data_uses_markitdown():
    """Complex doc (e.g. docx) via base64 data triggers MarkItDown via temp file."""
    fake_bytes = b"PK\x03\x04fake-docx-content"
    encoded = base64.b64encode(fake_bytes).decode("ascii")

    service = AttachmentMessageService(markdown_converter=_FakeMarkItDown())
    messages = [ChatMessage(role="user", content="Summarize")]
    files = [
        AttachedFile(
            data=encoded,
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            name="report.docx",
        )
    ]

    merged = service.merge_files_into_messages(messages, files)

    text = merged[-1].content[0]["text"]
    assert "# Extracted" in text
    assert "Summarize" in text


def test_data_preferred_over_path(tmp_path):
    """When both data and path are present, data takes precedence."""
    local_file = tmp_path / "local.png"
    local_file.write_bytes(b"LOCAL-BYTES")

    remote_bytes = b"REMOTE-BYTES"
    encoded = base64.b64encode(remote_bytes).decode("ascii")

    service = AttachmentMessageService()
    messages = [ChatMessage(role="user", content="Check")]
    files = [
        AttachedFile(
            path=str(local_file),
            data=encoded,
            mime_type="image/png",
            name="dual.png",
        )
    ]

    merged = service.merge_files_into_messages(messages, files)

    url = merged[-1].content[1]["image_url"]["url"]
    # Should contain the REMOTE bytes, not local
    decoded_back = base64.b64decode(url.split(",", 1)[1])
    assert decoded_back == remote_bytes


def test_path_fallback_when_no_data(tmp_path):
    """When data is absent, falls back to local path (backward compatible)."""
    local_file = tmp_path / "fallback.png"
    local_file.write_bytes(b"\x89PNG-local")

    service = AttachmentMessageService()
    messages = [ChatMessage(role="user", content="See")]
    files = [
        AttachedFile(
            path=str(local_file),
            mime_type="image/png",
            name="fallback.png",
        )
    ]

    merged = service.merge_files_into_messages(messages, files)

    url = merged[-1].content[1]["image_url"]["url"]
    decoded_back = base64.b64decode(url.split(",", 1)[1])
    assert decoded_back == b"\x89PNG-local"
