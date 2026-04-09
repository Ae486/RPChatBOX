# 基础 LLM 请求链解耦设计

## 1. 设计原则

### 1.1 先保持契约，再迁移实现

当前 Flutter UI 消费的不是结构化事件，而是 `Stream<String>` 文本流，并依赖 `<think>` 标签驱动 `StreamManager`。

因此首阶段不能直接把前后端边界改成全新的 typed event 协议。首阶段应遵循：

- backend 可以替换执行实现
- 但 Flutter 继续消费兼容的文本 chunk
- thinking 仍以 `<think>` 标签维持兼容

### 1.2 先收口运行时权力，不先动 UI

短期不要动：

- `conversation_view_v2` 的 UI 结构
- `StreamManager` 数据结构
- placeholder / reveal / scroll 行为

优先迁出：

- provider 路由权
- provider 配置与 key 真源
- 请求体规范化
- 流语义归一
- 服务端 fallback / circuit breaker

### 1.3 每一刀都要能回滚

每个阶段都要保留 feature flag 或切换手段，确保可以：

- 回到旧 provider 路径
- 回到旧 SSE 解释路径
- 回到旧配置来源

## 2. 当前边界与目标边界

## 2.1 当前边界

当前边界如下：

```text
Flutter
  - 路由选择
  - provider 配置与 key
  - 请求体规范化
  - SSE 语义解释
  - UI 流状态

backend
  - 上游请求执行
  - SSE 中继
  - 基础错误映射
```

## 2.2 目标边界

建议目标边界如下：

```text
Flutter
  - UI
  - 文本流展示
  - thinking 展示
  - 本地展示态

backend
  - provider registry / key custody
  - route selection
  - request normalization
  - upstream execution
  - stream normalization
  - fallback / retry / circuit breaker
  - observability
```

## 3. 推荐迁移切片

## 3.1 Phase 0：基线冻结

目标：

- 固定当前 Flutter <-> backend 契约
- 记录当前真实行为

需要冻结的内容：

1. proxy 请求体样本
2. direct 请求体样本
3. `/v1/chat/completions` 成功/错误结构
4. backend SSE 样本
5. Flutter provider 产出的文本 chunk 样本
6. `<think>` 展示行为样本

实现动作：

- 不改生产逻辑
- 只补 characterization tests / replay fixtures

为什么必须先做：

- 当前 direct 与 proxy 行为本来就不完全一致
- 不先记录现状，后续无法判断是“修复”还是“回归”

## 3.2 Phase 1：保持契约，backend 接管更多执行语义

目标：

- backend 不只是中继 SSE，而是逐步成为请求执行与语义归一中心
- Flutter 仍然消费兼容的文本 chunk

建议切片：

### Slice 1A：统一 backend 请求规范化入口

backend 需要接手：

- 参数裁剪
- provider 特殊字段拼装
- message 结构规范化

Flutter 暂时仍可继续发送当前 `provider + messages + params` 结构，但 backend 应开始内部统一解释。

首阶段约束：

- 不改 Flutter 请求协议
- 先让 backend 对现有请求体承担更多规范化责任

### Slice 1B：统一 backend 流语义归一

backend 需要开始负责：

- 从上游 SSE 中提取正文
- 识别 reasoning / thinking
- 输出兼容当前 Flutter 的 `<think>` 文本流

注意：

- 首阶段仍建议输出文本 chunk，而不是 typed event
- 这样 `StreamManager` 无需改动

### Slice 1C：补齐 direct/proxy 行为差异

至少需要对齐：

- 空 system 消息过滤
- 附件行为
- 参数裁剪规则
- Gemini thinking 配置

这一步是为了避免“backend 开了能聊，但和直连链表现不一样”。

## 3.3 Phase 2：backend 接管路由与韧性策略

目标：

- 让 backend 成为 route selection 的唯一真源

backend 接手：

