# Claude Code Memory Reference

Date: 2026-05-13

## Conclusion

Claude Code 的 agent memory 不是 RAG，也不是把所有历史塞进 prompt。它更接近一套文件系统驱动的、可解释的、用户可编辑的长期协作记忆：

1. `MEMORY.md` 是常驻索引，不是正文容器。
2. topic files 用 Markdown + YAML frontmatter 保存真实内容。
3. 每轮只扫描 topic frontmatter，再用模型 side query 选最多 5 个相关文件。
4. 记忆是 point-in-time observation，过期记忆必须提醒模型核验。
5. 保存规则强调只记不可从代码、git、项目文件或当前状态推导的信息。

这个模型给 SetupAgent 的启发不是“照搬长期用户记忆”，而是采用可解释 index、manifest selection、freshness 和按需打开的工程方式。当前 SetupAgent memory 的目标是 session-scoped setup fact recovery：从 editable draft 与 accepted setup truth 派生同一套 folder-like index/open workflow；handoff、runtime compact summary、recovery hints 仍留在 context assembly / compaction recovery 层。

## Local Reference: how-claude-code-works

Primary files:

- `docs/research/how-claude-code-works-main/docs/08-memory-system.md`
- `docs/research/how-claude-code-works-main/docs/03-context-engineering.md`
- `docs/research/how-claude-code-works-main/docs/13-minimal-components.md`

### Core model

`08-memory-system.md` 给出的核心边界是：记忆只保存不可从当前项目状态推导的信息。代码结构、路径、git 历史、临时任务状态、已经在 CLAUDE.md 中的内容都不该保存。

它把记忆分成四类：

| Type | Purpose | SetupAgent mapping |
| --- | --- | --- |
| `user` | 用户身份、偏好、知识背景 | 不进入当前 SetupAgent memory source set；这类偏好若要保留，应走独立长期协作记忆而不是 setup fact recovery |
| `feedback` | 用户对 agent 行为的纠正或肯定 | 不进入当前 SetupAgent memory source set；不能产生 `setup.memory.search` hits |
| `project` | 项目动态、决策、截止日期、原因 | 只作为调研参考；当前 memory index 仍以 setup facts 为 source |
| `reference` | 外部系统或资料位置 | 只作为调研参考；不替代 editable draft / accepted truth |

### Storage model

下方是 Claude Code 的长期记忆存储模型，只作为可解释 index / manifest 机制参考；它不是当前 SetupAgent memory 的 source taxonomy 或 MVP storage 方案。

目录结构是：

```text
memory/
├── MEMORY.md
├── user_*.md
├── feedback_*.md
├── project_*.md
└── reference_*.md
```

topic file 使用 frontmatter：

```markdown
---
name: concise reply preference
description: user prefers concise execution updates without end summaries
type: feedback
---

Rule content.

**Why:** ...
**How to apply:** ...
```

关键点是 `description` 不只是元数据，它是召回选择器的主要依据。

### Recall model

召回流程：

1. `MEMORY.md` index 每次会话加载。
2. 扫描 topic files，只读取前 30 行 frontmatter。
3. 将 manifest 交给 Sonnet side query。
4. side query 输出最多 5 个 filename。
5. 读取全文并作为 meta/system-reminder 注入当前上下文。

`03-context-engineering.md` 还强调记忆预取可以和主模型生成并行执行，减少用户感知延迟。

### Drift control

Claude Code 对 memory freshness 的处理很适合 SetupAgent：

- 记忆带有 mtime / age。
- 超过一定时间后提醒模型：这只是历史观察，不是当前事实。
- 如果记忆提到文件、函数、路径或实现细节，应先读当前代码验证。

这个约束能避免 agent memory 和真实 `SetupWorkspace` / backend 代码 / Trellis 文档漂移。

## Local Reference: claude-code-from-scratch

Primary files:

- `docs/research/claude-code-from-scratch-main/src/memory.ts`
- `docs/research/claude-code-from-scratch-main/python/mini_claude/memory.py`
- `docs/research/claude-code-from-scratch-main/src/prompt.ts`
- `docs/research/claude-code-from-scratch-main/src/session.ts`

### Minimal TypeScript implementation

`src/memory.ts` 已经实现了一套可迁移的最小 memory subsystem：

- `getMemoryDir()`：`~/.mini-claude/projects/{projectHash}/memory`
- `listMemories()`：读取所有 topic files 并解析 frontmatter
- `saveMemory()` / `deleteMemory()`：写入或删除 topic file 后更新 index
- `loadMemoryIndex()`：加载并截断 `MEMORY.md`
- `scanMemoryHeaders()`：读取 frontmatter，最多 200 个文件
- `formatMemoryManifest()`：生成 selector manifest
- `selectRelevantMemories()`：side query 选择最多 5 个记忆
- `startMemoryPrefetch()`：异步预取，避免阻塞主循环
- `formatMemoriesForInjection()`：用 `<system-reminder>` 包装注入内容
- `buildMemoryPromptSection()`：把 memory 指令和 index 拼入系统 prompt

