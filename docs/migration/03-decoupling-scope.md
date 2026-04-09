# 基础 LLM 请求链解耦范围

## 1. 分类原则

本轮将候选能力分为三类：

1. 前端保留
2. 必须解耦到 backend
3. 可延后解耦

判断标准：

- 是否属于运行时真相
- 是否需要成为后续 agent / RAG 底座
- 是否会影响当前 UI 契约稳定
- 是否已有 backend 承接点

## 2. 前端保留清单

### 2.1 消息 UI 与占位消息更新

- 当前职责：消息插入、placeholder、逐步 reveal、滚动跟随
- 代码位置：
  - `lib/widgets/conversation_view_v2/streaming.dart`
  - `lib/controllers/stream_output_controller.dart`
- 原因：
  - 属于展示层
  - 与 backend 迁移无直接冲突
- 推荐阶段：长期保留前端
- 风险：低
- 测试方式：
  - widget / golden / manual regression

### 2.2 `StreamManager` 的显示态管理

- 当前职责：将 `<think>` 与正文分离，维护 `StreamData`
- 代码位置：
  - `lib/widgets/stream_manager.dart`
- 原因：
  - 当前 UI 直接依赖其状态结构
  - 短期没必要迁往 backend
- 推荐阶段：长期保留前端
- 风险：低
- 测试方式：
  - unit tests for `<think>` parse / completion / error state

### 2.3 用户输入与本地会话展示态

- 当前职责：输入框、附件栏、线程显示态、局部缓存
- 代码位置：
  - `lib/widgets/conversation_view_v2/*`
  - `lib/models/*`
- 原因：
  - 属于交互与展示，不属于 backend 中枢职责
- 推荐阶段：长期保留前端
- 风险：低
- 测试方式：
  - manual UI regression

### 2.4 backend 生命周期拉起与开关入口

- 当前职责：桌面端启动 backend，设置页切换 backend 开关
- 代码位置：
  - `lib/main.dart`
  - `lib/pages/settings_page.dart`
  - `lib/services/backend_lifecycle_desktop.dart`
- 原因：
  - 这是桌面应用壳层能力
- 推荐阶段：前端保留
- 风险：低
- 测试方式：
  - manual smoke test

## 3. 必须解耦清单

### 3.1 Provider 路由决策

- 当前职责：
  - `pythonBackendEnabled` 决定走直连还是代理
  - `backendMode` 未真正生效
- 代码位置：
  - `lib/adapters/ai_provider.dart:273`
- 上下游依赖：
  - 上游：`ModelServiceManager.createProviderInstance()`
  - 下游：`HybridLangChainProvider` / `ProxyOpenAIProvider`
- 为什么应迁往 backend：
  - 路由是运行时真相，应由 backend 控制
  - 后续 fallback / circuit breaker / provider registry 都依赖此能力
- 推荐迁移阶段：
  - Phase 2
- 迁移风险：
  - 会影响 direct/proxy/auto 行为兼容性
- 对应测试：
  - provider routing characterization tests
  - backend integration tests for route selection

### 3.2 Provider 配置与 API key 真源

- 当前职责：
  - Flutter 本地持有 provider 配置、URL、API key、custom headers
  - proxy 请求时每次将这些信息发给 backend
- 代码位置：
  - `lib/models/provider_config.dart`
  - `lib/services/model_service_manager.dart`
  - `lib/adapters/proxy_openai_provider.dart:34`
- 上下游依赖：
  - 上游：本地 `SharedPreferences`
  - 下游：proxy/backend 请求体
- 为什么应迁往 backend：
  - 安全边界不正确
  - backend 无法成为配置真源
  - 不利于后续统一路由/审计/观测
- 推荐迁移阶段：
  - Phase 3
- 迁移风险：
  - 涉及配置迁移与兼容策略
- 对应测试：
  - config migration tests
  - backend auth/config contract tests

### 3.3 请求体规范化

- 当前职责：
  - Flutter provider 负责决定 message 结构、参数裁剪、reasoning 参数、Gemini 特殊字段
- 代码位置：
  - `lib/adapters/hybrid_langchain_provider.dart:436`
  - `lib/adapters/proxy_openai_provider.dart:43`
  - `lib/adapters/openai_provider.dart:378`
- 上下游依赖：
  - 上游：`chatMessages`、conversation settings、附件
  - 下游：upstream API 或 backend `/v1/chat/completions`
- 为什么应迁往 backend：
  - 当前 direct 与 proxy 请求体不一致
  - 后续统一 provider 兼容层必须收口
- 推荐迁移阶段：
  - Phase 1
- 迁移风险：
  - 会直接影响 provider 兼容性与请求行为
- 对应测试：
  - request snapshot tests
  - upstream mock integration tests

### 3.4 流语义标准化

- 当前职责：
  - Flutter provider 将 SSE JSON 解释为正文 chunk 与 `<think>` 标签
- 代码位置：
  - `lib/adapters/hybrid_langchain_provider.dart:136`
  - `lib/adapters/proxy_openai_provider.dart:130`
  - `lib/adapters/openai_provider.dart:105`
