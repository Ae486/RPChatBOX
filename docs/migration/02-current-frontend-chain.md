# 当前 Flutter 基础 LLM 请求链

## 1. 端到端执行链

当前基础 LLM 请求链可分为 8 段：

1. `main.dart` 恢复全局 backend 开关
2. 聊天页发送入口 `_sendMessage()`
3. `_startAssistantResponse()` 组装消息与参数
4. `ModelServiceManager.createProviderInstance()` 创建 provider
5. `ProviderFactory.createProviderWithRouting()` 选择实际 provider
6. provider 执行 `sendMessageStream()`
7. `StreamOutputController.startStreaming()` 订阅 provider 输出
8. `StreamManager.append()` 解析 `<think>` 并驱动 UI 更新

简化后的当前链路如下：

```text
main.dart
  -> 恢复 ProviderFactory.pythonBackendEnabled
  -> Chat UI 发送
  -> conversation_view_v2/streaming.dart::_sendMessage()
  -> _startAssistantResponse()
  -> ModelServiceManager.createProviderInstance()
  -> ProviderFactory.createProviderWithRouting()
     -> backend 开关关: HybridLangChainProvider
     -> backend 开关开: ProxyOpenAIProvider
  -> provider.sendMessageStream()
  -> StreamOutputController.startStreaming()
  -> onChunk -> _handleStreamFlush()
  -> StreamManager.append()
  -> UI 占位消息 / thinking 状态更新
```

## 2. 整体层面：各模块职责

### 2.1 发送入口层

核心文件：

- `lib/widgets/conversation_view_v2/streaming.dart`

关键函数：

- `_sendMessage()` at `streaming.dart:9`
- `_startAssistantResponse()` at `streaming.dart:77`
- `_handleStreamFlush()` at `streaming.dart:325`
- `_finalizeStreamingMessage()` at `streaming.dart:773`
- `_stopStreaming()` at `streaming.dart:903`

职责：

- 读取输入框和附件状态
- 生成用户消息并写入会话线程/UI
- 组装发送前的 `chatMessages`
- 选择 provider 并启动流式输出
- 接收 chunk，更新 placeholder
- 最终持久化 assistant 消息

说明：

- 该文件中包含 RP 相关分支，但本次分析排除；本轮只关注其通用聊天主链。

### 2.2 Provider 工厂与路由层

核心文件：

- `lib/services/model_service_manager.dart`
- `lib/adapters/ai_provider.dart`

关键函数：

- `ModelServiceManager.createProviderInstance()` at `model_service_manager.dart:263`
- `ProviderFactory.createProvider()` at `ai_provider.dart:241`
- `ProviderFactory.createProviderWithRouting()` at `ai_provider.dart:273`

职责：

- 从本地持久化 provider 配置创建运行时 provider 实例
- 根据全局 backend 开关选择直连或代理实现
- 决定当前请求链是走前端直连还是 backend 代理

当前运行事实：

- `pythonBackendEnabled == false` -> `createProvider()` -> `HybridLangChainProvider`
- `pythonBackendEnabled == true` -> `ProxyOpenAIProvider`
- `backendMode` 虽存在于 `ProviderConfig`，但当前 factory 未按 `direct / proxy / auto` 分支实例化

### 2.3 请求执行层

当前存在两条实现链：

1. 直连链：`HybridLangChainProvider`
2. 代理链：`ProxyOpenAIProvider -> backend -> upstream`

另有遗留/回滚实现：

- `OpenAIProvider`
- `BackendRoutingProvider`

但它们不是当前默认主链。

### 2.4 UI 流状态层

核心文件：

- `lib/controllers/stream_output_controller.dart`
- `lib/widgets/stream_manager.dart`

关键函数：

- `StreamOutputController.startStreaming()` at `stream_output_controller.dart:34`
- `StreamOutputController.stop()` at `stream_output_controller.dart:97`
- `StreamManager.createStream()` at `stream_manager.dart:88`
- `StreamManager.append()` at `stream_manager.dart:107`
- `StreamManager._parseThinkingContent()` at `stream_manager.dart:129`

职责：

- 订阅 provider 的字符串流
- 缓冲和分发 chunk
- 将 `<think>...</think>` 从正文中拆出，维护 thinking 状态
- 将正文内容与 thinking 内容分别写入 UI 状态容器

当前边界非常重要：

**UI 当前消费的是 `Stream<String>`，而不是结构化事件流。**

也就是说，前端并不是直接消费 backend 的 SSE JSON，而是消费 provider 最终“解释过”的文本 chunk。