- `direct / proxy / auto` 的真实实现
- fallback policy
- circuit breaker
- retry / timeout
- cancel protocol

Flutter 变化：

- Flutter 不再基于 provider 直接做路由切换
- Flutter 只表达“使用哪个模型/会话”
- 是否 fallback、何时熔断，由 backend 决定

兼容策略：

- 前端保留一个总开关作为回滚入口
- 但正常运行不再由前端决定 direct/proxy/auto

## 3.4 Phase 3：backend 接管 provider registry 与 key custody

目标：

- backend 成为 provider 配置与密钥真源

backend 接手：

- provider 存储
- provider 认证配置
- API key
- provider model listing

Flutter 变化：

- 不再在每次 `chat completion` 时发送 `api_key` / `api_url`
- 请求体不再携带完整 `provider` 凭据

迁移注意：

- 这一步会改边界契约
- 必须放在前两阶段稳定后再做

## 4. 前后端边界重定义建议

## 4.1 Flutter 到 backend 的首阶段契约

首阶段建议继续保留当前大体契约：

```json
{
  "model": "...",
  "messages": [...],
  "stream": true,
  "provider": {...},
  "temperature": ...,
  "max_tokens": ...
}
```

原因：

- 能降低迁移面
- 先迁执行权，再迁配置权

## 4.2 Flutter 到 backend 的中后期契约

中后期建议演进为：

```json
{
  "session_id": "...",
  "provider_id": "...",
  "model": "...",
  "messages": [...],
  "stream": true,
  "client_capabilities": {
    "thinking_tags": true
  }
}
```

这样 backend 才能真正控制：

- 配置来源
- 路由
- 语义标准

## 4.3 backend 到 Flutter 的流式契约

首阶段建议保持：

- 文本 chunk
- `<think>` / `</think>` 标签

不要在这个阶段改成 typed event，原因是：

- `StreamManager` 当前依赖文本标签解析
- 一次同时改“backend 实现”和“UI 消费协议”风险过高

后续如果要演进，可在 backend 稳定后再考虑：

- typed event stream
- thinking / text / tool / error 分事件类型

但这不是本轮迁移的第一步。

## 5. 每个切片的责任分配

### 5.1 Slice 1A：请求规范化

Flutter：

- 保持当前发送行为

backend：

- 对入参做统一规范化
- 对不同 provider 做统一兼容层

风险：

- 参数差异导致 provider 行为变化

测试：

- request snapshot tests
- upstream mock integration tests

### 5.2 Slice 1B：流语义归一

Flutter：

- 继续消费字符串 chunk

backend：

- 负责把上游 SSE 变成当前兼容语义

风险：

- thinking 展示回归
- chunk 边界变化导致 UI 漏字/重字

测试：

- SSE replay tests
- UI regression tests

### 5.3 Slice 2A：路由与 fallback 后端化

Flutter：

- 只发业务请求

backend：

- 选择执行路径
- 维护 breaker 状态

风险：

- 回退条件与当前预期不一致

测试：

- fallback characterization tests
- state transition tests

### 5.4 Slice 3A：配置与密钥后端化

Flutter：

- 不再发送 key

backend：

- 管理 provider registry

风险：

- 迁移脚本、配置同步、跨端一致性

测试：

- config migration tests
- auth tests

## 6. 契约保持原则

在 Phase 1 前，不建议修改以下前端消费点：

- `StreamOutputController.startStreaming()`
- `StreamManager.append()`
- `_handleStreamFlush()`
- UI 对 `<think>` 的展示逻辑

只要这些点不改，UI 侧的回归面会明显更小。

## 7. 本轮设计结论

正确迁移路径不是“把前端 provider 全删掉再重写 backend”，而是：

1. 先保持 Flutter 可继续工作
2. 让 backend 接手更多运行时真相
3. 逐步把路由、配置、语义、韧性策略收口到 backend
4. 最后再考虑更彻底的接口演进
