# Backend Decoupling Methodology

## 1. 文档目的

本文档用于约束后续将 Flutter 前端中的基础 LLM 请求能力逐步解耦到 backend 的迁移工作，目标是：

- 降低迁移过程中破坏现有链路的概率
- 明确前后端边界，避免职责混乱
- 在不做大爆炸重写的前提下完成架构收口
- 为后续 RAG / agent 能力落地提供稳定底座

本文档是迁移规范，不是实现方案细节文档。

## 2. 当前讨论范围

当前迁移范围只包含基础 LLM 请求链，不包含 RP 相关能力。

明确排除：

- roleplay 相关代码
- RP memory / context compiler / RP worker
- RP agent 设计

当前只关注：

- Flutter -> backend -> upstream LLM 的请求链
- provider 路由与代理
- 流式输出
- 模型列表探测
- 错误处理
- 后续为 RAG / agent 留出后端中枢能力

## 3. 当前架构基线

### 3.1 Flutter 当前承担的职责

当前 Flutter 仍然承担了较多运行时职责，而不仅仅是 UI：

- provider 创建与路由开关
- direct / proxy / auto 模式选择
- 部分请求体拼装
- provider 配置与 API key 持有
- 流式 chunk 语义解析
- thinking / reasoning 标签转换
- fallback 与 circuit breaker 逻辑
- UI 流状态管理

关键文件：

- `lib/widgets/conversation_view_v2/streaming.dart`
- `lib/adapters/ai_provider.dart`
- `lib/adapters/backend_routing_provider.dart`
- `lib/adapters/openai_provider.dart`
- `lib/adapters/proxy_openai_provider.dart`
- `lib/widgets/stream_manager.dart`
- `lib/services/model_service_manager.dart`
- `lib/services/circuit_breaker_service.dart`
- `lib/services/fallback_policy.dart`

### 3.2 Backend 当前已承担的职责

backend 已经具备基础 LLM 代理 MVP 能力：

- `/api/health`
- `/models` / `/v1/models`
- `/v1/chat/completions`
- 非流式请求代理
- SSE 流式中继
- LiteLLM 或 httpx 两种上游执行路径
- 基础超时、连接失败、上游 HTTP 错误映射

关键文件：

- `backend/main.py`
- `backend/api/chat.py`
- `backend/api/health.py`
- `backend/services/llm_proxy.py`
- `backend/services/litellm_service.py`
- `backend/models/chat.py`

## 4. 迁移总原则

### 4.1 不做大爆炸重写

禁止一次性重写整条链路。正确做法是：

- 目标架构一次设计清楚
- 实现按责任切片逐步替换
- 每一刀都能回滚

### 4.2 先冻结契约，再迁移实现

在迁移初期，Flutter 与 backend 之间的请求协议、SSE 协议、错误结构尽量不改。

原因：

- 一次同时修改“边界契约”和“执行实现”会放大排错成本
- 先保持契约稳定，才能逐步把运行时权力转移到 backend

### 4.3 先迁移运行时权力，不先迁移 UI

Flutter 在短期内应继续负责：

- 消息 UI
- 流式展示
- thinking 展示
- 输入框与交互
- 本地草稿和展示态缓存

优先迁出的应是：

- 上游请求执行权
- provider 路由权
- provider 配置与密钥托管
- 流语义标准化
- 后端错误与重试策略

### 4.4 以行为兼容为首要目标

迁移的第一目标不是“代码更漂亮”，而是：

- 行为不变
- 用户无感
- 链路稳定
- 可验证

## 5. 迁移前必须完成的理解工作

在任何解耦动作开始前，必须先读懂以下链路：

### 5.1 消息发送入口

需要明确：

- 用户消息如何进入发送链
- prompt 如何组装
- summary 如何注入
- provider 在哪里实例化
- 回调如何驱动 UI 更新

重点文件：

- `lib/widgets/conversation_view_v2/streaming.dart`

### 5.2 Provider 选择与路由逻辑

需要明确：

