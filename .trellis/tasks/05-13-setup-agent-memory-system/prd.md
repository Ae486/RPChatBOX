# setup agent memory system

## Goal

调研并实现 SetupAgent 讨论 session 内的记忆 / 检索系统。该系统生命周期与单个 SetupAgent 讨论 session / setup workspace 一致，服务于长讨论、draft 条目膨胀、stage 内和跨 stage 压缩后的细节恢复与精确检索。它需与 story runtime 的 RP memory 明确区分，避免把角色扮演叙事记忆、用户故事状态或 RP graph/projection 机制误用为 setup 讨论期的 agent memory。

当前已确认口径：SetupAgent memory 是 SetupAgent 的内部检索子系统，不是 `SetupWorkspace` truth，不是 `SetupAgentRuntimeStateService` 的状态扩张，也不是 RP Memory OS。模型通过受控 read-only 工具使用该能力；agent-facing 主路径是 `setup.memory.search` 用于定位 ref，`setup.memory.open` 用于打开单个 ref。打开三级 entry ref 返回四级 section 目录，打开四级 section ref 返回 clean content。`setup.memory.read_refs` 可保留兼容或内部读取能力，但不再作为 agent 的推荐心智入口。

## What I Already Know

- 用户目标是先确认当前 SetupAgent 是否已有服务单个讨论 session 的 memory / retrieval system，再参考 Claude Code / pi-mono 的成熟实现方式做设计与实现。
- agent 记忆系统是特殊且独立的，不等同于 story runtime 的 `rp memory`，也不是跨项目长期用户偏好记忆。
- 当前 setup draft / accepted setup truth 已经是 DB-backed structured JSON。memory 初版应从当前 setup 设定事实来源派生索引：editable draft 与 accepted truth 在 agent-facing 召回语义上都是“设定信息”，应进入同一 folder-like fact index。handoff、runtime compact / recovery refs 属于 context 层恢复线索，不是 memory index / open 工具需要关注的事实来源。
- 重点参考材料：
  - `docs/research/how-claude-code-works-main/docs`
  - `docs/research/claude-code-from-scratch-main`
  - `https://juejin.cn/post/7624105806963834930`
  - `https://juejin.cn/post/7625574757921406991`
- 当前 task 已绑定为 session-scoped Trellis task，不修改 repo 默认 task。

## Requirements (Evolving)

- 调研当前 SetupAgent 是否存在可称为 session-scoped agent memory / retrieval 的实现，包括但不限于：
  - setup runtime 内部状态、loop trace、context pipeline、capability plan、runtime state store；
  - prompt / skill / handoff / Trellis task / journal 是否承担了类 memory 职责；
  - 与 RP memory、story runtime memory、retrieval layer 的边界。
- 阅读 Claude Code 相关文档与最小实现，提炼可迁移的 memory retrieval 模型：
  - 文件层级与加载顺序；
  - 索引、manifest、topic file、side query / selector、freshness 的成熟做法；
  - memory 的写入、更新、冲突处理、压缩与优先级；
  - 与工具调用、prompt assembly、session resume 的关系。
- 形成适配 `chatboxapp` SetupAgent 的设计方案，并明确：
  - session-scoped 数据模型和存储位置；
  - 读路径与写路径；
  - prompt/context 注入边界；
  - 与现有 Trellis、skills、setup workspace、runtime trace 的关系；
  - 测试与迁移策略。
- 在方案确认后实现最小可验证版本。
- 模块化要求：memory 代码必须做成可卸载、可调试的独立模块，不得把 manifest、scoring、reader、tool adapter 全塞进一个大文件。

## Research References

- [`research/current-setup-agent-memory-audit.md`](research/current-setup-agent-memory-audit.md) — 当前 SetupAgent 只有 runtime-private cognition，不是独立 agent memory system。
- [`research/claude-code-memory-reference.md`](research/claude-code-memory-reference.md) — Claude Code 记忆系统参考：文件 + 索引 + topic files + side query + freshness。
- [`research/setup-agent-memory-design-options.md`](research/setup-agent-memory-design-options.md) — SetupAgent agent memory 的三种设计选项与推荐 MVP slice。
- [`research/setup-agent-memory-redesign-plan-2026-05-16.md`](research/setup-agent-memory-redesign-plan-2026-05-16.md) — 基于 Claude Code / Nocturne 复盘后的重构口径：清理 runtime 强制链、改为文件夹式事实索引、三级索引常驻、`setup.memory.open` 打开三级目录或四级内容，以及 clean recall view。

## Acceptance Criteria (Evolving)

