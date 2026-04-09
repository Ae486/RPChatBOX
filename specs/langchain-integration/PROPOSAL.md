# LangChain.dart 集成提案

> OpenSpec 提案文档
> 状态: DRAFT
> 创建: 2026-02-04

---

## 提案概述

将 LangChain.dart 框架从"全量使用"或"全量弃用"的二元选择，转变为**混合架构**：

- **LangChain 负责**：消息格式化、参数标准化、RAG 组件
- **自实现负责**：SSE 流式解析、Thinking 内容提取、请求取消

---

## 问题陈述

### 当前状态

1. LangChain.dart 已安装但禁用 (`useLangChain = false`)
2. 自实现 `OpenAIProvider` 承担所有 LLM 调用
3. 130 行 SSE 解析代码需要持续维护
4. 缺乏 RAG 能力

### 核心矛盾

| LangChain 优势 | LangChain 不足 |
|---------------|---------------|
| 标准化消息格式 | 无法提取 thinking 内容 |
| RAG 组件完善 | 无法取消进行中请求 |
| 社区维护 | 无 SSE 扩展点 |
| 减少自研负担 | 抽象层丢失关键信息 |

---

## 提案方案

### 架构决策

```
                    ┌─────────────────────┐
                    │   HybridProvider    │
                    └──────────┬──────────┘
                               │
           ┌───────────────────┼───────────────────┐
           ▼                   ▼                   ▼
   ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
   │   LangChain   │   │  自实现 SSE   │   │  自实现 HTTP  │
   │ MessageMapper │   │    Parser     │   │   (Dio)       │
   └───────────────┘   └───────────────┘   └───────────────┘
```

### 模块划分

| 模块 | 来源 | 理由 |
|------|------|------|
| 消息格式转换 | LangChain | 多 provider 格式复杂，标准化有价值 |
| 参数验证 | LangChain | 减少重复代码 |
| HTTP 请求 | Dio (自实现) | CancelToken 支持 |
| SSE 解析 | 自实现 | LangChain 无扩展点 |
| Thinking 提取 | 自实现 | LangChain 不支持 |
| RAG | LangChain | 完善且标准 |
| Memory | 自实现 | Hive 集成良好 |

---

## 实施计划

### Phase 1: 模块提取

**目标**：将 OpenAIProvider 中的可复用逻辑提取为独立模块

**产出**：
- `lib/adapters/sse/sse_parser.dart`
- `lib/adapters/sse/thinking_extractor.dart`
- 单元测试

### Phase 2: 混合 Provider

**目标**：创建 HybridLangChainProvider

**产出**：
- `lib/adapters/hybrid_langchain_provider.dart`
- 集成测试

### Phase 3: 路由切换

**目标**：通过 ProviderFactory 切换到混合实现

**产出**：
- 修改 `ProviderFactory.createProvider()`
- A/B 测试配置

---

## 验收标准

### 功能验收

| 场景 | 预期结果 |
|------|---------|
| 普通聊天 (OpenAI) | 正常流式输出 |
| DeepSeek R1 推理 | thinking bubble 正常显示 |
| Claude extended thinking | thinking bubble 正常显示 |
| Gemini 2.0 thinking | thinking bubble 正常显示 |
| 请求取消 | 立即中断，无残留 chunk |
| 网络错误 | 精细错误提示 |

### 非功能验收

| 指标 | 要求 |
|------|------|
| 首 chunk 延迟 | ≤ 原实现 |
| 内存占用 | ≤ 原实现 |
| 代码行数 | ≤ 原实现 + 100 行 |

---

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| LangChain 版本兼容性 | 锁定版本，定期评估 |
| 混合架构复杂度 | 清晰模块边界 + 文档 |
| SSE 格式变化 | 完善测试 + 监控 |

---

## 决策请求

请确认以下决策：

1. **是否采用混合架构？** (推荐: 是)
2. **是否保留现有 OpenAIProvider 作为 fallback？** (推荐: 是)
3. **是否立即引入 LangChain RAG 组件？** (推荐: 延后)

---

## 参考文档

- [CONSTRAINT_SET.md](./CONSTRAINT_SET.md) - 完整约束集
- [langchain_dart wiki](https://deepwiki.com/davidmigloz/langchain_dart)
- [OpenAI Streaming API](https://platform.openai.com/docs/api-reference/streaming)