- 当前是否强制 proxy
- direct / proxy / auto 实际行为
- fallback 触发条件
- circuit breaker 状态机

重点文件：

- `lib/adapters/ai_provider.dart`
- `lib/adapters/backend_routing_provider.dart`
- `lib/services/fallback_policy.dart`
- `lib/services/circuit_breaker_service.dart`

### 5.3 直连与代理两条请求链

需要逐项比对：

- 请求头
- 请求体字段
- 文件/附件处理
- stream/non-stream 差异
- provider 特殊字段
- reasoning/thinking 兼容逻辑

重点文件：

- `lib/adapters/openai_provider.dart`
- `lib/adapters/proxy_openai_provider.dart`

### 5.4 UI 流状态语义

必须明确：

- `<think>` 如何被解析
- thinking 内容和正文内容如何分离
- 工具调用事件如何进入 UI
- 流中断、完成、错误如何落 UI

重点文件：

- `lib/widgets/stream_manager.dart`

### 5.5 后端当前请求执行方式

必须明确：

- backend 如何选择 LiteLLM / httpx
- 上游 URL 如何拼接
- SSE 如何中继
- 错误如何映射
- `/models` 如何作为探测与透传接口

重点文件：

- `backend/api/chat.py`
- `backend/services/llm_proxy.py`
- `backend/services/litellm_service.py`
- `backend/models/chat.py`

## 6. 迁移边界定义

### 6.1 Flutter 长期保留的职责

- UI 渲染
- 消息列表与占位消息展示
- thinking/tool 状态展示
- 用户输入与交互
- 前端本地缓存与展示态状态
- 桌面端 backend 生命周期拉起与切换入口

### 6.2 必须逐步迁移到 backend 的职责

- 上游模型请求执行
- provider 路由决策
- provider 配置与密钥托管
- 流语义标准化
- 错误语义标准化
- retry / timeout / fallback / circuit breaker 的后端化
- RAG 检索、上下文注入
- agent 执行循环

### 6.3 当前阶段不应迁移的部分

- 聊天 UI 结构
- `StreamManager` 的纯显示层能力
- 页面层交互状态
- 与 RP 相关的一切内容

## 7. 推荐迁移顺序

迁移顺序必须按“责任切片”进行，而不是按目录或模块名粗暴搬运。

### Phase 0：基线与契约冻结

目标：

- 确认当前主链路可运行
- 固定当前 Flutter <-> backend 契约
- 收集真实行为样本

产出：

- 请求体样本
- SSE chunk 样本
- 错误响应样本
- fallback 行为样本
- 当前可回归测试清单

### Phase 1：保持现有契约，强化 backend 执行层

目标：

- backend 完整接管上游请求执行
- 在不改前端 UI 行为的情况下稳定代理链路

此阶段允许 Flutter 继续：

- 传 provider 信息
- 解析流 chunk
- 保留路由开关

### Phase 2：流语义与错误语义后端化

目标：

- backend 输出统一流事件语义
- 减少 Flutter 对 provider 差异的理解

迁移后：

- Flutter 主要消费标准化事件
- backend 处理 reasoning / content / tool / error 语义

### Phase 3：provider / secret / routing authority 后端化

目标：

- backend 成为 provider 配置与密钥真源
- routing / fallback / circuit breaker 全部以后端为准

迁移后：

- Flutter 不再每次携带完整 provider 配置
- Flutter 只传会话级或模型级引用信息

### Phase 4：RAG 与 agent 能力接入

前提：

- 基础请求链稳定
- 标准事件语义稳定
- 后端已成为运行时中枢

此阶段再实现：

- 检索
- 索引
- 上下文拼接
- agent loop
- tool runtime

## 8. 测试方法论

### 8.1 Characterization Tests

用途：

- 固定当前行为，而不是评价当前设计优劣

必须覆盖：

- direct 模式流式输出
- proxy 模式流式输出
- auto 模式 fallback
- thinking 标签输出
- `/models` 拉取行为

### 8.2 Contract Tests

