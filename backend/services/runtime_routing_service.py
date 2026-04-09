"""Backend runtime routing service for primary/fallback execution."""
import json
import logging
import re
from typing import Any, AsyncIterator

from config import get_settings
from models.chat import ChatCompletionRequest
from services.gemini_native_service import (
    GeminiNativeService,
    get_gemini_native_service,
)
from services.llm_proxy import LLMProxyService, get_llm_proxy_service
from services.litellm_service import (
    LiteLLMService,
    get_http_status_for_exception,
    get_litellm_service,
)

logger = logging.getLogger(__name__)


class BackendFallbackPolicy:
    """Conservative fallback policy for backend-internal service fallback."""

    _FALLBACK_STATUS_CODES = {502, 503, 504}
    _STATUS_CODE_RE = re.compile(r"status[_\s]?code[=:\s]*(\d{3})", re.IGNORECASE)

    @classmethod
    def should_fallback_exception(
        cls,
        exc: Exception,
        *,
        has_emitted_chunk: bool,
    ) -> bool:
        if has_emitted_chunk:
            return False

        status_code, _ = get_http_status_for_exception(exc)
        return status_code in cls._FALLBACK_STATUS_CODES

    @classmethod
    def should_fallback_sse_error(
        cls,
        *,
        error_type: str,
        error_message: str,
        has_emitted_chunk: bool,
    ) -> bool:
        if has_emitted_chunk:
            return False

        normalized_type = error_type.lower()
        if any(
            token in normalized_type
            for token in ("connection", "timeout", "serviceunavailable")
        ):
            return True

        match = cls._STATUS_CODE_RE.search(error_message)
        if match is None:
            return False

        return int(match.group(1)) in cls._FALLBACK_STATUS_CODES


