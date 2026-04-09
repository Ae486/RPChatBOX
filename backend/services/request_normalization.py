"""Request normalization for backend chat execution."""
from __future__ import annotations

from copy import deepcopy

from models.chat import ChatCompletionRequest, ChatMessage
from services.attachment_message_service import get_attachment_message_service


class RequestNormalizationService:
    """Normalize incoming chat requests to match current direct-chain semantics."""

    _TOP_P_PROVIDERS = {"openai", "deepseek", "claude"}
    _PENALTY_PROVIDERS = {"openai"}

    def __init__(self, attachment_message_service=None):
        self._attachment_message_service = (
            attachment_message_service or get_attachment_message_service()
        )

    def normalize(self, request: ChatCompletionRequest) -> ChatCompletionRequest:
        """Return a normalized copy of the request."""
        provider_type = request.provider.type if request.provider else None
        extra_body = self._normalize_extra_body(request)

        return request.model_copy(
            update={
                "messages": self._normalize_messages(request.messages, request.files),
                "temperature": self._normalize_temperature(request.temperature),
                "max_tokens": self._normalize_max_tokens(request.max_tokens),
                "top_p": self._normalize_top_p(provider_type, request.top_p),
                "frequency_penalty": self._normalize_penalty(
                    provider_type, request.frequency_penalty
                ),
                "presence_penalty": self._normalize_penalty(
                    provider_type, request.presence_penalty
                ),
                "extra_body": extra_body,
                "files": None,
            },
            deep=True,
        )

    def _normalize_messages(
        self,
        messages: list[ChatMessage],
        files,
    ) -> list[ChatMessage]:
        """Filter empty system messages to match current Flutter direct-chain behavior."""
        normalized: list[ChatMessage] = []
        for message in messages:
            if self._is_empty_system_message(message):
                continue
            normalized.append(message)
        return self._attachment_message_service.merge_files_into_messages(
            normalized,
            files,
        )

    def _is_empty_system_message(self, message: ChatMessage) -> bool:
        if message.role != "system":
            return False
        if message.content is None:
            return True
        if isinstance(message.content, str):
            return message.content.strip() == ""
        return False

    def _normalize_temperature(self, temperature: float | None) -> float | None:
        if temperature is None or temperature == 1.0:
            return None
        return temperature

    def _normalize_max_tokens(self, max_tokens: int | None) -> int | None:
        if max_tokens is None or max_tokens <= 0:
            return None
        return max_tokens

    def _normalize_top_p(
        self, provider_type: str | None, top_p: float | None
    ) -> float | None:
        if provider_type not in self._TOP_P_PROVIDERS:
            return None
        if top_p is None or top_p == 1.0:
            return None
        return top_p

    def _normalize_penalty(
        self, provider_type: str | None, penalty: float | None
    ) -> float | None:
        if provider_type not in self._PENALTY_PROVIDERS:
            return None
        if penalty is None or penalty == 0.0:
            return None
        return penalty

    def _normalize_extra_body(
        self, request: ChatCompletionRequest
    ) -> dict | None:
        extra_body = deepcopy(request.extra_body) if request.extra_body else None
        if "gemini" not in request.model.lower():
            return extra_body

        if extra_body is None:
            extra_body = {}

        google = extra_body.setdefault("google", {})
        thinking_config = google.setdefault("thinking_config", {})
        thinking_config.setdefault("include_thoughts", True)
        return extra_body


_request_normalization_service: RequestNormalizationService | None = None


def get_request_normalization_service() -> RequestNormalizationService:
    """Get singleton request normalization service."""
    global _request_normalization_service
    if _request_normalization_service is None:
        _request_normalization_service = RequestNormalizationService()
    return _request_normalization_service
