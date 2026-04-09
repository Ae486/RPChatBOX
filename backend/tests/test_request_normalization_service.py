"""Tests for backend request normalization."""
from models.chat import AttachedFile, ChatCompletionRequest, ChatMessage, ProviderConfig
from services.request_normalization import RequestNormalizationService


def build_request(
    provider_type: str = "openai",
    model: str = "gpt-4o-mini",
    messages: list[ChatMessage] | None = None,
    **kwargs,
) -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model=model,
        messages=messages
        or [
            ChatMessage(role="system", content=""),
            ChatMessage(role="user", content="hello"),
        ],
        provider=ProviderConfig(
            type=provider_type,
            api_key="sk-test",
            api_url="https://api.example.com/v1",
        ),
        **kwargs,
    )


def test_filters_empty_system_messages():
    service = RequestNormalizationService()
    request = build_request()

    normalized = service.normalize(request)

    assert len(normalized.messages) == 1
    assert normalized.messages[0].role == "user"


def test_openai_default_top_p_and_penalties_are_removed():
    service = RequestNormalizationService()
    request = build_request(
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        temperature=0.7,
        max_tokens=2048,
    )

    normalized = service.normalize(request)

    assert normalized.temperature == 0.7
    assert normalized.max_tokens == 2048
    assert normalized.top_p is None
    assert normalized.frequency_penalty is None
    assert normalized.presence_penalty is None


def test_gemini_forces_thinking_extra_body_when_missing():
    service = RequestNormalizationService()
    request = build_request(
        provider_type="gemini",
        model="gemini-2.5-flash",
        temperature=0.7,
        max_tokens=2048,
        top_p=1.0,
    )

    normalized = service.normalize(request)

    assert normalized.top_p is None
    assert normalized.extra_body == {
        "google": {"thinking_config": {"include_thoughts": True}}
    }


def test_existing_extra_body_is_preserved_and_merged():
    service = RequestNormalizationService()
    request = build_request(
        provider_type="gemini",
        model="gemini-2.5-flash",
        extra_body={"google": {"thinking_config": {"temperature": 0.1}}},
    )

    normalized = service.normalize(request)

    assert normalized.extra_body == {
        "google": {
            "thinking_config": {
                "temperature": 0.1,
                "include_thoughts": True,
            }
        }
    }


def test_files_are_merged_into_last_user_message_and_cleared_from_request(tmp_path):
    text_file = tmp_path / "notes.txt"
    text_file.write_text("Alpha content", encoding="utf-8")

    service = RequestNormalizationService()
    request = build_request(
        messages=[ChatMessage(role="user", content="Summarize the file")],
        files=[
            AttachedFile(
                path=str(text_file),
                mime_type="text/plain",
                name="notes.txt",
            )
        ],
    )

    normalized = service.normalize(request)

    assert normalized.files is None
    assert isinstance(normalized.messages[0].content, list)
    assert normalized.messages[0].content[0]["type"] == "text"
    assert "Alpha content" in normalized.messages[0].content[0]["text"]
    assert "Summarize the file" in normalized.messages[0].content[0]["text"]
