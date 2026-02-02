# LiteLLM 框架集成实施计划

> 零决策可执行计划 - 最终效果与直连一致

## 0. 执行摘要

| 项目 | 说明 |
|------|------|
| **目标** | 用 LiteLLM SDK 替换 httpx 直接转发，保持与 Flutter 直连完全相同的行为 |
| **范围** | 仅修改 `backend/services/llm_proxy.py`，不改动 Flutter 端 |
| **策略** | Flutter 端 `ProxyOpenAIProvider` 保持现有解析逻辑（策略 B） |
| **预计改动** | ~150 行 Python 代码 |

---

## 1. 功能对等性要求（来自 Gemini 分析）

### 1.1 必须对齐的功能

| 功能 | 直连 (Flutter) | 当前 Proxy | LiteLLM 覆盖 |
|------|----------------|------------|--------------|
| 基础参数 (model/messages/stream) | ✅ | ✅ | ✅ |
| `include_reasoning: true` | ✅ 硬编码 | ✅ 透传 | ✅ 透传 |
| `extra_body` (Gemini thinking) | ✅ 自动添加 | ✅ 透传 | ✅ 透传 |
| Provider 类型参数过滤 | ✅ 按类型 | ❌ 全量 | ✅ 内置 |
| SSE 流式响应 | ✅ | ✅ | ✅ |
| `reasoning_content` 字段 | ✅ 检测 | ✅ 透传 | ✅ 标准化 |
| 错误格式统一 | ✅ | 部分 | ✅ |

### 1.2 不需要改动的功能（Flutter 端处理）

- `<think>` 标签生成 → `ProxyOpenAIProvider` 已实现
- Gemini first-part-as-thinking → `ProxyOpenAIProvider` 已实现
- 多模态文件处理 → Flutter 端预处理

---

## 2. LiteLLM API 用法（来自文档调研）

### 2.1 异步流式调用

```python
from litellm import acompletion

async def stream_completion():
    response = await acompletion(
        model="openai/gpt-4o",  # 格式: provider/model
        messages=[{"role": "user", "content": "Hello"}],
        stream=True,
        api_key="sk-xxx",       # 每请求传入，不依赖环境变量
        api_base="https://api.openai.com/v1",  # 自定义 base URL
        temperature=0.7,
        max_tokens=1000,
    )

    async for chunk in response:
        # chunk.choices[0].delta.content
        # chunk.choices[0].delta.reasoning_content  # 如果有
        yield chunk
```

### 2.2 Provider 前缀映射

| ChatBoxApp Provider | LiteLLM Model 前缀 |
|---------------------|-------------------|
| `openai` | `openai/` |
| `deepseek` | `deepseek/` 或 `openai/` (兼容模式) |
| `gemini` | `gemini/` 或 `vertex_ai/` |
| `claude` | `anthropic/` |

### 2.3 自定义 API Base

```python
# 方式 1: 直接参数
response = await acompletion(
    model="openai/gpt-4",
    api_base="https://custom-endpoint.com/v1",
    api_key="sk-xxx",
    ...
)

# 方式 2: 使用 custom_llm_provider
response = await acompletion(
    model="custom/my-model",
    custom_llm_provider="openai",
    api_base="https://custom-endpoint.com/v1",
    ...
)
```

### 2.4 错误处理

```python
from litellm.exceptions import (
    AuthenticationError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
    APIConnectionError,
)

# 映射到 HTTP 状态码
EXCEPTION_STATUS_MAP = {
    AuthenticationError: 401,
    RateLimitError: 429,
    ServiceUnavailableError: 503,
    Timeout: 504,
    APIConnectionError: 502,
}
```

---

## 3. 实施步骤

### Step 1: 添加依赖

```bash
# backend/requirements.txt 添加
litellm>=1.50.0
```

验证命令:
```bash
cd backend && pip install litellm && python -c "import litellm; print(litellm.version)"
```

---

### Step 2: 创建 LiteLLM 服务模块

**文件**: `backend/services/litellm_service.py`

