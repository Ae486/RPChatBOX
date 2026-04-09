# 测试、回滚与可观测性

## 1. 当前测试现状

## 1.1 backend 已有测试

已有：

- `backend/tests/test_health.py`
  - 覆盖 `/api/health`
  - 覆盖 `GET /models`
- `backend/tests/test_litellm_service.py`
  - 覆盖 LiteLLM model prefix
  - 覆盖 `_get_api_base()` 剥离 endpoint suffix
  - 覆盖 kwargs 构造
  - 覆盖 stream/non-stream 与异常映射

结论：

- backend 有最小单测基础
- 但缺少 API contract 测试、SSE replay 测试、上游 mock 集成测试

## 1.2 Flutter 当前测试缺口

本轮未发现针对以下模块的现成回归测试：

- `ProxyOpenAIProvider`
- `BackendRoutingProvider`
- `FallbackPolicy`
- `CircuitBreaker`
- `StreamManager`
- `ProviderFactory.createProviderWithRouting()` 的真实路由行为

这意味着：

- 当前基础请求链迁移风险主要靠人工验证兜底
- 必须先补 characterization tests，不能只靠手测

## 2. 推荐测试分层

## 2.1 Characterization Tests

目的：

- 固定当前行为，而不是证明当前实现优雅

应该覆盖：

1. `ProviderFactory.createProviderWithRouting()`
   - backend 开关关 -> `HybridLangChainProvider`
   - backend 开关开 -> `ProxyOpenAIProvider`
   - `backendMode` 当前被忽略

2. 直连与代理请求体差异
   - system 消息过滤
   - 参数裁剪
   - `include_reasoning`
   - Gemini `extra_body`
   - 附件行为

3. `StreamManager` 对 `<think>` 的解析
   - 正常开闭
   - thinking 未闭合时结束流
   - thinking 与正文混排

意义：

- 后续一旦行为变化，可以判断是“有意修正”还是“无意回归”

## 2.2 API Contract Tests

backend 需要补的 contract tests：

1. `GET /api/health`
2. `GET /models`
3. `POST /models`
4. `POST /v1/chat/completions` non-stream
5. `POST /v1/chat/completions` stream
6. 错误结构：
   - 400
   - 401/403
   - 429
   - 5xx

重点验证：

- 返回结构稳定
- SSE 格式稳定
- 错误 envelope 稳定

## 2.3 SSE Replay Tests

这是本次迁移中最重要的一类测试。

需要准备 fixture：

1. OpenAI 风格 `choices[].delta.content`
2. reasoning 风格 `choices[].delta.reasoning_content`
3. Gemini/OpenRouter 风格 `candidates[].content.parts[]`
4. mid-stream error
5. `[DONE]`

测试目标：

- backend 标准化后的输出与当前 Flutter provider 输出一致
- `<think>` 边界一致
- 正文不丢字、不重字

## 2.4 Integration Tests

建议使用 mock upstream server 做集成测试，覆盖：

1. 成功非流式请求
2. 成功流式请求
3. 上游超时
4. 上游 401/403
5. 上游 429
6. 上游 502/503/504
7. 半路断流
8. malformed chunk

重点观察：

- backend 是否按预期映射错误
- 是否触发 fallback
- SSE 是否正确结束

## 2.5 UI Regression Tests

首阶段不要只测 backend，必须保底测 UI 表现。

至少覆盖：

1. thinking 是否正常显示
2. 正文是否按流式逐步出现
3. 完成态是否正常落地
4. 错误态是否正常落地
5. 停止输出后 UI 是否一致

这部分可以先以手工回归为主，再逐步补自动化。

## 3. 推荐的测试矩阵

## 3.1 路由矩阵

- backend 开关关闭
- backend 开关开启
- `backendMode = direct / proxy / auto`

说明：

- 虽然当前主链忽略 `backendMode`
- 但测试应先把这个现实固定下来

## 3.2 Provider 矩阵

- OpenAI
- DeepSeek
- Claude
- Gemini

原因：

- 当前 reasoning 与 path suffix 兼容逻辑依 provider 不同

## 3.3 流式语义矩阵

- 无 thinking
- 有 thinking
- thinking 后接正文
- Gemini first-part thinking
- error mid-stream

## 4. 回滚策略

## 4.1 总原则

每个迁移切片必须满足：

- 单独开关
- 单独回滚
- 回滚后主链可继续工作

## 4.2 建议的回滚层级

### 回滚层级 A：关闭新 backend 语义实现

保留：

- 旧 backend relay
- 旧 Flutter provider 解释逻辑

适用：

- backend 流语义归一出问题

### 回滚层级 B：恢复前端路由决策

保留：

- 旧 `ProviderFactory` 选择逻辑

适用：

- route selection / fallback 后端化出问题

### 回滚层级 C：恢复前端 provider 配置来源

保留：

- `ProviderConfig` 本地真源

适用：

- provider registry / key custody 迁移出问题

## 4.3 回滚所需条件

每个阶段至少要保留：

1. 旧路径仍可运行
2. 切换开关明确
3. 测试可以覆盖新旧两条路径

## 5. 可观测性要求

当前 backend 还缺少系统性的可观测性。迁移过程中建议逐步补齐：

### 5.1 请求级字段

- request id
- provider type
- model
- route mode
- upstream service path
- stream / non-stream

### 5.2 时延字段

- request start time
- upstream connect latency
- first token latency
- total duration
- chunk count

### 5.3 错误字段

- HTTP status
- mapped error code
- fallback triggered or not
- breaker state
- cancelled or not

### 5.4 日志与指标

至少需要：

- 结构化日志
- 关键错误计数
- fallback 计数
- breaker open 计数
- provider 维度失败率

## 6. 本轮测试建议优先级

如果只能先补一批测试，优先级建议如下：

1. `ProviderFactory` 路由现实测试
2. `StreamManager` `<think>` 解析测试
3. backend `/v1/chat/completions` stream contract tests
4. SSE replay tests
5. fallback / circuit breaker tests
6. 附件/多模态兼容测试

## 7. 结论

本次迁移最容易出错的不是“请求发不出去”，而是：

- thinking 语义变了
- chunk 边界变了
- fallback 行为变了
- route 选择逻辑和用户理解不一致

因此测试重点必须放在：

- 行为基线
- SSE 语义
- 路由与回退
- UI 表现一致性
