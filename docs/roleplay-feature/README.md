# AI 角色扮演/创作特化功能研究

> 研究阶段文档，旨在为 ChatBoxApp 添加特化的创作/角色扮演助手功能

## 背景

现有方案的问题：
- **SillyTavern (ST)**：功能强大但耗 token，学习曲线陡峭
- **普通客户端**（Cherry Studio、ChatBox）：长文记忆差，参数调整乏力，上下文过长时断崖式失忆

## 目标

构建一个 **"轻量但有效"** 的特化方案：
1. 解决长文记忆问题（Memory Snap）
2. 提供精细的上下文控制
3. 兼顾 token 效率
4. 保持易用性

## 文档索引

| 文档 | 说明 |
|------|------|
| [01-ST-FEATURES.md](./01-ST-FEATURES.md) | SillyTavern 核心特性深度分析 |
| [02-IMPLEMENTATION-ROADMAP.md](./02-IMPLEMENTATION-ROADMAP.md) | 实现路线图与优先级 |
| [03-DATA-MODELS.md](./03-DATA-MODELS.md) | 数据模型设计草案 |
| [04-AI-WRITING-PROJECTS-ANALYSIS.md](./04-AI-WRITING-PROJECTS-ANALYSIS.md) | AI 写作项目核心架构分析（MuMuAINovel / Arboris-Novel） |
| [05-LETTA-MEMORY-ANALYSIS.md](./05-LETTA-MEMORY-ANALYSIS.md) | Letta (MemGPT) 高级记忆系统深度分析 |
| [06-COMPREHENSIVE-SUMMARY.md](./06-COMPREHENSIVE-SUMMARY.md) | 四大项目可借鉴优势综合总结 |
| [07-REQUIREMENTS-BASELINE.md](./07-REQUIREMENTS-BASELINE.md) | 写作/跑团式角色扮演：需求基底（Draft） |
| [08-PROMPT-DESIGN.md](./08-PROMPT-DESIGN.md) | Prompt 设计指南：角色扮演/创作功能 |
| [09-BLOCK-TAXONOMY-AND-FLOWS.md](./09-BLOCK-TAXONOMY-AND-FLOWS.md) | 块级结构与记忆流转（Draft） |
| [10-BLOCK-MODULE-FRAMEWORK.md](./10-BLOCK-MODULE-FRAMEWORK.md) | 块级模块框架（Mod/创意工坊式）（Draft） |
| [11-VIEW-CATALOG-AND-TRACKERS.md](./11-VIEW-CATALOG-AND-TRACKERS.md) | View 目录与 Tracker 模式（Draft） |
| [12-KEY-EVENTS-LINKER-AND-CONSISTENCY-GATES.md](./12-KEY-EVENTS-LINKER-AND-CONSISTENCY-GATES.md) | Key Events / Linker / 一致性闸门（Draft） |
| [13-EDIT-MODES-AND-PERMISSIONS.md](./13-EDIT-MODES-AND-PERMISSIONS.md) | 编辑模式与权限（Draft） |
| [14-EDGE-CASES-AND-OPEN-QUESTIONS.md](./14-EDGE-CASES-AND-OPEN-QUESTIONS.md) | 容易忽略的点与开放问题（Draft） |
| [15-PROPOSALS-CATALOG.md](./15-PROPOSALS-CATALOG.md) | Proposal 清单（要有哪些提议？）（Draft） |
| [16-USER-EDIT-TRACKING-AND-CORRECTION-SIGNALS.md](./16-USER-EDIT-TRACKING-AND-CORRECTION-SIGNALS.md) | 用户对话编辑追踪与纠错信号（Draft） |
| [17-BRANCHING-ROLLBACK-AND-JOB-SAFETY.md](./17-BRANCHING-ROLLBACK-AND-JOB-SAFETY.md) | 分支+回滚+后台任务：一致性与竞态处理（Draft） |
| [18-SNAPSHOT-ROLLBACK-TECHNICAL-DESIGN.md](./18-SNAPSHOT-ROLLBACK-TECHNICAL-DESIGN.md) | 快照级回滚：技术实现草案（Draft） |
| **Phase 4: 架构审查与最终设计** | |
| [19-ARCHITECTURE-REVIEW.md](./19-ARCHITECTURE-REVIEW.md) | 架构问题诊断与改进方案 |
| [20-AGENT-ORCHESTRATION-DESIGN.md](./20-AGENT-ORCHESTRATION-DESIGN.md) | Agent 体系与编排设计 |
| [21-TECHNICAL-IMPLEMENTATION-MAPPING.md](./21-TECHNICAL-IMPLEMENTATION-MAPPING.md) | 技术实现映射（Hive 模型、版本控制） |
| [22-FINAL-SUMMARY.md](./22-FINAL-SUMMARY.md) | 设计总结与实现路线图 |
| [23-SKILL-BASED-AGENT-DESIGN.md](./23-SKILL-BASED-AGENT-DESIGN.md) | **Skill 化 Agent 设计**（跨模型兼容） |
| [24-PROJECT-CODEBASE-REFERENCE.md](./24-PROJECT-CODEBASE-REFERENCE.md) | **项目代码库参考**（数据模型、服务层、集成点） |
| **开发指导** | |
| [CLAUDE.md](./CLAUDE.md) | **开发指导文档**（Claude/Codex 协作规范、实现路线图） |

## 核心概念速查

```
┌─────────────────────────────────────────────────────────────────┐
│                      上下文组装流程                              │
├─────────────────────────────────────────────────────────────────┤
│  [System Prompt]                     ← 系统指令                 │
│       ↓                                                         │
│  [Character Card]                    ← 角色定义                 │
│       ↓                                                         │
│  [World Info / Lorebook]             ← 按关键词触发注入         │
│       ↓                                                         │
│  [Memory Summary]                    ← 历史摘要（可选）         │
│       ↓                                                         │
│  [Chat History]                      ← 对话历史                 │
│       ↓                                                         │
│  [Author's Note @ Depth N]           ← 任意深度插入提醒         │
│       ↓                                                         │
│  [User Input]                        ← 当前输入                 │
└─────────────────────────────────────────────────────────────────┘
```

## 关键问题清单

- [ ] World Info 的触发机制如何高效实现？
- [ ] 记忆摘要的时机和粒度？
- [ ] 角色卡格式兼容 ST V2 Spec 还是自定义？
- [ ] 多角色/群聊是否纳入 MVP？
- [ ] 是否需要导入 ST 源码进行深度研究？

---

**状态**：开发阶段（MVP 策略 C）
**最后更新**：2026-01-15
**Codex Session**: `019b8e40-021b-7563-b300-cf99e87f76ec`
