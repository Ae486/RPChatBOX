# 基础 LLM 请求链迁移分析总览

## 1. 目标

本文档用于承接 `docs/migration/backend-decoupling-methodology.md`，系统分析当前项目中 Flutter 前端承担的“基础 LLM 请求链”职责，并形成后续低风险迁移的输入。

本轮分析只回答 5 件事：

1. 当前链路实际上如何运行
2. Flutter 当前承担了哪些运行时职责
3. backend 已经接手了哪些、还缺哪些
4. 哪些能力必须解耦、哪些应保留前端、哪些可延后
5. 后续应如何按切片迁移，才能尽量不破坏现有功能

## 2. 范围

本轮分析只覆盖基础 LLM 请求链，不包含 RP：

- 消息发送入口
- Provider 创建与路由选择
- `direct / proxy / auto`
- 请求体拼装
- provider 配置与密钥边界
- `/models` 与 `/v1/chat/completions` 调用链
- SSE 流式解析
- thinking / reasoning 流语义
- fallback / circuit breaker
- UI 流状态与 backend 事件边界

明确排除：

- 全部 RP 代码与 RP 设计
- RP memory / context compiler / worker / agent
- MCP / tool 的完整迁移设计

说明：

- 代码中确实存在 RP 相关分支，例如 `lib/widgets/conversation_view_v2/streaming.dart` 中的 roleplay context 注入逻辑，但本次不纳入结论。

## 3. 方法

本轮分析遵循迁移规范中的三条原则：

1. 先理解现状，再谈解耦
2. 先冻结契约，再切片迁移
3. 先迁运行时权力，不先迁 UI

分析粒度分三层展开：

1. 整体：端到端执行链
2. 模块：前端与 backend 职责拆分
3. 关键函数/数据流：落到具体文件与关键函数

## 4. 当前前后端职责概览

### 4.1 Flutter 当前承担的核心职责

当前 Flutter 不只是 UI，仍承担了多项运行时职责：

- 发送入口与 prompt 组装
- Provider 实例创建
- backend 全局开关与路由选择
- direct / proxy 行为分叉
- 请求体拼装
- provider 配置与 API key 持有
- SSE 文本语义解析
- `<think>` 标签生成与 UI thinking 状态解析
- fallback / circuit breaker 逻辑定义
- UI 流状态管理与占位消息更新

关键实现：

- `lib/widgets/conversation_view_v2/streaming.dart`
- `lib/controllers/stream_output_controller.dart`
- `lib/adapters/ai_provider.dart`
- `lib/adapters/hybrid_langchain_provider.dart`
- `lib/adapters/proxy_openai_provider.dart`
- `lib/widgets/stream_manager.dart`
- `lib/services/model_service_manager.dart`
- `lib/services/fallback_policy.dart`
- `lib/services/circuit_breaker_service.dart`

### 4.2 backend 当前承担的核心职责

当前 backend 已具备“代理执行层 MVP”能力：

- `GET /api/health`
- `GET /models` / `GET /v1/models` 健康探测
- `POST /models` / `POST /v1/models` 上游模型列表透传
- `POST /v1/chat/completions`
- 上游请求执行
- SSE 中继
- LiteLLM / httpx 两种执行路径
- 基础超时、连接失败、HTTP 错误映射

关键实现：

- `backend/api/chat.py`
- `backend/services/llm_proxy.py`
- `backend/services/litellm_service.py`
- `backend/models/chat.py`

## 5. 本轮最重要的事实结论

### 5.1 当前“直连链”默认不是 `OpenAIProvider`

这是本轮分析中最重要的现实校正。

当前默认配置下：

- `ProviderFactory.useHybridLangChain = true`，定义在 `lib/adapters/ai_provider.dart:235`
- 当 `ProviderFactory.pythonBackendEnabled = false` 时，`createProviderWithRouting()` 会回落到 `createProvider()`，定义在 `lib/adapters/ai_provider.dart:273-277`
- `createProvider()` 默认返回的是 `HybridLangChainProvider`，定义在 `lib/adapters/ai_provider.dart:241-245`

因此，当前实际“直连链”是：

`Flutter -> HybridLangChainProvider -> upstream API`

而不是：

`Flutter -> OpenAIProvider -> upstream API`

`OpenAIProvider` 目前更接近遗留/回滚实现，而不是当前默认直连实现。

### 5.2 当前 backend 开启后，`backendMode` 实际被忽略

当全局 Python backend 开关开启时：

- `ProviderFactory.createProviderWithRouting()` 直接返回 `ProxyOpenAIProvider`
- `config.backendMode` 没有被实际使用

对应实现：

- `lib/adapters/ai_provider.dart:280-282`

因此当前运行事实是：

- `direct`: 仅在全局 backend 开关关闭时生效
- `proxy`: 全局 backend 开关开启时强制使用
- `auto`: 代码存在，但当前不在主运行链路中

### 5.3 `BackendRoutingProvider`、fallback、circuit breaker 当前并未进入主链路

`BackendRoutingProvider` 实现了 auto mode 逻辑，但本轮没有发现它被工厂实际创建。

证据：

- `BackendRoutingProvider` 定义于 `lib/adapters/backend_routing_provider.dart`
- 全仓库搜索仅发现其定义，没有发现工厂或运行链路中的实例化
- `createProviderWithRouting()` 当前只会返回 `createProvider()` 或 `ProxyOpenAIProvider`

因此：

- fallback policy 与 circuit breaker 的实现存在
- 但它们不是当前主链路的实际运行时真相

### 5.4 backend 已可用，但还不是完整后端中枢

当前 backend 已经能够支撑：

- 健康检查
- 模型探测
- chat completion 请求转发
- SSE 中继

但还没有完全接管：

- provider 路由权
- provider 配置与密钥托管
- 请求体规范化
- 流语义标准化
- fallback / circuit breaker
- 取消协议
- 统一可观测性

因此当前更准确的定位是：

**backend 已具备“基础请求代理 MVP”，但尚未完成“基础 LLM 请求链解耦收口”。**

## 6. 当前迁移判断

### 6.1 Flutter 长期应保留

- 聊天 UI
- 占位消息与消息列表渲染
- thinking 展示
- 流式 reveal 与渲染节奏控制
- 用户输入与页面交互
- 本地会话展示态
- backend 生命周期启动与切换入口

### 6.2 必须逐步迁往 backend

- provider 路由与真实运行模式选择
- provider 配置与 API key 托管
- 请求体规范化
- 错误语义标准化
- fallback / retry / circuit breaker
- SSE 语义标准化
- 后续 RAG / agent 的执行权

### 6.3 当前整体建议

不建议直接大改 UI 或重写整条链路。

建议路线是：

1. 先把现有链路写清楚并冻结契约
2. 先让 backend 接管更多“运行时权力”
3. 保持 Flutter 继续消费当前兼容的流式文本契约
4. 等 backend 真正成为中枢后，再考虑更大边界调整

## 7. 相关文档

- `docs/migration/backend-decoupling-methodology.md`
- `docs/migration/02-current-frontend-chain.md`
- `docs/migration/03-decoupling-scope.md`
- `docs/migration/04-decoupling-design.md`
- `docs/migration/05-testing-and-rollback.md`
- `docs/migration/06-risks-and-open-questions.md`
