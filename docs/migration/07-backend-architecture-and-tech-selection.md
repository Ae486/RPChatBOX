# 后端选型与架构设计

## 1. 文档目的

本文档用于明确基础 LLM 请求链迁移阶段的 backend 技术选型与整体架构设计，作为后续实现、评审和回滚的依据。

它回答 4 个问题：

1. backend 应该承担什么职责
2. backend 各层分别用什么技术更合适
3. 哪些地方应该直接使用 Python 生态中的成熟轮子
4. 当前阶段和后续 agent / RAG 阶段应如何分层演进

## 2. 已确认的设计前提

本项目当前已经明确以下前提：

1. 当前只关注基础 LLM 请求链，不包含 RP 实现
2. Flutter 现有实现不需要逐行复制
3. 如果 Python 有更成熟、更稳定、更高层的轮子，优先直接使用
4. 前端保留 direct mode，作为回滚通道
5. backend 第一阶段可先只做文本主链
6. 如果附件/多模态的 backend 化复杂度过高，可后置到下一阶段
7. 第一阶段优先保持 Flutter 现有流式 UI 链路兼容，不做大爆炸协议重写
8. `direct` 链只用于识别必要兼容边界，不是必须逐细节复刻的最终目标实现

## 3. 总体架构目标

backend 的目标不是“另一个转发脚本”，而是逐步成为：

- LLM 请求中枢
- provider 兼容层
- 流语义标准化层
- 后续 RAG / agent 的执行底座

Flutter 的目标应收敛为：

- UI
- 流式展示
- Markdown / 代码块 / LaTeX / Mermaid 渲染
- thinking / 正文分区展示
- 输入与本地交互状态

也就是：

```text
Flutter = 展示层
backend = 运行时中枢
```

## 4. 架构原则

## 4.1 优先用成熟轮子，不复制低质量实现

这是当前最核心的原则。

如果 Python 生态中已经有成熟方案，可以覆盖现有功能且可接入当前链路，则应优先直接使用，而不是机械复刻 Flutter 端的已有实现。

这里的“现有功能”指的是：

- 核心能力覆盖
- 接口/链路可接入
- 用户可感知体验不倒退

而不是要求 backend 与 Flutter `direct` 链在每个中间细节上完全一致。

适用范围：

- provider 兼容
- 文件解析
- SSE / LLM gateway
- agent runtime
- RAG ingestion / retrieval

不适用范围：

- 与具体 UI 呈现强绑定的前端展示逻辑

## 4.2 不让单一框架定义整个系统边界

不建议把 backend 全部交给某一个“大一统框架”定义。

正确做法是：

- 先定义系统分层
- 再给每一层选最合适的工具

否则会出现两个问题：

1. 框架绑架业务边界
2. 后续难以替换或局部演进

## 4.3 第一阶段先求稳定可接入，不求一步到位

第一阶段目标不是：

- 完整 agent
- 完整 RAG
- 完整配置中心
- 完整 typed event 协议

第一阶段目标是：

- backend 能稳定接管基础请求链
- 前端体验不被破坏
- 为后续能力留出正确的边界

## 5. 推荐分层架构

建议 backend 按 6 层组织：

### 5.1 API Layer

职责：

- HTTP API
- SSE 输出
- 请求校验
- 健康检查
- 调试/探测接口

推荐技术：

- `FastAPI`

原因：

- 当前已经在用
- 适合流式 API
- 与 Pydantic 模型天然配合
- 对后续 agent / RAG API 都足够友好

当前结论：

- 保留，不推倒

### 5.2 Gateway Layer

职责：

- 统一 provider 接入
- provider 参数兼容
- 模型访问入口
- 基础异常映射

推荐技术：

- `LiteLLM`

原因：

- 已经接入当前 backend
- 非常适合做多 provider gateway
- 能减少直接手写 provider 兼容逻辑
- 比在 Flutter 端自己兼容各种 provider 协议更合适

当前结论：

- 继续使用，并作为主要上游访问层强化

补充：

- 对不适合走 LiteLLM 的边缘场景，可以保留 `httpx` 直连兜底实现
- 但主路径应尽量统一到 LiteLLM 语义层

### 5.3 Application / Service Layer

职责：

- 业务边界
- 请求编排
- 路由选择
- 流语义归一
- fallback / retry / cancel
- 后续 RAG / agent 组合

推荐方式：

- 这一层优先使用**自定义 service 层**

建议保留清晰的服务边界，例如：