```python
"""LiteLLM-based LLM service."""
import json
from typing import AsyncIterator

import litellm
from litellm.exceptions import (
    AuthenticationError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
    APIConnectionError,
)

from config import get_settings
from models.chat import ChatCompletionRequest, ProviderConfig


class LiteLLMService:
    """LLM service using LiteLLM SDK."""

    # Provider type to LiteLLM prefix mapping
    PROVIDER_PREFIX = {
        "openai": "openai",
        "deepseek": "deepseek",
        "gemini": "gemini",
        "claude": "anthropic",
    }

    def __init__(self):
        self.settings = get_settings()
        # Disable LiteLLM telemetry
        litellm.telemetry = False
        litellm.drop_params = True  # Auto-drop unsupported params per provider

    def _get_litellm_model(self, provider: ProviderConfig, model: str) -> str:
        """Convert model name to LiteLLM format: provider/model."""
        prefix = self.PROVIDER_PREFIX.get(provider.type, "openai")

        # If model already has prefix, use as-is
        if "/" in model:
            return model

        return f"{prefix}/{model}"

    def _get_api_base(self, provider: ProviderConfig) -> str | None:
        """Get API base URL, handling # suffix for force mode."""
        base_url = provider.api_url.rstrip("/")

        if base_url.endswith("#"):
            return base_url[:-1]

        # LiteLLM handles /v1/chat/completions automatically
        return base_url

    def _build_completion_kwargs(self, request: ChatCompletionRequest) -> dict:
        """Build kwargs for litellm.acompletion()."""
        provider = request.provider

        kwargs = {
            "model": self._get_litellm_model(provider, request.model),
            "messages": [msg.model_dump(exclude_none=True) for msg in request.messages],
            "stream": request.stream,
            "api_key": provider.api_key,
            "timeout": self.settings.llm_request_timeout,
        }

        # Set custom API base if provided
        api_base = self._get_api_base(provider)
        if api_base:
            kwargs["api_base"] = api_base

        # Standard parameters (LiteLLM auto-drops unsupported ones)
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens
        if request.top_p is not None:
            kwargs["top_p"] = request.top_p
        if request.frequency_penalty is not None:
            kwargs["frequency_penalty"] = request.frequency_penalty
        if request.presence_penalty is not None:
            kwargs["presence_penalty"] = request.presence_penalty
        if request.stop is not None:
            kwargs["stop"] = request.stop

        # Provider-specific extensions
        if request.extra_body:
            kwargs["extra_body"] = request.extra_body

        # Custom headers
        if provider.custom_headers:
            kwargs["extra_headers"] = provider.custom_headers

        return kwargs

    async def chat_completion(self, request: ChatCompletionRequest) -> dict:
        """Handle non-streaming chat completion."""
        if not request.provider:
            raise ValueError("Provider configuration is required")

        kwargs = self._build_completion_kwargs(request)
        kwargs["stream"] = False

        response = await litellm.acompletion(**kwargs)
        return response.model_dump()

    async def chat_completion_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[str]:
        """Handle streaming chat completion, yielding SSE formatted strings."""
        if not request.provider:
            raise ValueError("Provider configuration is required")

        kwargs = self._build_completion_kwargs(request)
        kwargs["stream"] = True

        response = await litellm.acompletion(**kwargs)

        async for chunk in response:
            # Convert chunk to dict and format as SSE
            chunk_dict = chunk.model_dump()
            yield f"data: {json.dumps(chunk_dict)}\n\n"

        yield "data: [DONE]\n\n"


# Exception to HTTP status code mapping
def get_http_status_for_exception(exc: Exception) -> tuple[int, str]:
    """Map LiteLLM exceptions to HTTP status codes."""
    if isinstance(exc, AuthenticationError):
        return 401, "authentication_error"
    elif isinstance(exc, RateLimitError):
        return 429, "rate_limit_error"
    elif isinstance(exc, ServiceUnavailableError):
        return 503, "service_unavailable"
    elif isinstance(exc, Timeout):
        return 504, "timeout"
    elif isinstance(exc, APIConnectionError):
        return 502, "connection_error"
    else:
        return 500, "internal_error"


# Singleton instance
_litellm_service: LiteLLMService | None = None


def get_litellm_service() -> LiteLLMService:
    """Get LiteLLM service instance."""
    global _litellm_service
    if _litellm_service is None:
        _litellm_service = LiteLLMService()
    return _litellm_service
```

---

### Step 3: 更新 API 路由使用 LiteLLM

**文件**: `backend/api/chat.py`

修改导入和服务调用:

```python
# 替换
from services.llm_proxy import get_llm_proxy_service

# 为
from services.litellm_service import get_litellm_service, get_http_status_for_exception
from litellm.exceptions import (
    AuthenticationError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
    APIConnectionError,
)
```

修改 `chat_completions` 函数的异常处理:

```python
@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    # ... 验证逻辑不变 ...

    service = get_litellm_service()  # 替换为 LiteLLM 服务

    try:
        if chat_request.stream:
            return StreamingResponse(
                service.chat_completion_stream(chat_request),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        else:
            response = await service.chat_completion(chat_request)
            return response

    # LiteLLM 异常处理
    except (AuthenticationError, RateLimitError, ServiceUnavailableError,
            Timeout, APIConnectionError) as e:
        status_code, error_code = get_http_status_for_exception(e)
        raise HTTPException(
            status_code=status_code,
            detail={"error": {"message": str(e), "code": error_code}}
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": {"message": f"Internal error: {e}", "code": "internal_error"}}
        )
```

---

### Step 4: 保留原有服务作为 Fallback

**不删除** `backend/services/llm_proxy.py`，保留作为回退选项。

在 `config.py` 添加开关:

```python
class Settings(BaseSettings):
    # ... 现有配置 ...

    # LLM 服务选择
    use_litellm: bool = True  # False 时回退到 httpx 直接转发
```

在 `api/chat.py` 添加条件判断:

```python
from config import get_settings

settings = get_settings()

if settings.use_litellm:
    from services.litellm_service import get_litellm_service as get_service
else:
    from services.llm_proxy import get_llm_proxy_service as get_service
```

---

### Step 5: 测试验证

#### 5.1 单元测试

**文件**: `backend/tests/test_litellm_service.py`

```python
import pytest
from unittest.mock import AsyncMock, patch
from services.litellm_service import LiteLLMService
from models.chat import ChatCompletionRequest, ProviderConfig, ChatMessage


@pytest.fixture
def service():
    return LiteLLMService()


@pytest.fixture
def sample_request():
    return ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role="user", content="Hello")],
        stream=False,
        temperature=0.7,
        provider=ProviderConfig(
            type="openai",
            api_key="sk-test",
            api_url="https://api.openai.com/v1",
        ),
    )


def test_get_litellm_model(service):
    provider = ProviderConfig(type="openai", api_key="", api_url="")
    assert service._get_litellm_model(provider, "gpt-4") == "openai/gpt-4"

    provider.type = "deepseek"
    assert service._get_litellm_model(provider, "deepseek-chat") == "deepseek/deepseek-chat"

    # Already has prefix
    assert service._get_litellm_model(provider, "custom/model") == "custom/model"


def test_get_api_base(service):
    provider = ProviderConfig(type="openai", api_key="", api_url="https://api.example.com/v1")
    assert service._get_api_base(provider) == "https://api.example.com/v1"

    # Force mode with #
    provider.api_url = "https://api.example.com/custom#"
    assert service._get_api_base(provider) == "https://api.example.com/custom"


@pytest.mark.asyncio
@patch("services.litellm_service.litellm.acompletion")
async def test_chat_completion(mock_acompletion, service, sample_request):
    mock_response = AsyncMock()
    mock_response.model_dump.return_value = {
        "id": "test",
        "choices": [{"message": {"content": "Hi!"}}],
    }
    mock_acompletion.return_value = mock_response

    result = await service.chat_completion(sample_request)

    assert result["id"] == "test"
    mock_acompletion.assert_called_once()
```

#### 5.2 集成测试

```bash
# 启动后端
cd backend && python main.py

# 测试非流式
curl -X POST http://localhost:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Say hi"}],
    "stream": false,
    "provider": {
      "type": "openai",
      "api_key": "YOUR_KEY",
      "api_url": "https://api.openai.com/v1"
    }
  }'

# 测试流式
curl -X POST http://localhost:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-reasoner",
    "messages": [{"role": "user", "content": "What is 2+2?"}],
    "stream": true,
    "include_reasoning": true,
    "provider": {
      "type": "deepseek",
      "api_key": "YOUR_KEY",
      "api_url": "https://api.deepseek.com"
    }
  }'
```

#### 5.3 对等性验证

使用 Flutter 应用分别测试:
1. 关闭 Python 后端开关 → 直连模式
2. 开启 Python 后端开关 → 代理模式

验证项:
- [ ] 流式输出速度一致
- [ ] thinking 内容正确显示 `<think>...</think>`
- [ ] 错误信息格式一致
- [ ] 参数生效（temperature, max_tokens）

---

## 4. 回滚策略

如果 LiteLLM 出现问题:

```bash
# 方式 1: 环境变量
export CHATBOX_BACKEND_USE_LITELLM=false

# 方式 2: 修改 config.py
use_litellm: bool = False
```

原有 `llm_proxy.py` 保持不变，可立即回滚。

---

## 5. 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/requirements.txt` | 修改 | 添加 `litellm>=1.50.0` |
| `backend/services/litellm_service.py` | 新增 | LiteLLM 服务封装 |
| `backend/api/chat.py` | 修改 | 切换到 LiteLLM 服务 |
| `backend/config.py` | 修改 | 添加 `use_litellm` 开关 |
| `backend/tests/test_litellm_service.py` | 新增 | 单元测试 |

**Flutter 端无需改动** - `ProxyOpenAIProvider` 已实现完整的 thinking 解析逻辑。

---

## 6. 后续扩展

LiteLLM 引入后可逐步启用:

1. **Cost Tracking** - `litellm.success_callback` 记录 token 消耗
2. **Fallback** - 配置多 Provider 自动切换
3. **Caching** - 启用 `litellm.cache` 减少重复请求
4. **Multimodal** - LiteLLM 已支持统一的多模态消息格式

---

## 7. 验收标准

- [ ] `pytest backend/tests/` 全部通过
- [ ] 流式 thinking 输出与直连一致
- [ ] 非流式响应格式与直连一致
- [ ] 错误场景返回正确 HTTP 状态码
- [ ] 回滚开关功能正常
