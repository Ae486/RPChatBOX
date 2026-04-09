# backend 轮子 / 框架上位替代核查

## 1. 文档目标

本文档只回答一个问题：

**当前基础 LLM 请求链迁移中，backend 哪些部分已经有成熟 Python 轮子/框架可用于上位替代 Flutter `direct` 链里的粗糙实现？**

约束：

1. 只看基础 LLM 请求链，不看 RP/agent/RAG 业务实现
2. `direct` 只作为兼容参考，不作为逐细节复刻目标
3. 替代方案必须能兼容当前 Flutter 渲染链路：
   - `text/event-stream`
   - OpenAI 风格 JSON chunk
   - `choices[0].delta.content`
   - `<think>...</think>` 兼容语义

## 2. 当前 backend 现状

当前 backend 已有分层：

1. API 层
   - `backend/main.py`
   - `backend/api/chat.py`
2. Gateway / 上游接入
   - `backend/services/litellm_service.py`
   - `backend/services/llm_proxy.py`
3. 语义胶水层
   - `backend/services/request_normalization.py`
   - `backend/services/stream_normalization.py`
4. 协议模型
   - `backend/models/chat.py`

当前已经完成的核心事实：

1. backend 能稳定处理 `/v1/chat/completions`
2. backend 已把部分 Flutter `direct` 侧的请求规范化迁到 Python
3. backend 已把 provider-specific 流语义归一成兼容的 `delta.content` chunk
4. Flutter 当前 proxy 链已经可以优先消费 backend 标准化后的文本流

因此，这次核查不是“backend 要不要重写”，而是：

**哪些点该继续用现成轮子吸收 direct 的职责，哪些点继续保持自定义胶水层最合理。**

## 3. 核查标准

一个轮子/框架只有满足下面条件，才算“适合上位替代”：

1. 能覆盖当前核心能力
2. 能接入当前 backend
3. 不破坏 Flutter 渲染契约
4. 不要求前端大改
5. 相比现有自定义实现，确实减少维护成本

## 4. 结论总览

### 4.1 现在就应该继续强化使用的

1. `LiteLLM`
   - 用于 provider 兼容、统一调用、后续 routing/fallback/retry
   - 这是当前最明确的上位替代

2. `MarkItDown`
   - 用于后续附件/文档解析
   - 适合替代 Flutter 侧当前零散文件解析逻辑

### 4.2 现在可保留，但不必急着替换的

1. `FastAPI + StreamingResponse`
   - 当前已足够支撑现有 SSE 契约
   - 不需要为了“更框架化”立即重写成别的流框架

2. `RequestNormalizationService`
3. `StreamNormalizationService`
   - 这两层仍然应保留为自定义胶水层
   - 因为它们承担的是“当前项目的兼容语义”，不是通用轮子能直接替代的内容

### 4.3 可以研究，但不建议当前阶段引入的

1. `LiteLLM Proxy Server`
2. `sse-starlette / EventSourceResponse`
3. `Unstructured`

它们不是“不行”，而是：

- 当前阶段未必比现有方案更合适
- 一旦引入，改动面可能比收益更大

## 5. 逐项核查

## 5.1 Provider 兼容层：`LiteLLM`

### 当前问题

Flutter `direct` 链目前自己承担了大量 provider 兼容逻辑：

1. OpenAI / Claude / DeepSeek / Gemini 差异
2. 请求参数裁剪
3. 上游 URL 差异
4. reasoning 字段差异

这部分正是 Python 生态里最不该继续手写的地方。

### 官方能力

LiteLLM 官方文档明确提供：

1. 统一 OpenAI 格式调用多 provider
2. 一致化输出
3. streaming
4. retries / budgets / routing
5. Router / Proxy Server

这和当前项目需要的 backend 能力高度对齐。

### 对当前项目的判断

结论：**应继续把 provider 兼容职责收口到 LiteLLM，而不是继续让 Flutter `direct` 链承担。**

更明确地说：

1. `litellm_service.py` 是正确方向
2. `llm_proxy.py` 应逐步退成兜底路径，而不是主路径
3. Phase 2 的 routing / fallback / retry，优先评估直接用 LiteLLM Router，而不是自己重写