Python 版本 `python/mini_claude/memory.py` 与 TypeScript 版本基本同构，说明这套设计可以直接迁移到 Python backend，不依赖 Node 特性。

### Prompt integration

`src/prompt.ts` 在 `buildSystemPrompt()` 中拼接：

- cwd / date / platform / shell；
- git context；
- CLAUDE.md；
- memory section；
- skills；
- agents；
- deferred tools。

SetupAgent 对应点不是把 memory 直接塞进 `SetupContextPacket`，而是在 context assembly / prompt guidance 中提供 session fact index view 和工具使用规则，并明确 index/search summary 只是导航：需要精确信息时走 `setup.memory.search` + `setup.memory.open`。`setup.memory.read_refs` 只保留兼容 / 内部路径。

## External Articles

### CC 源码解读 #1：Claude Code 为什么不用 RAG？

Source: https://juejin.cn/post/7624105806963834930

Takeaways:

- Claude Code 对代码库探索依赖工具：Grep、Glob、Read、Bash、FileIndex、Explore subagent、Compaction，而不是预先 embedding 全仓库。
- 对 memory 也不用 embedding。它用 side query 对 memory manifest 做语义选择。
- 有工具权限的 coding agent 更适合“模型自己搜 + 小索引 + 上下文治理”，而不是一开始引入向量数据库。
- RAG 仍适合超大非结构化文档、多语言语义检索、无工具权限等场景。

### CC 源码解读 #2：记忆系统为什么不用向量数据库？

Source: https://juejin.cn/post/7625574757921406991

Takeaways:

- 两层结构：`MEMORY.md` 索引 + topic files。
- `MEMORY.md` 不存正文，只存文件指针和简短描述。
- side query 最多选择 5 个相关文件，已 surfaced 的文件不重复加载。
- 约束：index 最多 200 行 / 25KB，memory files 最多 200 个，frontmatter 只读前 30 行。
- 记忆过期提醒很重要，因为有来源的旧信息比无来源信息更容易被模型错误信任。
- 不用向量数据库的原因：规模不需要、LLM selection 更适合“需要哪条记忆”的推理问题、部署复杂度低、可解释性强。

## What To Borrow For SetupAgent

### Borrow directly

- Index-first mental model: always-visible small index, full content opened only when needed.
- Manifest/header selection instead of stuffing all content into prompt.
- Freshness warning and “verify against current truth” prompt.
- Side query / selector can be borrowed later, but first slice should prefer explicit `search/open` tools.
- 200 files / 200 lines / 25KB / 30 frontmatter lines / top 5 recall limits.
- Already-surfaced filtering.

### Adapt carefully

- SetupAgent memory should not mutate RP Memory OS.
- SetupAgent memory should not become `SetupWorkspace` truth.
- Memory content should be injected as lower-authority guidance, not as draft facts.
- Editable draft and accepted truth should be normalized into one agent-facing fact index/open workflow.
- Handoff, runtime compact summary, and recovery hints should remain context-layer guidance, not memory index/open sources.

### Avoid for MVP

- Team memory.
- KAIROS / daily logs / dream distillation.
- Background automatic extraction after every turn.
- File-backed primary memory store.
- Long-term user/feedback/project/reference memory as this feature's MVP source taxonomy.
- Vector database or retrieval-core integration.
- Graph projection.

## Candidate MVP Shape

```text
backend/rp/setup_agent_memory/
├── contracts.py
├── draft_source.py
├── truth_source.py
├── manifest_builder.py
├── scorer.py
├── reader.py
└── service.py

sources:
  SetupWorkspace editable draft
  accepted setup truth via SetupTruthIndexService
```

Flow:

1. Context assembly builds or refreshes a small session fact index view.
2. If the visible index is insufficient, the model calls `setup.memory.search`.
3. Search returns entry/section refs plus bounded `navigation_summary`, not payload.
4. The model calls `setup.memory.open` on one ref.
5. Opening a level-3 entry returns a level-4 section directory; opening a level-4 section returns clean structured content.

Open design choice: whether later slices add side-query prefetch over the manifest. Given SetupAgent already has model-gateway/tool-call complexity, the pragmatic MVP should keep deterministic index injection plus explicit `setup.memory.search` / `setup.memory.open` first, then add selector/prefetch only after the clean recall contract is stable.