- `ChatService`
- `RoutingService`
- `StreamNormalizationService`
- `ProviderRegistryService`
- `ModelDiscoveryService`
- `AttachmentIngestionService`
- `AgentService`
- `RetrievalService`

原因：

- 这层是系统边界，不应直接绑死某个外部框架
- 后续即使替换 agent / RAG 框架，这层边界仍然稳定

### 5.4 Stream Semantics Layer

职责：

- 解析上游 SSE
- 抽取 thinking / reasoning
- 抽取正文
- 标准化错误、done、tool 等事件
- 第一阶段输出兼容当前 Flutter 的文本协议

第一阶段推荐方案：

- backend 内部先统一成结构化流事件：
  - `thinking`
  - `text`
  - `tool_call`
  - `error`
- backend 继续输出：
  - 正文增量文本
  - `<think>`
  - `</think>`

原因：

- 避免 backend 直接把上游原生结构打碎成字符串再让 Flutter 二次猜测
- 这样前端 `StreamManager` 与思考块 UI 基本不用重写
- 可以把“协议语义识别”迁到 backend，但保持前端体验不变

未来可选升级：

- 再逐步演进为 typed events

但这不应是第一阶段目标。

### 5.5 Agent Runtime Layer

职责：

- 工具调用
- 结构化输出
- 多步执行
- 状态化 agent 运行

当前推荐：

- 第一阶段先不引入到基础请求链
- 进入 agent 阶段时，优先考虑 `PydanticAI`

原因：

- 更贴近 `FastAPI + Pydantic` 风格
- 类型约束更自然
- 适合作为后续 backend agent runtime
- 比一上来把整个系统绑死在高层 LangChain agent 上更稳

对 `LangChain` 的定位：

- 可以作为组件库或集成层使用
- 但不建议让它直接定义整个 backend 的系统边界

对 `LangGraph` 的定位：

- 如果后续确实需要更复杂的层级编排、持久化工作流、多代理图执行，再引入
- 不是第一阶段必需

### 5.5.1 当前阶段是否要为后续 agent 留基建

要留，但只留**后端内部基建和扩展接口**，不把它提前做成主聊天的默认产品能力。

当前阶段建议保留的东西：

1. 稳定的 backend 执行入口
   - 继续以 `chat_completion()` / `chat_completion_stream()` 这类 service 边界作为统一执行入口
   - 后续 agent 无论是同步调用、后台任务还是子 agent 调用，都应复用这层，而不是绕过它直接打 provider
2. 可扩展的执行策略承载位
   - 允许 backend request / service context 继续承载少量“执行提示”，例如：
     - route mode
     - timeout / first-chunk timeout
     - fallback enable
     - retry budget
   - 这些字段当前可以只服务基础链，不必扩展成完整的 agent policy schema
3. 标准化错误分类
   - 至少把 timeout、auth、rate limit、upstream unavailable、manual abort 这类错误在 backend 内部收口
   - 后续 agent 才能基于这些错误类别决定“重试 / 换模型 / 降级 / 转后台异步”
4. 可观测性
   - 保留 `request_id`
   - 保留 route / first-chunk / cancel / completed / failed 等日志标记
   - 后续 agent 调度要判断是否超时、是否需要回退，离不开这些观测点
5. 可传播的取消语义
   - 当前主链已经在做最小 cancel 收敛
   - 后续 agent 如果有多步执行或后台任务，也必须建立在“可取消”的底座之上

当前阶段不应该提前做的东西：

1. 主聊天默认自动切换模型
2. 主聊天默认自动降级到低价模型
3. 把复杂 retry/fallback 策略暴露成面向用户的产品能力
4. 为了 future-proof 提前引入完整 agent policy engine
5. 在 Flutter UI 里先做一套复杂策略配置页

原因：

1. 这些能力本质上属于 agent orchestration，不属于基础请求链迁移的主目标
2. 如果现在把“主链稳定化”和“多模型策略产品化”混在一起，测试变量会明显增多
3. 后续 RP agent 的策略维度会更多：
   - 子任务类型
   - 成本/速度权衡
   - 是否允许异步后台完成
   - 是否允许降级回答质量
4. 这些都应在 agent 设计阶段统一定义，而不是在主聊天迁移阶段零散生长

### 5.6 RAG Layer

职责：

- 文档/设定导入
- 切片
- 索引
- 检索
- prompt/context 注入

当前推荐：