### 与 Flutter 渲染链路的兼容性

兼容。

原因：

1. LiteLLM 本身就是 OpenAI 兼容调用层
2. 当前 backend 已经在 LiteLLM 之上再做一层 `stream_normalization`
3. 所以 Flutter 只要继续消费当前 `delta.content` + `<think>` 契约，不需要知道底层是不是 LiteLLM

### 结论

`LiteLLM`：**推荐，且应继续强化使用。**

## 5.2 直接用 LiteLLM Proxy Server 替代当前 backend？

### 官方能力

LiteLLM 官方提供 Proxy / Gateway：

1. YAML 配置模型
2. OpenAI 兼容 `/chat/completions`
3. routing / retries / budgets / auth

### 为什么当前阶段不建议直接替换

当前项目还处于过渡态，关键特征是：

1. Flutter 仍会把 `provider` 配置随请求体发给 backend
2. 当前需要兼容已有前端链路和回滚开关
3. 当前 backend 还承担了特定的请求规范化和流语义兼容

而 LiteLLM Proxy 更适合：

1. provider / key 已经后端真源化
2. 模型列表和路由已静态/半静态配置
3. 系统准备好围绕网关做权限和治理

### 对当前项目的判断

结论：**LiteLLM Proxy Server 是后续可选升级，不是当前阶段最优替换。**

当前更合理的做法是：

1. 保留现有 FastAPI 壳层
2. 在壳层内部优先走 LiteLLM SDK / Router
3. 等 provider registry 和 key custody 后端化后，再评估是否进一步转向 LiteLLM Proxy 架构

### 结论

`LiteLLM Proxy Server`：**后续可选，不建议当前直接替换现有 backend 壳层。**

## 5.3 SSE / 流输出层：`FastAPI StreamingResponse`

### 当前问题

当前已经有：

1. `StreamingResponse`
2. 手写 `data: {json}\n\n`
3. `[DONE]`

这套方案已经兼容 Flutter 现有消费逻辑。

### 官方能力

FastAPI 官方文档明确支持：

1. `StreamingResponse`
2. SSE
3. `EventSourceResponse`

也就是说，FastAPI 本身已经足够承担当前流输出职责。

### 对当前项目的判断

结论：**当前不需要为了 SSE 再引入新的主框架。**

现在最重要的是：

1. 保持现有 OpenAI chunk 契约稳定
2. 保持 `<think>` 兼容语义稳定
3. 让 Flutter 不需要重写流式渲染层

对这一目标来说，当前 `StreamingResponse` 已经够用。

### 结论

`FastAPI + StreamingResponse`：**当前已足够，是合理实现，不必为了“更像 SSE 框架”而替换。**

## 5.4 是否要改成 `EventSourceResponse` / `sse-starlette`

### 官方能力

FastAPI / `sse-starlette` 都提供：

1. SSE 连接生命周期管理
2. disconnect 检测
3. ping
4. send timeout

这些能力在严格 SSE 场景下有价值。

### 对当前项目的判断

当前项目的前端消费方式不是浏览器原生 `EventSource`，而是把 OpenAI 风格 SSE 当作 LLM chunk 流来解析。

所以当前阶段的关键不是“更标准的 SSE 封装”，而是：

1. chunk 语义正确
2. `data:` 行正确
3. `[DONE]` 正确

因此：

- 如果只是保持当前链路，`StreamingResponse` 足够
- 如果未来进入 typed events、断线感知、长连接治理，再评估 `EventSourceResponse`

另外，当前代码已经把 `sse-starlette` 放进依赖，但实际没有使用。  
这本身说明它目前不是迁移阻塞点。

### 结论

`sse-starlette / EventSourceResponse`：**可选增强，不是当前基础请求链的必要替代。**

## 5.5 附件 / 文档解析：`MarkItDown`

### 当前问题

Flutter 当前通过：

1. 自己判断 mime / extension
2. 自己做 PDF / DOCX / HTML / CSV 等提取
3. 自己把结果拼进用户消息

这条链本质上就是典型的“前端做了不该做的重活”。

### 官方能力

MarkItDown 官方文档明确提供：