必须为 backend 建立接口契约测试：

- `GET /api/health`
- `GET /models`
- `POST /models`
- `POST /v1/chat/completions`
- SSE 返回格式
- 错误响应结构

### 8.3 SSE Replay Tests

这是迁移中最关键的测试类型之一。

必须使用真实或录制的样本回放：

- OpenAI 风格 chunk
- Gemini 风格 chunk
- Claude 风格 chunk
- 半路报错
- 半路断流
- 空 chunk / 非法 chunk

验证点：

- 正文不丢
- thinking 不串位
- 不重复输出
- 结束标记正确

### 8.4 Integration Tests

backend 应使用 mock upstream 做集成测试，至少覆盖：

- 上游超时
- 401 / 403
- 429
- 500 / 502 / 503 / 504
- malformed JSON
- SSE 中途断开

### 8.5 UI Regression Tests

Flutter 侧重点不是验证 backend 内部，而是验证显示语义：

- placeholder 是否正确
- thinking 是否正确开闭
- 错误信息是否正常展示
- 完成态与中断态是否正确收口

### 8.6 回归策略

每完成一个迁移切片，至少需要执行：

- backend 单测
- backend contract tests
- Flutter 关键单测
- 一次桌面端真实联调
- 一次 proxy 模式真实 smoke test

## 9. 可回滚要求

每一个迁移阶段都必须保留回滚能力。

必须满足：

- 保留 feature flag
- 保留旧链路入口
- 可以按 provider 或模式粒度切回
- 不依赖手工改代码回滚

禁止：

- 尚未验证完成就删除旧链路
- 一边迁移一边大量改 UI
- 没有 fallback 就直接替换生产链路

## 10. 可观测性要求

为了保证迁移定位问题足够快，backend 至少要补齐以下基础观测：

- request id
- provider type
- model name
- route mode
- upstream target
- error category
- stream start / first token / done / error 时间点

如果没有观测能力，迁移时出现问题将很难判断：

- 是前端解析错
- 是 backend 契约错
- 是上游模型错
- 是 fallback 错

## 11. 迁移时最容易出错的细节

### 11.1 一边改契约，一边改逻辑

这是最危险的做法。  
必须拆开处理。

### 11.2 流式语义不一致

最常见问题：

- reasoning 混进正文
- thinking 结束标签漏掉
- 同一个 chunk 被重复消费
- `DONE` 处理不一致

### 11.3 fallback 条件变化

如果 fallback 规则迁移到 backend 后与前端旧逻辑不一致，会出现：

- 本应回退却没回退
- 本不该回退却回退
- 半路已经出字后又回退导致重复回复

### 11.4 provider 配置边界不清

迁移过程中如果同时存在：

- 前端 provider 配置
- backend provider 配置

必须定义清楚谁是真源。  
否则极易出现“前端以为用了 A，backend 实际用了 B”的问题。

### 11.5 测试只测 happy path

迁移失败大多不是出在 happy path，而是：

- 半路断流
- 429
- 认证错误
- 超时
- chunk 畸形
- 用户取消

### 11.6 UI 与 backend 同时大改

迁移阶段应避免同时改：

- 流事件协议
- UI 渲染逻辑
- placeholder 策略
- thinking 展示策略

否则排错难度会指数级上升。

## 12. 迁移切片完成的验收标准

每一个迁移切片完成后，至少满足：

- 主链路 smoke test 通过
- 关键 contract tests 通过
- 不引入新的 UI 可见回归
- 有明确回滚路径
- 已记录已知限制
- 已更新迁移文档与 MEMORY

## 13. 当前推荐结论

对于本项目，迁移的正确姿势是：

- 先读懂前端已有请求链
- 先固定当前契约与行为基线
- 先迁移 backend 运行时权力
- 后迁移语义与配置真源
- 最后再落 RAG / agent

一句话总结：

> 目标架构可以一次设计到位，但代码迁移必须按契约、测试、回滚三件事约束下分阶段完成，不能一口气重写。