- 后续 RAG 阶段优先考虑 `LlamaIndex`

原因：

- 在索引、检索、RAG workflow 上更专
- 适合作为后续写作/RP/知识检索的专门子系统

建议定位：

- `LlamaIndex` 是 RAG 子系统，不是整个 backend 框架

## 6. 附件 / 多模态的选型原则

这部分不要复制 Flutter 的粗糙实现。

原则是：

- Python 有成熟轮子，就直接用
- 若接入成本过高，第一阶段先不纳入

推荐处理思路：

### 6.1 文档类

目标：

- 把用户上传文件转换成可送给模型的文本或结构化片段

候选轮子：

- `markitdown`
- `unstructured`
- `pymupdf`
- `python-docx`
- `openpyxl`

使用策略：

- 不要求首阶段全覆盖
- 先覆盖最常见文本文件和 PDF

### 6.2 图片类

目标：

- 作为多模态输入提供给模型

处理方式：

- 保留 base64 / data URL 形式或统一上传后引用

候选轮子：

- `Pillow`

### 6.3 首阶段建议

如果附件链路会明显拖慢基础请求链迁移，则：

- 第一阶段只做文本聊天主链
- 附件能力在后续切片补齐

## 7. 数据与存储策略

当前建议是**过渡态优先**。

也就是：

- 当前不急着把所有 provider/config/session 都迁成 backend 真源
- 只有当后续 backend 真正需要配置中心、RAG 存储、agent 状态持久化时，再引入数据库迁移

### 7.1 第一阶段

- 允许前端继续持有部分 provider 配置
- backend 先把请求执行权、流语义权接过去

### 7.2 后续阶段

当以下能力开始落地时，再考虑持久化升级：

- provider registry
- agent state
- RAG index
- cross-device shared data

届时可考虑：

- `PostgreSQL`
- 向量检索用 `pgvector` 或 `Qdrant`

但不建议现在超前引入。

## 8. 第一阶段推荐架构形态

第一阶段推荐形态如下：

```text
Flutter
  - 聊天 UI
  - thinking / 正文分离渲染
  - Markdown / code / LaTeX / Mermaid 渲染
  - backend 开关
  - direct mode 回滚

backend
  - FastAPI API
  - LiteLLM gateway
  - 请求规范化
  - 上游执行
  - 流语义识别
  - `<think>` 兼容输出
```

对应执行链：

```text
Flutter -> backend /v1/chat/completions -> LiteLLM/httpx -> upstream LLM
        <- backend 归一后的增量文本 / <think> 标签流 <- 
```

## 9. 第一阶段不建议做的事

以下事情不建议进入第一阶段：

1. 重写 Flutter UI 流式渲染体系
2. 立即把前后端协议升级为 typed events
3. 立即做完整 provider/config 数据库迁移
4. 立即引入复杂多代理编排
5. 为了“架构优雅”强行复制 Flutter 的全部附件逻辑

## 10. direct mode 的设计地位

当前已经确认：

- direct mode 保留
- 作为回滚通道存在
- 在 backend 未完全正确接管前，不移除

建议继续以当前 Python backend 全局开关作为切换核心。

这意味着：

- backend 路线可以渐进落地
- 任一切片出问题时可快速切回

## 11. 选型结论

基于当前项目现状，推荐的 backend 技术路线是：

### 当前阶段

- API：`FastAPI`
- Gateway：`LiteLLM`
- 执行编排：自定义 service 层
- 流式协议：第一阶段保持 `<think>` 兼容文本流
- 文件处理：优先用 Python 成熟轮子；复杂则后置

### 后续 agent 阶段

- agent runtime：优先 `PydanticAI`
- `LangChain` 作为组件库/集成工具可选使用
- `LangGraph` 留给更复杂的多阶段编排场景
- 在此阶段再正式设计：
  - 多模型切换
  - 任务级重试/降级
  - 后台异步执行
  - agent policy / scheduler

### 后续 RAG 阶段

- 优先 `LlamaIndex`
- 向量存储后续按实际规模选择 `pgvector` 或 `Qdrant`

## 12. 最终判断

对当前项目，最合理的路线不是：

- 在 Flutter 中继续堆更多运行时逻辑
- 或者把整个 backend 一把梭重写成某个大框架项目

而是：

**保留 Flutter 的展示优势，利用 Python 的成熟生态做后端上位替代，把 provider 兼容、流语义、后续 agent / RAG 底座逐步收口到 backend。**