class RuntimeRoutingService:
    """Route requests through LiteLLM first, then fallback to httpx when safe."""

    def __init__(
        self,
        *,
        primary_service: LiteLLMService | None = None,
        fallback_service: LLMProxyService | None = None,
        gemini_native_service: GeminiNativeService | None = None,
        settings: Any | None = None,
    ):
        self.settings = settings or get_settings()
        self.primary_service = primary_service or get_litellm_service()
        self.fallback_service = fallback_service or get_llm_proxy_service()
        self.gemini_native_service = gemini_native_service or get_gemini_native_service()

    @property
    def fallback_enabled(self) -> bool:
        return bool(getattr(self.settings, "llm_enable_httpx_fallback", True))

    async def chat_completion(self, request: ChatCompletionRequest):
        route_mode = self._get_route_mode(request)
        if route_mode == "direct":
            logger.info(
                "[ROUTE] backend_execution_mode=direct stream=false provider=%s model=%s service=httpx",
                request.provider.type if request.provider else "unknown",
                request.model,
            )
            return await self.fallback_service.chat_completion(request)

        if route_mode == "proxy":
            logger.info(
                "[ROUTE] backend_execution_mode=proxy stream=false provider=%s model=%s service=litellm",
                request.provider.type if request.provider else "unknown",
                request.model,
            )
            return await self.primary_service.chat_completion(request)

        if self._should_use_gemini_native(request):
            try:
                logger.info(
                    "[ROUTE] backend_execution_mode=auto stream=false provider=%s model=%s service=gemini_native",
                    request.provider.type if request.provider else "unknown",
                    request.model,
                )
                return await self.gemini_native_service.chat_completion(request)
            except Exception as exc:
                logger.warning(
                    "[ROUTE] gemini_native_fallback_to_litellm stream=false provider=%s model=%s reason=%s",
                    request.provider.type if request.provider else "unknown",
                    request.model,
                    type(exc).__name__,
                )

        try:
            return await self.primary_service.chat_completion(request)
        except Exception as exc:
            if self._is_httpx_fallback_enabled(
                request
            ) and BackendFallbackPolicy.should_fallback_exception(
                exc,
                has_emitted_chunk=False,
            ):
                logger.warning(
                    "[ROUTE] backend_fallback_to_httpx stream=false provider=%s model=%s reason=%s",
                    request.provider.type if request.provider else "unknown",
                    request.model,
                    type(exc).__name__,
                )
                return await self.fallback_service.chat_completion(request)
            raise

    async def chat_completion_stream(
        self,
        request: ChatCompletionRequest,
    ) -> AsyncIterator[str]:
        route_mode = self._get_route_mode(request)
        if route_mode == "direct":
            logger.info(
                "[ROUTE] backend_execution_mode=direct stream=true provider=%s model=%s service=httpx",
                request.provider.type if request.provider else "unknown",
                request.model,
            )
            async for chunk in self.fallback_service.chat_completion_stream(request):
                yield chunk
            return

        if route_mode == "proxy":
            logger.info(
                "[ROUTE] backend_execution_mode=proxy stream=true provider=%s model=%s service=litellm",
                request.provider.type if request.provider else "unknown",
                request.model,
            )
            async for chunk in self.primary_service.chat_completion_stream(request):
                yield chunk
            return

        if self._should_use_gemini_native(request):
            native_has_emitted_chunk = False
            try:
                logger.info(
                    "[ROUTE] backend_execution_mode=auto stream=true provider=%s model=%s service=gemini_native",
                    request.provider.type if request.provider else "unknown",
                    request.model,
                )
                async for chunk in self.gemini_native_service.chat_completion_stream(request):
                    error_payload = self._extract_error_from_sse_chunk(chunk)
                    if error_payload is not None and not native_has_emitted_chunk:
                        logger.warning(
                            "[ROUTE] gemini_native_fallback_to_litellm stream=true provider=%s model=%s reason=%s",
                            request.provider.type if request.provider else "unknown",
                            request.model,
                            error_payload["type"],
                        )
                        break

                    if self._chunk_has_visible_content(chunk):
                        native_has_emitted_chunk = True
                    yield chunk
                else:
                    return
            except Exception as exc:
                if native_has_emitted_chunk:
                    raise
                logger.warning(
                    "[ROUTE] gemini_native_fallback_to_litellm stream=true provider=%s model=%s reason=%s",
                    request.provider.type if request.provider else "unknown",
                    request.model,
                    type(exc).__name__,
                )

        has_emitted_chunk = False

        try:
            async for chunk in self.primary_service.chat_completion_stream(request):
                error_payload = self._extract_error_from_sse_chunk(chunk)
                if (
                    error_payload is not None
                    and self._is_httpx_fallback_enabled(request)
                    and BackendFallbackPolicy.should_fallback_sse_error(
                        error_type=error_payload["type"],
                        error_message=error_payload["message"],
                        has_emitted_chunk=has_emitted_chunk,
                    )
                ):
                    logger.warning(
                        "[ROUTE] backend_fallback_to_httpx stream=true provider=%s model=%s reason=%s",
                        request.provider.type if request.provider else "unknown",
                        request.model,
                        error_payload["type"],
                    )
                    async for fallback_chunk in self.fallback_service.chat_completion_stream(
                        request
                    ):
                        yield fallback_chunk
                    return

                if self._chunk_has_visible_content(chunk):
                    has_emitted_chunk = True
                yield chunk
        except Exception as exc:
            if self._is_httpx_fallback_enabled(
                request
            ) and BackendFallbackPolicy.should_fallback_exception(
                exc,
                has_emitted_chunk=has_emitted_chunk,
            ):
                logger.warning(
                    "[ROUTE] backend_fallback_to_httpx stream=true provider=%s model=%s reason=%s",
                    request.provider.type if request.provider else "unknown",
                    request.model,
                    type(exc).__name__,
                )
                async for fallback_chunk in self.fallback_service.chat_completion_stream(
                    request
                ):
                    yield fallback_chunk
                return
            raise

    def _get_route_mode(self, request: ChatCompletionRequest) -> str:
        """Resolve backend execution mode during the Phase 2 transition."""
        provider = request.provider
        if provider is None or provider.backend_mode is None:
            # Legacy payloads keep current behavior: LiteLLM primary + safe httpx fallback.
            return "auto"
        return provider.backend_mode

    def _is_httpx_fallback_enabled(self, request: ChatCompletionRequest) -> bool:
        """Return whether backend-internal httpx fallback is allowed."""
        if not self.fallback_enabled:
            return False

        route_mode = self._get_route_mode(request)
        if route_mode != "auto":
            return False

        provider = request.provider
        if provider is not None and provider.fallback_enabled is False:
            return False
        return True

    def _should_use_gemini_native(self, request: ChatCompletionRequest) -> bool:
        if not bool(getattr(self.settings, "llm_enable_gemini_native", True)):
            return False
        if self._get_route_mode(request) != "auto":
            return False
        return self.gemini_native_service.supports_request(request)

    @staticmethod
    def _extract_error_from_sse_chunk(chunk: str) -> dict[str, str] | None:
        if not chunk.startswith("data: "):
            return None

        payload = chunk[6:].strip()
        if payload == "[DONE]":
            return None

        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return None

        error = data.get("error")
        if not isinstance(error, dict):
            return None

        return {
            "type": str(error.get("type") or "unknown"),
            "message": str(error.get("message") or ""),
        }

    @staticmethod
    def _chunk_has_visible_content(chunk: str) -> bool:
        if not chunk.startswith("data: "):
            return False

        payload = chunk[6:].strip()
        if payload == "[DONE]":
            return False

        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return False

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            event_type = data.get("type")
            return event_type in {
                "thinking_delta",
                "text_delta",
                "tool_call",
                "tool_started",
                "tool_result",
                "tool_error",
            }

        delta = choices[0].get("delta")
        if not isinstance(delta, dict):
            return False

        content = delta.get("content")
        if isinstance(content, str) and content != "":
            return True
        tool_calls = delta.get("tool_calls")
        return isinstance(tool_calls, list) and len(tool_calls) > 0


_runtime_routing_service: RuntimeRoutingService | None = None


def get_runtime_routing_service() -> RuntimeRoutingService:
    """Get cached runtime routing service instance."""
    global _runtime_routing_service
    if _runtime_routing_service is None:
        _runtime_routing_service = RuntimeRoutingService()
    return _runtime_routing_service
