# 架构决策记录（ADR）

本目录记录 ChatBoxApp 的关键架构决策，采用轻量 Nygard 式 **ADR-lite** 格式。

## 这是什么

ADR（Architecture Decision Record）用一份简短文档记录"为什么这样决定"。它捕捉决策的**背景、所选方案与后果**，让后来者无需考古即可理解既有架构，也为新决策提供可追溯的先例。

本目录的 ADR-0001…0010 为**回填**——记录项目中**已经生效**的决策，每条标注来源依据。

## 约定

- 文件名：`NNNN-kebab-标题.md`，编号零填充四位（`0001`、`0002`…）。
- 每条包含：**状态 / 日期 / 来源 / 背景 / 决策 / 影响**（模板见 [`0000-template.md`](0000-template.md)）。
- 状态流转：`Proposed` → `Accepted` →（必要时）`Superseded by ADR-XXXX` / `Deprecated`。
- **不修改已生效的 ADR**：决策变更时新建 ADR，并把旧条标记为 `Superseded`。
- 新增决策从下一个空号继续编号。

> 说明：与全仓 markdown 一致，本目录被 `.gitignore`（`*.md`）忽略，当前为本地文档；待项目 `*.md` 策略放开后再随仓发布。详见 [ADR-0010](0010-markdown-docs-local-only.md)。

## 目录

| 编号 | 标题 | 状态 |
|---|---|---|
| [ADR-0001](0001-backend-routing-modes.md) | 后端路由三模式（direct/proxy/auto）+ 熔断回退 | Accepted |
| [ADR-0002](0002-bubble-free-llm-output.md) | 无气泡 LLM 输出渲染 | Accepted |
| [ADR-0003](0003-flutter-chat-ui-fork.md) | flutter_chat_ui 本地 fork | Accepted |
| [ADR-0004](0004-roleplay-subsystem-isolation.md) | 角色扮演（RP）子系统隔离 | Accepted |
| [ADR-0005](0005-rp-services-10-domain-organization.md) | RP services 10 领域目录组织 | Accepted |
| [ADR-0006](0006-memory-os-facade-core-state-block.md) | RP Memory OS 门面 + Core State Block 封套 | Accepted |
| [ADR-0007](0007-retrieval-broker-unified-interface.md) | RetrievalBroker 统一检索接口 | Accepted |
| [ADR-0008](0008-core-state-dual-write-migration.md) | Core State 双写迁移开关 | Accepted |
| [ADR-0009](0009-sse-streaming-contract.md) | SSE 流式契约 | Accepted |
| [ADR-0010](0010-markdown-docs-local-only.md) | Markdown 文档本地化策略 | Accepted |
| [ADR-0011](0011-rp-services-import-lint.md) | RP services import lint | Accepted |

## 相关文档

- [项目优化主指南](../../.trellis/spec/guides/project-optimization-master-guide.md) — §E 架构任务要求"先写 ADR"
- [后端规范目录](../../.trellis/spec/backend/index.md) — 89 条后端契约
- [架构设计文档](../../ARCHITECTURE.md)、[贡献指南](../../CONTRIBUTING.md)
