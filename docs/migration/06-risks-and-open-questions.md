# 风险与待确认问题

## 1. 高风险点

## 1.1 对当前“直连链”的误判风险

风险描述：

- 很容易假设当前 direct path 是 `OpenAIProvider`
- 但当前默认直连实际是 `HybridLangChainProvider`

证据：

- `lib/adapters/ai_provider.dart:235`
- `lib/adapters/ai_provider.dart:241-245`

影响：

- 如果迁移分析忽略这一点，会错误比较 direct / proxy 行为
- 也会误判取消、附件、SSE 解析等职责所在

结论：

- 这是本轮已确认事实，不是待确认项

## 1.2 路由语义与 UI 配置语义漂移

风险描述：

- `ProviderConfig.backendMode` 让人以为支持 `direct / proxy / auto`
- 但当前主链只受全局 `pythonBackendEnabled` 控制

证据：

- `lib/adapters/ai_provider.dart:273-282`

影响：

- 用户认知与真实运行行为可能不一致
- 后续如果直接实现 backend 路由，容易出现“看似兼容，实际变更”的情况

## 1.3 fallback / circuit breaker 已实现但未接入

风险描述：

- 代码中存在 `BackendRoutingProvider`、`FallbackPolicy`、`CircuitBreaker`
- 但当前 factory 未实例化该路径

影响：

- 文档与代码容易误判成“已有 auto mode”
- 迁移时若直接假设它已在线，会做出错误决策

## 1.4 direct 与 proxy 请求体不一致

风险描述：

- `HybridLangChainProvider` 与 `ProxyOpenAIProvider` 的请求体构造不一致

已确认差异：

1. `HybridLangChainProvider` 会过滤空 system 消息
2. `HybridLangChainProvider` 会处理附件/多模态
3. `ProxyOpenAIProvider` 当前忽略 `files`
4. `ProxyOpenAIProvider` 参数发送方式更直接，未按 provider 默认值裁剪

影响：

- 一旦迁移不先冻结样本，就很难判断差异是 bug、缺陷，还是现有行为

## 1.5 流语义仍在前端

风险描述：

- backend 当前只中继 SSE
- thinking / reasoning 解释主要仍在 Flutter provider

影响：

- 任何 backend 流语义调整都可能直接影响 `StreamManager`
- 如果不先做 replay tests，最容易出现 thinking 回归

## 1.6 取消链不完整

风险描述：

- `_stopStreaming()` 只在 `runtimeType` 含 `OpenAI` 时尝试调用 `cancelRequest()`
- `HybridLangChainProvider` 不满足此条件
- `ProxyOpenAIProvider` 没有 `cancelRequest()`
- backend 没有取消 API

证据：

- `lib/widgets/conversation_view_v2/streaming.dart:903`
- `lib/adapters/hybrid_langchain_provider.dart:426`
- `lib/adapters/openai_provider.dart:368`

影响：

- UI 停止不等于网络与上游真的停止
- 未来长流、长上下文、agent 都会受影响

## 1.7 `/models` 接口语义容易误用

风险描述：

- `GET /models` 当前只是健康探测
- `POST /models` 才是上游 provider 模型列表

影响：

- 如果迁移或调用方误以为 `GET /models` 是真实模型列表，会得到错误结论

证据：

- `backend/api/chat.py:116`
- `backend/api/chat.py:126`

## 1.8 backend 测试覆盖不足

风险描述：

- 当前 backend 有最小测试
- 但缺少 stream contract、replay、integration coverage

影响：

- 一旦迁移请求规范化或 SSE 语义，很难靠现有测试发现回归

## 2. 易错点

## 2.1 把 UI 表现问题当成 backend 问题

例如：

- thinking 不显示
- 文本跳字/重字

这些问题有时来自：

- chunk 边界变化
- `_handleStreamFlush()`
- `StreamManager._parseThinkingContent()`

而不一定是 backend 本身返回错。

## 2.2 把“backend 可发请求”误认为“已完成解耦”

当前 backend 已经可用，但这不等于：

- 路由已经后端化
- key 已后端化
- fallback 已后端化
- 流语义已后端化

## 2.3 同时改契约和实现

这是最不建议的做法。

如果同一轮同时改：

- Flutter 到 backend 请求结构
- backend 到 Flutter 流结构
- backend 内部执行逻辑

排错成本会迅速失控。

## 2.4 忽略附件差异

即使首阶段只关注文本聊天，也不能忘记：

- 当前 proxy 链与 direct 链在附件行为上不等价

这至少要在文档和测试里显式记录。

## 3. 待确认问题

以下问题本轮证据不足，暂不主观补全。

## 3.1 Phase 1 是否要求附件/多模态完全对齐

当前状态：

- 已确认 direct/proxy 行为不一致

待确认点：

- 第一阶段是否只要求文本链跑通
- 还是必须把附件也纳入“基础请求链完整性”

建议：

- 由需求侧明确

## 3.2 backend 最终是否要成为 provider registry 真源

当前状态：

- 当前设计方向明显指向是

待确认点：

- Phase 3 是否要引入完整 provider 管理
- 还是先做“前端继续存配置，backend 仅执行”的过渡态

## 3.3 frontend direct mode 是否长期保留

当前状态：

- 当前仍有直连能力

待确认点：

- 它未来是永久回滚通道
- 还是迁移完成后仅保留开发调试用途

这会影响：

- factory 设计
- 测试矩阵
- 配置模型

## 3.4 backend 到 Flutter 的事件契约是否未来升级为 typed events

当前状态：

- 当前 UI 边界是字符串流 + `<think>` 标签

待确认点：

- 未来是否计划升级为 structured events
- 若升级，何时升级

建议：

- 不是当前迁移第一阶段的目标

## 3.5 `/models` 是否保留双语义

当前状态：

- 目前 `GET /models` 做健康探测，`POST /models` 做 provider list

待确认点：

- 后续是否要保持兼容
- 还是拆成更清晰的 endpoint

## 4. 建议先回答的关键问题

如果后续要进入实施阶段，建议先明确以下 5 个问题：

1. Phase 1 是否只要求文本链，还是要附件对齐
2. frontend direct mode 是永久保留还是过渡能力
3. provider/key 真源何时切换到 backend
4. 首阶段是否坚持保留 `<think>` 字符串契约
5. cancel protocol 是否必须进入 Phase 2

## 5. 结论

当前迁移的主要风险不在“写不出 backend”，而在：

- 误判现状
- 混淆主链和遗留链
- 未冻结行为样本就开始迁移
- 在 thinking / 流边界处发生无感破坏

因此，后续实施前必须先把这些风险显式纳入测试与阶段设计。
