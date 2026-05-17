# SetupAgent Memory Design Options

Date: 2026-05-13

Status: Superseded by [`setup-agent-memory-redesign-plan-2026-05-16.md`](setup-agent-memory-redesign-plan-2026-05-16.md).

This document records the earlier design exploration. Do not use its `search/read_refs` or runtime-policy wording as the current implementation plan. The current confirmed agent-facing workflow is:

```text
agent-visible level-3 session index
  -> setup.memory.search when the ref is unknown
  -> setup.memory.open(level-3 entry ref) returns level-4 section directory
  -> setup.memory.open(level-4 section ref) returns clean structured content
```

`setup.memory.read_refs` is compatibility/internal only while older tests and paths are migrated.

## Recommendation

推荐走 **Option B：session-scoped agent memory retrieval + structured draft manifest + 精确 readback 工具**。

这条路径借鉴 Claude Code 的成熟检索机制，但不照搬它的长期用户记忆作用域，且和当前 `chatboxapp` 的边界最稳：

- 不复用 RP Memory OS；
- 不把 `SetupWorkspace` 替换成 memory truth；
- 不扩大 runtime-private cognition 的语义；
- 不引入向量数据库或新外部依赖；
- 可以先做可测试的 search/open 闭环，再逐步加 side query 和 prefetch 优化。

## Option A: Treat Existing Runtime Cognition As Memory

### Shape

继续扩展 `SetupAgentRuntimeStateService`，让 `SetupCognitiveStateSnapshot` 保存更多跨 turn 信息。

### Pros

- 改动小，已有 DB record 和测试。
- 已接入 runtime overlay。
- 现有失效机制能处理 user edit / proposal reject。

### Cons

- 概念错误：runtime cognition 是 workspace + step 私有治理状态，不是 agent 长期记忆。
- 会把用户偏好、项目反馈、协作经验塞进 setup draft lifecycle。
- 容易违反 Phase F 约束：setup runtime-private cognition 不进入 Memory OS durable layer，也不应扩张成新的 durable knowledge source。
- 无法跨 workspace / session 复用。

### Verdict

不推荐。它会制造边界债。

## Option B: Session-Scoped Agent Memory Retrieval Beside Setup Runtime

### Shape

新增 SetupAgent session memory retrieval service：

```text
backend/rp/agent_memory/
  contracts.py
  service.py
  selector.py
```

存储 / manifest 可利用当前 draft 天然文件式、结构化的特点。下方 Markdown-like topic/index 文件结构是 2026-05-13 早期探索，不是当前确认的 MVP 主存储或 source taxonomy；当前确认口径以 editable draft 与 accepted truth 派生索引为准：

```text
data/agent_memory/setup_agent/{workspace_id}/
  MEMORY.md
  user_*.md
  feedback_*.md
  project_*.md
  reference_*.md
```

初始 scope：

- `workspace_id` / setup discussion session：与 SetupAgent 生命周期一致；
- 可跨 stage，但不跨 setup workspace 长期复用；
- activation / archive 后可只保留 accepted truth，session memory 不继续作为 active runtime memory。

### Read Path

1. `SetupAgentExecutionService._prepare_runtime_v2_launch()` 前后生成或读取 session memory manifest。
2. manifest 覆盖 setup fact sources：editable draft entries / sections 与 accepted setup truth entries / sections。handoff、compact summary、recovery hints 属于 context 层，不进入 memory index/open 来源。
3. `setup.memory.search` 基于 query + filters 返回 refs 和导航摘要。
4. `setup.memory.open` 打开单个 ref：三级 entry ref 返回四级 section 目录，四级 section ref 返回 clean structured content。
5. 可选的 system-side selector/prefetch 在主模型调用前选出少量候选，但精确内容仍通过 open 或受控注入进入上下文。

### Write Path

MVP 不优先做长期“写记忆”。记忆源主要来自 setup session 的结构化事实状态：

- draft entries / sections；
- accepted setup truth refs。

如果后续需要记录 raw discussion distillation，应作为 session-scoped compact artifact，而不是 Claude Code 式长期 user/feedback memory。

### Authority Rules