- 上下游依赖：
  - 上游：SSE JSON chunk
  - 下游：`StreamOutputController`、`StreamManager`
- 为什么应迁往 backend：
  - 语义翻译器不应长期在前端
  - 后续 agent / RAG / tool / reasoning 都需要统一事件源
- 推荐迁移阶段：
  - Phase 1，先保持文本契约不变
- 迁移风险：
  - 极高，直接影响 thinking 展示与正文增量输出
- 对应测试：
  - SSE replay tests
  - UI regression tests on `<think>` behavior

### 3.5 fallback / circuit breaker 运行时决策

- 当前职责：
  - 代码存在于 Flutter，但当前主链未实际启用
- 代码位置：
  - `lib/adapters/backend_routing_provider.dart`
  - `lib/services/fallback_policy.dart`
  - `lib/services/circuit_breaker_service.dart`
- 上下游依赖：
  - 上游：provider routing
  - 下游：proxy/direct 请求切换
- 为什么应迁往 backend：
  - 这是服务端韧性策略，不应放在 UI 客户端
  - 后续一旦 backend 成为中枢，这些策略天然属于 backend
- 推荐迁移阶段：
  - Phase 2
- 迁移风险：
  - 中，当前未真正接线，迁移时主要风险在行为定义而不是兼容旧逻辑
- 对应测试：
  - error classification tests
  - circuit breaker state transition tests
  - integration tests with injected 5xx / timeout / auth errors

### 3.6 模型列表语义与 provider 探测逻辑

- 当前职责：
  - Flutter 区分 `GET /models` 健康探测与 `POST /models` 上游模型列表
- 代码位置：
  - `lib/adapters/proxy_openai_provider.dart:79`
  - `lib/adapters/proxy_openai_provider.dart:104`
  - `backend/api/chat.py:116`
  - `backend/api/chat.py:126`
- 上下游依赖：
  - 上游：provider 配置
  - 下游：设置页、模型选择逻辑
- 为什么应迁往 backend：
  - 探测与模型查询语义应由 backend 统一定义
- 推荐迁移阶段：
  - Phase 2 或 3
- 迁移风险：
  - 低到中
- 对应测试：
  - API contract tests for `GET /models` vs `POST /models`

## 4. 可延后解耦清单

### 4.1 附件 / 多模态消息规范化

- 当前职责：
  - 直连链支持 `_convertMessages(files)`
  - proxy 链当前未对 `files` 做同等处理
- 代码位置：
  - `hybrid_langchain_provider.dart:515`
  - `proxy_openai_provider.dart:43`
- 为什么可延后：
  - 如果首阶段目标只要求“文本聊天基础链”，可暂不作为第一刀
- 为什么不能永久延后：
  - 否则 proxy 与 direct 行为永远不一致
- 推荐迁移阶段：
  - Phase 1B 或 Phase 2
- 迁移风险：
  - 中
- 对应测试：
  - attachment request snapshot tests
  - multimodal integration tests

### 4.2 取消协议

- 当前职责：
  - 前端可停止渲染和订阅
  - 网络层与 backend 取消不完整
- 代码位置：
  - `streaming.dart:903`
  - `stream_output_controller.dart:97`
- 为什么可延后：
  - 不阻塞基础“能用”的请求链
- 为什么不能长期缺失：
  - 会浪费 token 与后端连接
  - 对长输出和未来 agent 很关键
- 推荐迁移阶段：
  - Phase 2
- 迁移风险：
  - 中
- 对应测试：
  - cancel integration tests
  - long stream interruption tests

### 4.3 `OpenAIProvider` 遗留实现清理

- 当前职责：
  - 作为非默认直连实现存在
- 代码位置：
  - `lib/adapters/openai_provider.dart`
- 为什么可延后：
  - 首阶段不需要立即删除
  - 可作为回滚参考实现
- 推荐迁移阶段：
  - 最后阶段
- 迁移风险：
  - 低
- 对应测试：
  - none required before final cleanup

## 5. backend 已接手 / 部分接手 / 未接手

### 5.1 已接手

- `/v1/chat/completions` 入口
- 上游请求执行
- SSE 中继
- `/models` 健康探测
- `POST /models` 上游模型列表透传
- 基础错误映射

### 5.2 部分接手

- provider 兼容层
  - backend 能执行
  - 但 provider 配置真源仍在前端
- 请求体构建
  - backend 能构建上游 body
  - 但前端仍主导输入 body 结构

### 5.3 尚未接手

- 路由决策
- provider / secret 托管
- 流语义真相
- fallback / circuit breaker
- 取消协议
- 统一观测

## 6. 本轮范围清单结论

### 6.1 必须解耦

- 路由决策
- provider 配置与 API key 真源
- 请求体规范化
- 流语义标准化
- fallback / circuit breaker
- 模型探测语义

### 6.2 前端保留

- UI
- thinking 展示
- `StreamManager` 显示态
- 输入与交互
- backend 生命周期与桌面集成

### 6.3 可延后

- 附件/多模态对齐
- 取消协议
- 遗留 provider 清理