## 3. 模块层面：关键实现链

### 3.1 入口与 prompt 组装

#### `_sendMessage()`

位置：

- `lib/widgets/conversation_view_v2/streaming.dart:9`

做的事：

- 校验输入与模型
- 生成用户消息并插入当前会话/线程
- 更新 UI
- 调用 `_startAssistantResponse()`

#### `_startAssistantResponse()`

位置：

- `lib/widgets/conversation_view_v2/streaming.dart:77`

做的事：

- 创建 assistant placeholder 与 `streamId`
- 创建 `StreamManager` 流状态
- 构造 `chatMessages`
- 估算 prompt tokens
- 通过 `globalModelServiceManager.createProviderInstance()` 创建 provider
- 调用 `_streamController.startStreaming()`

本次范围内需要特别注意的实现点：

- system prompt 会被加入 `chatMessages`
- 历史消息按 `contextLength` 截断
- summary 会在满足条件时注入系统消息
- provider 创建发生在这里，而不是 UI 更外层

### 3.2 Provider 创建与路由选择

#### `createProviderInstance()`

位置：

- `lib/services/model_service_manager.dart:263`

做的事：

- 根据 providerId 从 `SharedPreferences` 中恢复的 `ProviderConfig` 创建 provider

#### `createProviderWithRouting()`

位置：

- `lib/adapters/ai_provider.dart:273`

当前行为：

- 如果 `pythonBackendEnabled` 为 `false`，返回 `createProvider(config)`
- 如果 `pythonBackendEnabled` 为 `true`，直接返回 `ProxyOpenAIProvider(config)`

这意味着：

- 当前路由判断依赖全局布尔开关，而不是 provider 粒度的 `backendMode`
- auto mode 没有进入主链
- backend 是否启用，是 UI/本地配置层的决定，不是 backend 自己的路由能力

### 3.3 当前直连链：`HybridLangChainProvider`

核心文件：

- `lib/adapters/hybrid_langchain_provider.dart`

关键函数：

- `testConnection()` at `hybrid_langchain_provider.dart:67`
- `listAvailableModels()` at `hybrid_langchain_provider.dart:111`
- `sendMessageStream()` at `hybrid_langchain_provider.dart:136`
- `sendMessage()` at `hybrid_langchain_provider.dart:364`
- `_buildRequestBody()` at `hybrid_langchain_provider.dart:436`
- `_convertMessages()` at `hybrid_langchain_provider.dart:515`

基础 LLM 请求链相关职责：

- 直连上游 API
- 构建请求头，持有 `Authorization: Bearer ${config.apiKey}`
- 构建请求体
- 按 provider 类型裁剪参数
- 处理附件与多模态消息
- 解析 SSE 为文本 chunk
- 生成 `<think>` / `</think>` 标签

当前请求体特点：

- `messages` 通过 `_convertMessages()` 规范化
- 会过滤空 `system` 消息
- 支持将附件转换为文本/图片多模态内容
- 默认带 `include_reasoning: true`
- Gemini 会带 `extra_body.google.thinking_config.include_thoughts = true`

说明：

- 该 provider 同时带 MCP/tool 相关逻辑，但不属于本轮范围；这里只使用其基础聊天职责。

### 3.4 当前代理链：`ProxyOpenAIProvider`

核心文件：

- `lib/adapters/proxy_openai_provider.dart`

关键函数：

- `_buildProxyHeaders()` at `proxy_openai_provider.dart:23`
- `_buildProviderPayload()` at `proxy_openai_provider.dart:34`
- `_buildRequestBody()` at `proxy_openai_provider.dart:43`
- `testConnection()` at `proxy_openai_provider.dart:79`
- `listAvailableModels()` at `proxy_openai_provider.dart:104`
- `sendMessageStream()` at `proxy_openai_provider.dart:130`
- `sendMessage()` at `proxy_openai_provider.dart:325`

基础职责：

- 向本地 backend 发送 `POST /v1/chat/completions`
- 将 provider 配置一并打包到请求体里的 `provider`
- 订阅 backend 的 SSE 输出
- 在前端继续把 SSE JSON 解析为文本 chunk
- 在前端继续生成 `<think>` / `</think>` 标签

当前请求体特点：

- `messages` 直接来自 `messages.map((m) => m.toJson()).toList()`
- `provider` 中包含 `type / api_key / api_url / custom_headers`
- 参数为显式展开字段：`temperature / max_tokens / top_p / frequency_penalty / presence_penalty`
- 默认带 `include_reasoning: true`
- Gemini 同样带 `extra_body`