Prompt 必须写清：

- Agent memory retrieval result 是 setup session 内的检索候选，不是 workspace truth。
- 与 `SetupWorkspace`、当前 draft、accepted commit、代码、Trellis 文档冲突时，以当前可验证事实为准。
- 检索结果是导航候选；写 draft 或回答精确细节前应通过 `setup.memory.open` 打开四级内容节点读取当前 payload。

### Pros

- 借鉴 Claude Code 的索引 / selector / freshness / 少量注入方式。
- 贴合当前 draft 天然文件式、严格格式化、易索引的结构。
- 易测试：纯文件 IO、frontmatter、index truncation、selector mock。
- 不需要新依赖。
- 可独立演进为后台提取或 team memory。

### Cons

- 需要新增 prompt 注入层和路径安全策略。
- 需要定义 search/open 工具或 service API。
- 如果完全依赖 Agent 自行判断是否搜索，长上下文压缩后可能漏检；如果总是 prefetch，可能增加延迟和噪声。

### Verdict

推荐。它满足当前任务目标且风险最低。

## Option C: Use RP Memory OS / Retrieval Layer For Agent Memory

### Shape

把 SetupAgent 的长期记忆写入 Memory OS，然后通过 `memory.search_recall` / `memory.search_archival` 找回。

### Pros

- 复用已有 retrieval / memory 抽象。
- 后续可能支持复杂查询。

### Cons

- 直接违反用户边界：agent memory 与 story runtime RP memory 必须区分。
- RP Memory OS 是叙事和 runtime state layer，不是 agent 操作偏好系统。
- 记忆写入会被 proposal / projection / retrieval ingestion 语义污染。
- 向量 / retrieval 对当前规模过重，也弱化可解释性。

### Verdict

不推荐。仅未来可以让 agent memory 中的 `reference` 指向 RP memory 资源，但不应把 RP memory 当 agent memory store。

## MVP Slice Proposal

### Slice 1: Research + Contract

Status: in progress in this task.

Deliverables:

- current implementation audit；
- Claude Code reference summary；
- design options；
- confirmed MVP boundary。

### Slice 2: Session Manifest + Tests

Implement:

- `SetupSessionMemoryRef`
- `SetupSessionMemoryHit`
- `SetupSessionMemoryManifestBuilder`
- editable draft / accepted truth entry and section ref extraction
- workspace version / draft fingerprint freshness metadata

Tests:

- builds refs from draft entries and sections
- excludes prior stage handoff refs
- excludes compact recovery hints
- preserves workspace version / draft fingerprint
- excludes unrelated raw runtime debug / loop trace

### Slice 3: Search + Open Tools

Implement:

- `setup.memory.search`
- `setup.memory.open`
- filters by stage / block_type / ref_kind
- deterministic scoring first, optional LLM selector later
- exact readback routed to existing editable draft / accepted truth sources

Tests:

- search returns relevant refs
- open returns section directories for entry refs and exact clean content for section refs
- stale fingerprint warns / re-reads current source
- missing refs are reported clearly

### Slice 4: Runtime Policy / Optional Prefetch

Implement:

- prompt/context guidance for memory search when exact setup facts are needed and missing from current context
- optional side query / selector prefetch over manifest
- top-N bounded candidate injection
- no-block fallback when selector fails

Tests:

- compact context can expose navigation guidance, but does not create memory search expectations
- no relevant hits does not block normal response
- prefetch failure does not block setup turn
- injected candidates are bounded and marked non-authoritative until the agent opens the relevant ref with `setup.memory.open`

## Open Question For User

MVP 的第一版建议选择：

1. **Tools first**：先实现 manifest + `setup.memory.search/open`，由 Agent 显式检索。
2. **Prefetch first**：第一版就做 Claude Code 式 side query prefetch，自动注入候选。
3. **Hybrid**：tools first，同时预留 prefetch 接口；后续在 compact/cross-stage 场景开启。

我的建议是 3，但第一刀按 tools first 落地。因为当前 SetupAgent 已经有复杂 runtime loop，先把 ref schema、search/open、freshness 和非权威边界固化，再引入 selector/prefetch，风险更低。