- [x] 有一份调研记录说明当前 SetupAgent 是否已有 memory-like 机制，以及为什么它们不足以称为 session-scoped agent memory / retrieval system。
- [x] 有一份 Claude Code memory 机制参考总结，覆盖本地文档、最小实现和用户给出的技术文章。
- [x] 有一份设计方案明确 agent memory 与 RP memory / story runtime memory 的边界。
- [x] 最小实现具备可测试的 manifest、search、open 路径，并通过 read-only setup tools 暴露给 SetupAgent；`read_refs` 仅作为兼容/内部路径保留。
- [ ] 覆盖主要失败路径测试，例如无 workspace / 无命中 / 缺失 ref / 过长 payload bounded / stale fingerprint warning。
- [x] 清理 memory 相关 `SetupActionExpectation` / `ActionDecisionPolicy` / completion guard 强制链，改为 agent-visible index、轻量 prompt/tool guidance 和确定性工具召回。
- [ ] 索引能力支持 folder-like session index：默认到 `stage / category / entry`，当前 stage 展示 `path + ref`，其他 stage 展示 `path + ref + short summary`。
- [x] `setup.memory.search` 可以返回 entry 级和 section 级候选；候选可带 `navigation_summary` 帮助选择 ref，但必须标记为导航摘要而不是事实正文。
- [x] 支持 `setup.memory.open` 单 ref 打开能力：三级 entry ref 只返回四级 section 目录和确定性提示；四级 section ref 返回 clean structured content。
- [x] `setup.memory.open` 的四级内容结果返回 agent-facing clean structured block，保留 text/list/key_value 的有效内容结构，不返回内部结构和 debug metadata。

## Implementation / Check Notes

- 已确认 agent-facing 主链路是 `setup.memory.search` + `setup.memory.open`。`setup.memory.read_refs` 保留为兼容/内部路径，但不作为 prompt guidance 的推荐入口。
- 已清理 runtime guard 方向的强制链：memory 缺失召回不再依赖 `SetupActionExpectation` / `ActionDecisionPolicy` / completion guard 拦截，而是依赖模型可见索引、工具描述、轻量 prompt 心智与确定性的工具返回。
- `setup.memory.open(ref)` 当前只允许一次打开一个 ref。三级 entry ref 返回四级 section 目录和“需要继续 open 四级 ref”的确定性提示；四级 section ref 返回可作为事实依据的 clean structured content。
- Laplace check 后已补强 clean recall view：四级内容必须先从 payload 清洗成 `text` / `list` / `key_value` / `truncated` / `unknown` agent-facing block，再按 `max_chars` 截断；截断或 unknown fallback 不得回显原始 payload JSON，也不得泄漏 `section_id`、`retrieval_role`、`source_kind`、`ref_kind`、`fingerprint` 等内部字段。
- 当前失败路径已有覆盖包括：无命中、缺失 ref、entry 目录 summary bounded、oversized section clean truncation、accepted truth section 与 editable draft section 同 clean shape。`workspace missing` 和 stale fingerprint warning 尚未作为完整验收闭环覆盖，因此“主要失败路径测试”仍不勾选完成。

## Definition of Done

- 相关调研文档落在本 task 的 `research/` 目录。
- 方案经过用户确认后再进入实现。
- 实现遵循现有 SetupAgent 架构边界，不改动 story runtime RP memory 的业务语义。
- 通过与改动风险匹配的单元测试、集成测试或手工验证。
- 交付时说明改动范围、验证结果、剩余风险和后续扩展点。

## Out of Scope

- 不把 story runtime 的 RP memory 重构为 agent memory。
- 不在未确认前引入新外部依赖。
- 不在本 task 初期直接改动生产数据或真实用户长期记忆。
- 不把 memory 设计扩展成完整知识库、GraphRAG 或通用 retrieval 平台。
- 不把该系统设计成 Claude Code 一样的跨项目长期用户/反馈记忆；只借鉴其 manifest、选择、top-k、freshness 和非权威 readback 机制。
- 不把 session memory 初版做成文件存储。文件式只作为 ref/manifest 的检索抽象，物理数据源仍是 setup DB-backed records。

## Open Questions

- 后续是否增加 Claude Code 式 side-query prefetch。当前重构 slice 不做默认 prefetch，先让 context index + tools 驱动 agent 自主召回。
- 后续是否持久化 derived index cache。已确认索引可以作为衍生缓存维护，但必须可从 editable draft / accepted truth 这些 setup fact sources 重建，不能成为 truth store。
- 是否后续移除或隐藏 `setup.memory.read_refs`。当前确认第一版保留兼容，但 agent guidance 主推 `setup.memory.search` + `setup.memory.open`。
- 后续是否支持 `setup.memory.open_many` 或 batch open。当前确认第一版只支持单个 ref，功能稳定后再考虑 batch。

## Technical Notes

- 当前 Trellis task：`.trellis/tasks/05-13-setup-agent-memory-system`
- 当前 session task source：`session`
- 初始阶段应先读文档和现有 SetupAgent 代码，再规划实现；不得把 RP memory 当作现成答案直接复用。