与直连链的关键差异：

1. **附件未做同等处理**
   - `ProxyOpenAIProvider._buildRequestBody()` 接收 `files`
   - 但当前实现中未使用 `files`
   - 与 `HybridLangChainProvider._convertMessages()` 的附件处理能力不一致

2. **流语义仍在前端解析**
   - backend 只中继 SSE
   - thinking / reasoning 的语义归一仍由 Flutter 完成

3. **密钥边界仍在前端**
   - `api_key` 每次请求都会从 Flutter 发给 backend

### 3.5 backend 当前调用链

入口：

- `backend/api/chat.py:31` `chat_completions()`

执行分支：

- `_get_llm_service()` at `chat.py:17`
- 若可用则优先走 `LiteLLMService`
- 否则走 `LLMProxyService`

LiteLLM 路径：

- `backend/services/litellm_service.py`
- `_get_api_base()` at `litellm_service.py:41` 会剥离 Flutter 传来的完整 endpoint suffix
- `_build_completion_kwargs()` at `litellm_service.py:64` 负责构建 LiteLLM 参数

httpx 路径：

- `backend/services/llm_proxy.py`
- `_get_upstream_url()` at `llm_proxy.py:35`
- `_build_headers()` at `llm_proxy.py:54`
- `_build_request_body()` at `llm_proxy.py:64`

当前 backend 对 `/models` 的双重语义：

- `GET /models` at `chat.py:116`：仅返回健康检查哨兵模型
- `POST /models` at `chat.py:126`：需要请求体中的 `provider`，用于实际查询上游模型列表

## 4. 关键数据流

### 4.1 配置与密钥数据流

当前数据流：

`SharedPreferences -> ProviderConfig -> ModelServiceManager -> ProviderFactory -> provider -> request body / headers`

结论：

- provider 配置与 API key 的真源仍在 Flutter 本地
- backend 目前只是“被动接受前端传来的 provider 描述”

### 4.2 SSE 与 thinking 数据流

当前数据流：

`upstream SSE -> (direct provider 或 backend 中继) -> Flutter provider 解析 JSON -> 产出 String chunk + <think> 标签 -> StreamOutputController -> StreamManager -> UI`

这意味着：

- Flutter provider 是“语义翻译器”
- `StreamManager` 是“显示态解释器”
- backend 还不是 thinking / reasoning 语义的唯一真源

### 4.3 取消数据流

当前关键实现：

- `_stopStreaming()` at `streaming.dart:903`
- `StreamOutputController.stop()` at `stream_output_controller.dart:97`
- `OpenAIProvider.cancelRequest()` at `openai_provider.dart:368`
- `HybridLangChainProvider.cancelRequest()` at `hybrid_langchain_provider.dart:426`

当前问题：

1. `_stopStreaming()` 只在 `provider.runtimeType.toString().contains('OpenAI')` 时尝试动态调用 `cancelRequest()`
2. `HybridLangChainProvider` 不包含 `OpenAI` 字样，因此默认直连链不会走到其 `cancelRequest()`
3. `ProxyOpenAIProvider` 当前没有实现 `cancelRequest()`
4. backend 也没有显式的取消接口

因此当前取消链路的实际状态是：

- UI 可以停止订阅与渲染
- 但网络层与 backend/upstream 取消并不完整

这属于后续迁移的高风险点。

## 5. 当前主链中的遗留/非主链组件

### 5.1 `OpenAIProvider`

位置：

- `lib/adapters/openai_provider.dart`

状态：

- 仍然是完整的直连实现
- 但当前默认配置下不是主链
- 更像回滚实现

### 5.2 `BackendRoutingProvider`

位置：

- `lib/adapters/backend_routing_provider.dart`

状态：

- 定义了完整 auto mode + fallback + circuit breaker 行为
- 但当前 factory 未实例化
- 属于“已实现但未接入当前主链”

## 6. 当前链路结论

当前 Flutter 基础 LLM 请求链的真实情况不是“UI 薄层 + backend 中枢”，而是：

- 发送入口在 Flutter
- 路由决策在 Flutter
- provider 配置与密钥真源在 Flutter
- 流语义翻译在 Flutter
- UI 状态解释在 Flutter
- backend 主要承担上游执行和中继

因此，后续迁移的关键不是“让 backend 能发请求”，而是**逐步把运行时真相从 Flutter 收口到 backend。**