1. 把 PDF / DOCX / HTML / CSV / 图片 / 音频等转换成 Markdown
2. 简单 Python API
3. 可选插件与可选 OCR / 图片说明能力
4. 面向 LLM 使用场景

这和当前项目“附件先转文本/Markdown，再交给模型”的需求高度一致。

### 对当前项目的判断

结论：**如果进入 Phase 1.5 附件收口，优先选 MarkItDown。**

原因：

1. 接入简单
2. 目标就是 LLM-ready text / markdown
3. 比 Flutter 端手工拼各种文件解析逻辑更合适
4. 不要求逐格式自己维护解析器

### 与 Flutter 链路的兼容性

兼容。

可行接法：

1. backend 接收文件
2. backend 用 MarkItDown 转 markdown/text
3. backend 把结果注入消息内容
4. Flutter 仍只接收标准消息流，不需要理解附件解析细节

### 结论

`MarkItDown`：**强推荐，作为附件/文档解析的上位替代。**

## 5.6 `Unstructured` 是否更好

### 官方能力

Unstructured 官方能力更强：

1. partition 多种文件
2. 返回 structured elements
3. 支持 metadata / layout / OCR / table extraction
4. 更适合 ingestion / RAG pipeline

### 为什么当前阶段不优先

对“基础聊天附件解析”来说，它有几个现实问题：

1. 能力更重
2. 集成面更大
3. 更偏 ingestion / RAG，而不是轻量 chat attachment

这不是说它不好，而是说：

**它更像未来 RAG/知识处理层的轮子，不是当前文本主链迁移最优先的轮子。**

### 结论

`Unstructured`：**适合未来 RAG/ingestion，不是当前 Phase 1.5 的首选。**

## 5.7 请求规范化与流语义归一，有没有现成轮子完全替代？

短答案：**没有一个轮子能直接替代当前项目的这两层。**

原因：

1. 这两层处理的是“当前项目的兼容语义”
2. 需要对接 Flutter 现有渲染契约
3. 需要在 provider 差异与前端历史行为之间做桥接

因此最合理的实现仍然是：

1. provider/gateway 交给 `LiteLLM`
2. 项目兼容语义保留在自定义胶水层：
   - `RequestNormalizationService`
   - `StreamNormalizationService`

这不是“自己造轮子”，而是必要的边界胶水。

## 6. 最终建议

## 6.1 当前阶段

继续采用：

1. `FastAPI`
2. `LiteLLM`
3. 自定义 normalization/glue 层

不建议当前直接替换成：

1. 纯 LiteLLM Proxy Server
2. 新的 SSE 主框架

## 6.2 Phase 1.5 附件能力

优先引入：

1. `MarkItDown`

不建议优先引入：

1. `Unstructured`

除非目标已经变成：

1. 结构化元素抽取
2. 表格/版面理解
3. RAG ingestion pipeline

## 6.3 Phase 2 路由与韧性

优先核查并可能引入：

1. `LiteLLM Router`

因为它已经提供：

1. routing
2. fallbacks
3. retries
4. cooldown / allowed fails

这比完全自写 fallback / circuit breaker 更符合“有轮子用轮子”的原则。

## 7. 一句话结论

**当前最合理的上位替代路线不是“重写 backend”，而是：继续把 provider 兼容和后续韧性能力收口到 LiteLLM，把附件解析交给 MarkItDown，保留当前 FastAPI + 自定义兼容胶水层来维持 Flutter 渲染契约。**

## 8. 参考资料

1. LiteLLM 官方文档: https://docs.litellm.ai/
2. LiteLLM Proxy / Gateway 文档: https://docs.litellm.ai/docs/proxy/quick_start
3. LiteLLM Reliability / Router 文档: https://docs.litellm.ai/docs/proxy/reliability
4. FastAPI StreamingResponse 文档: https://fastapi.tiangolo.com/advanced/custom-response/
5. FastAPI SSE 文档: https://fastapi.tiangolo.com/tutorial/server-sent-events/
6. sse-starlette README: https://github.com/sysid/sse-starlette
7. MarkItDown 官方仓库: https://github.com/microsoft/markitdown
8. Unstructured 官方仓库: https://github.com/unstructured-io/unstructured
