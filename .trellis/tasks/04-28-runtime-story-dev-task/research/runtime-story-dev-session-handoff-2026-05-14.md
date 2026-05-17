# Runtime Story Dev Task Session Handoff (2026-05-14)

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Purpose: 给下一 session 一个可直接接续的上下文：Stage V 到底完成了什么、哪些能力仍未完成、哪些能力只是低完成度 foundation，以及下一阶段建议怎么推进。

## 0. 先说结论

Stage V 可以作为 **Branch-aware Memory Product Foundation** 收口，但不能被解释为
writer brainstorm 产品链路已经完成。

更准确的边界是：

1. Stage V 已完成 branch-aware memory / read scope / memory inspection /
   governed memory action / post-write read-manifest 的 foundation。
2. Stage V 已修正 brainstorm 的安全边界：不再让 brainstorm 直接解析自然语言并私自改
   Core；brainstorm transcript 也改为读取 branch-visible snapshot。
3. Stage V 没有完成用户可用的 writer brainstorm 产品闭环。当前前端 brainstorm 仍是
   minimal hookup：默认 `dry_run_items`，无真实 LLM discussion，无正常气泡，无 item
   review UI，且 `redirect/pending_review` 状态反馈仍可能误导用户。

下一阶段建议命名为：

`Stage W: Writer Brainstorm Product Loop + Fresh Seed Validation`

## 1. 下一 session 必看文档顺序

不要重新全量读所有 research。按下面顺序看。

### 1.1 执行计划与当前状态

1. [story-runtime-execution-plan.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-execution-plan.md)
   - 看 `Stage V` 的 V0-V6 完成记录。
   - 看主脑规则、subagent 并发规则、模块级 check 规则。

2. [story-runtime-branch-aware-memory-product-foundation-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-branch-aware-memory-product-foundation-spec.md)
   - 看 Stage V 的需求真相，尤其 V4 Writer Brainstorm Apply。

3. [story-runtime-branch-aware-memory-product-foundation-development-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-branch-aware-memory-product-foundation-development-spec.md)
   - 看 V4/V5 的开发合同和字段边界。

4. [context-engineering-compact-summary-development-handoff.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/context-engineering-compact-summary-development-handoff.md)
   - 看 brainstorm summarize / compact 的通用上下文工程口径。

5. [story-runtime-writing-worker-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-writing-worker-spec.md)
   - 看 writer / discussion / brainstorm / rewrite 的 worker 分工。

6. [story-runtime-product-acceptance-manual-qa.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-product-acceptance-manual-qa.md)
   - 看当前手测清单，但注意只测已实现能力，不要拿 future scope 当本阶段 blocker。

### 1.2 当前必须看的代码锚点

后端：

- [story_brainstorm_service.py](H:/chatboxapp/backend/rp/services/story_brainstorm_service.py)
  - Brainstorm session / item / summarize / apply 当前实现。
  - 必须确认下一阶段不要把自然语言字段解析塞回这里。

- [story_session_service.py](H:/chatboxapp/backend/rp/services/story_session_service.py)
  - `build_chapter_snapshot(...)`
  - branch-visible pending pointer / effective phase / visible discussion filtering。

- [story_turn_domain_service.py](H:/chatboxapp/backend/rp/services/story_turn_domain_service.py)
  - writing/rewrite/accept/complete 的 turn-domain 主链。

- [core_state_as_of_resolver.py](H:/chatboxapp/backend/rp/services/core_state_as_of_resolver.py)
  - Core State turn-bound manifest / as-of revision 解析。

- [legal_longform_session_seed.py](H:/chatboxapp/backend/rp/devtools/legal_longform_session_seed.py)
  - fresh legal longform session seed。
  - 当前 memory edit 报错首先应该用 fresh seed 复测，而不是直接判定链路坏。

- [test_story_brainstorm_service.py](H:/chatboxapp/backend/rp/tests/test_story_brainstorm_service.py)
  - Brainstorm 安全边界、防窄解析、branch-visible transcript 的测试。

- [test_legal_longform_session_seed.py](H:/chatboxapp/backend/rp/tests/test_legal_longform_session_seed.py)
  - fresh seed direct edit / manifest 测试。

前端：

- [longform_story_page.dart](H:/chatboxapp/lib/pages/longform_story_page.dart)
  - 当前 brainstorm send path、Memory panel、runtime inspect、rewrite/adoption UI 都在这里。

- [backend_story_service.dart](H:/chatboxapp/lib/services/backend_story_service.dart)
  - Brainstorm API 调用、Memory API 调用。

- [story_memory_panel.dart](H:/chatboxapp/lib/widgets/story_memory_panel.dart)
  - Memory product surface。

## 2. 下一 session 必须遵守的规则

这些规则来自用户在长线任务里的反复补充，下一 session 不要漂移：

1. 以 task 下需求、spec、开发规格书为准。旧 runtime / MVP 只做参考，必要时可以删除旧链路。
2. 单个模块/功能由同一个 implement agent 连续负责到底；模块完成后才做一次模块级 check。
3. 同时最多两个 subagent；只有互不依赖、互不冲突的模块才能并行。
4. implement 使用 `gpt-5.4 xhigh`；check 使用 `gpt-5.5 xhigh`。
5. 不允许同时保留两套链路或含糊 fallback。正确链路明确后，应删除/绕开错误链路。
6. 测试和手测只覆盖已实现能力，不要测 future scope。
7. 遇到设计不清：
   - 先查 task 文档、spec、开发规格书；
   - 再查已有代码和成熟框架/项目；
   - 仍不能推出口径时再 grill 用户。
8. Brainstorm 的层级边界非常重要：
   - brainstorm 是 writer 的讨论人格 / mode；
   - brainstorm 不知道 Memory OS 细节；
   - brainstorm 不输出 `target_layer / target_domain / operation_kind / intent_labels`；
   - 用户提交的 active item 交给 W5 consumer；
   - scheduler / dispatcher 选择 Core domain owner worker，而不是在 Core / Recall / Archival 之间做 layer dispatch；
   - 对应 Core worker 可通过 Retrieval Broker / 工具召回 Recall / Archival evidence；
   - Core worker 再产出字段级 executable change；
   - Core mutation 走 shared mutation kernel。

## 3. Stage V 完成了什么

### 3.1 V0 Product Evidence Lock

已完成 clean longform + branch + runtime inspect baseline 记录。

重要结论：

- old session / old outline artifact 不作为 Stage V blocker。
- Stage V 验收只针对已实现的 V0-V5 foundation scope。

### 3.2 V1 Branch-aware Memory Resolver And Writer Context

已基本完成：

- writer context、Memory inspection、runtime inspect、Recall/Retrieval runtime reads 共享 branch-aware read scope。
- branch-from-turn 使用 active branch lineage + cutoff turn，不读 source branch post-fork future memory。
- Runtime-owned retrieval scope 失败时 fail closed，不走 weak identity fallback。
- runtime artifact metadata 需要 canonical `runtime_*` ownership metadata，不再信 legacy fallback。
- Core State as-of resolver 支持 turn-bound manifest / object revision 解析。

注意：

- old session 的空 `historical_as_of_unavailable` manifest 不会被自动修复。
- fresh seed 应该优先用于判断当前链路是否坏。

### 3.3 V2 Backend Memory Product Contract

已基本完成：

- `/memory/inspection` 作为 Core / Projection / Workspace / Recall / Archival 的 canonical envelope producer。
- Core direct edit 走 shared governed mutation。
- Recall action 走 lifecycle review。
- Archival evolution 走 version / reindex governance。
- action receipt 带 refresh entrypoint，可刷新 Memory inspection 和 runtime inspect。

### 3.4 V3 Frontend Memory Product Surface

已完成 foundation：

- Longform 页面有 Memory 入口。
- 前端消费 backend canonical envelope，不发明第二套 Memory DTO。
- 能看 Core / Projection / Runtime Workspace / Recall / Archival。
- 能触发 Core direct edit、Recall lifecycle action、Archival evolution。

不足：

- UX 仍偏工程化。
- Recall 按钮语义不够产品化，用户不容易理解发生了什么。
- action 状态提示需要继续收敛。

### 3.5 V4 Writer Brainstorm Apply

已完成 historical foundation 和安全修复，但没有完成产品闭环。当前 Stage W
已经取代旧 V4 `confirmed/apply` 口径：产品路径是 brainstorm discussion ->
summarize -> draft batch -> 用户编辑/新增/删除/恢复 -> submit 后 active items
成为 `pending_processing`。W5 才消费这些 frozen items。

已完成：

- `BrainstormSession / BrainstormItem` 基础模型存在。
- `BrainstormItem` forbid routing fields，保持 memory-layer agnostic。
- 已删除错误的 `mood` 窄解析 / auto Core edit。
- historical V4 apply 在无 `core_field_changes` 时会进入
  `redirect/pending_review`，不自动改 Core；Stage W 前半段不再把 submit
  表达为 apply。
- `core_field_changes` 只作为后续 W5 外部 scheduler/worker 产出的字段级
  变更输入，不属于 brainstorm summarize / batch submit 输出。
- transcript 读取 branch-visible snapshot discussion entries，不读 hidden branch discussion。
- main hidden pending 不再卡住 child branch 续写。

未完成：

- 没有真实 brainstorm discussion 气泡链路。
- 当前产品路径仍可使用 `dry_run_items` 绕过 LLM summarize。
- 没有明确 summarize button / review item UI。
- 旧 `redirect/pending_review` 成功态仍是历史风险；Stage W UI 必须显示 batch
  submitted / pending processing，而不是 memory apply success。
- `pending_processing` item -> scheduler -> Core owner worker -> Core mutation
  的真实链路未完成。

### 3.6 V5 Post-write Memory Maintenance Minimum Closure

已完成 minimum closure：

- projection refresh 不再只是 boolean placeholder。
- deferred / hidden / stale materialization job 有 read-manifest evidence。
- writer packet/read manifest 不会把 deferred/hidden/stale 当 completed selected memory。
- branch/rollback-hidden future materialization jobs 会作为 omitted evidence，而不是进入当前 writer packet。

不足：

- Recall / Archival materialization executor 仍不是完整成品。
- Post-write memory quality 仍是 minimum closure，不是最终维护质量。

### 3.7 V6 Product Acceptance

正式 check 允许 Stage V finish，前提是：

- Stage V 只按 foundation scope finish；
- 不把完整 brainstorm product loop、legacy session migration、完整 Recall/Archival executor、branch merge、full RP/TRPG runtime 算作已完成。

## 4. 当前已完成 / 未完成 / 少量完成清单

下一 session 必须核对这个清单，不要直接照抄为最终事实。

### 4.1 已基本完成

- Runtime Workspace / evidence ledger 主链。
- Deterministic context orchestration。
- Writing worker structured request/result 主链。
- Writer-side bounded retrieval loop 的显式门控路径。
- Post-write governance / workflow job ledger foundation。
- Branch / rollback 应用层 visibility truth。
- LangGraph checkpoint pointer 作为薄技术锚点。
- Longform rewrite / revision overlay 后端合同。
- Minimal frontend revision surface。
- Runtime inspect / debug 只读面板。
- Structured outline / beat cursor / one accepted segment covers one beat。
- Chapter bridge summary provider foundation。
- Branch-aware memory read scope。
- Memory backend product contract。
- Memory frontend surface foundation。
- Stage V safety fixes：
  - no brainstorm mood parser；
  - hidden pending 不阻塞 child branch；
  - brainstorm transcript 不读 hidden discussion。

### 4.2 完成度低

- Writer Brainstorm 产品链路。
- Scheduler / dispatcher 到 Core worker 的真实闭环。
- Core worker 从 user intent 到 field-level patch 的 LLM 能力。
- Memory UI 的产品语义和状态反馈。
- Recall action 的用户可理解性。
- Story Evolution / Archival 编辑产品体验。
- Post-write memory materialization 的真实质量。
- Writer 输出质量控制和 eval。
- Mode selection / multi-mode runtime 产品入口。
- Runtime inspect 的用户可读性。
- Legal longform seed / hand测 session 工具边界。

### 4.3 未实现或明确非当前范围

- 完整 branch UI / branch tree / branch compare。
- Branch merge。
- Physical purge / GC。
- 完整 RP/TRPG runtime。
- SuperDoc/WebView 集成。
- Manual beat editor。
- 复杂 paragraph rewrite UI / batch rewrite。
- 完整通用 Context Engineering / Compact 模块。
- 完整端到端 UI 自动化和模型质量 eval。
- Legacy session repair/backfill。
- 完整 scheduler/worker trace 可视化。

## 5. 当前刚暴露的两个问题

### 5.1 Memory direct edit 报错

用户手测旧 session 报：

`core_state_as_of_revision_missing:core_snap_07e93bb3534b:core_state.authoritative:story:character.state_digest`

只读调查结论：

- 这个 session 里 `character.state_digest` authoritative revision 存在。
- 失败 turn 绑定到了空的 `historical_as_of_unavailable` manifest：
  `core_snap_07e93bb3534b`。
- 该 manifest 的 `effective_revision_map_json = {}`。
- 原修复覆盖的是 fresh / replace legal longform seed 的 latest runtime turn manifest。
- 原修复不自动迁移已有旧 session / 已绑定旧空 manifest。

下一 session 不要先修 repair。先做 fresh seed 验证：

1. 重新生成一版合法 longform session。
2. 在新 session 上只测 Core memory direct edit。
3. 如果新 session 通过，将旧 session 报错归类为 legacy hand-test 数据问题。
4. 如果新 session 仍失败，才把它升级为 Stage W 前置逻辑 bug。

### 5.2 Brainstorm 无 LLM / 无气泡 / 假成功

只读调查结论：

- 前端当前 `_sendDiscussion()` 会调用 brainstorm start/summarize/update/apply。
- `BackendStoryService.summarizeBrainstormSession()` 默认传 `dry_run_items`。
- 后端看到 `dry_run_items` 会跳过 LLM。
- 前端没有把用户输入持久化或显示为 discussion 气泡。
- 旧 apply 返回 `redirect/pending_review` 时，前端仍可能显示“完成/成功”。
- 当前 Stage W 应删除这条产品心智：W1-W4 的成功反馈只代表 batch submit
  进入 `pending_processing`，不是 memory apply 完成。

这是当前 product path 的真实缺口，不是后端 LLM provider 故障。

## 6. 下一阶段建议

建议新阶段：

`Stage W: Writer Brainstorm Product Loop + Fresh Seed Validation`

### W0. Fresh Seed Validation

目标：

- 确认 Memory direct edit 在 fresh legal longform session 上是否通过。

完成标准：

- fresh seed 新 session；
- Core direct edit 成功；
- 若失败，定位为当前逻辑 bug 并先修；
- 若成功，不做 legacy session repair/backfill。

### W1. Brainstorm Batch Status Truthfulness

目标：

- 修正前端状态反馈，让 UI 如实表达 brainstorm batch 的状态，而不是沿用
  historical apply receipt 心智。

完成标准：

- summarize 只显示“已生成待处理条目 / draft batch”；
- batch submit 成功只显示“已提交待处理 / pending processing”；
- `failed/conflict` 显示失败原因；
- 不再把 batch submit 显示成 memory apply success；
- 若历史 apply path 仍存在于 debug/test，只能标为 legacy，不得作为 Stage W
  产品入口。

### W2. Real Brainstorm Discussion Loop

目标：

- 恢复“有气泡、可交流”的体验，但路由到 brainstorm，而不是 writer 正文。

完成标准：

- 用户发送后有 brainstorm user bubble；
- assistant 以 brainstorm / discussion persona 回复；
- 回复不写 story segment，不改 Core；
- discussion 持久化到 branch/turn-scoped `BrainstormSession` 或等价 Runtime Workspace material；
- transcript 使用 branch-visible context。

### W3. Dedicated LLM Summarize Action

目标：

- 产品路径不再默认 `dry_run_items`。

完成标准：

- 有显式“总结为变更项”动作；
- 走真实 `brainstorm_summarize` LLM call；
- LLM 只输出 `items: list[str]`，后端固定逻辑创建 draft batch / item id /
  source/status；
- `dry_run_items` 只留给测试/debug。

### W4. Brainstorm Batch Review UI

目标：

- 用户能审查 LLM 总结条目。

完成标准：

- list items；
- edit summary text；
- delete / restore；
- add user item；
- deleted item 保留展示但绝不上传；
- 不显示或沉淀 `uncertainty` / `evidence_refs` 等讨论期不确定字段；
- active item 在 batch submit 后进入 `pending_processing`，等待 W5。

### W5. Minimal Scheduler / Worker Dispatch For Core

目标：

- `pending_processing` item 交给 Core-oriented scheduler/worker，而不是 brainstorm 自己解析字段。

完成标准：

- scheduler 只处理 frozen batch 下的 `pending_processing` active items；
- 第一版只支持 Core State maintenance；
- scheduler 选择 Core domain owner worker，不把 brainstorm item 路由成 Recall / Archival 写入；
- worker 读取 branch-aware as-of Core state；
- worker 可按工具权限通过 Retrieval Broker 召回 Recall / Archival evidence；
- worker 产出最小 field-level executable changes；
- backend 填 old_value / base revision / conflict；
- Core mutation 仍走 shared mutation kernel；
- Recall lifecycle / Archival Evolution 类诉求返回 review/redirect，不进入 Recall/Archival brainstorm edit。

建议 W0-W4 串行，W5 在 W4 完成后再做。不要一开始就做 W5，否则会重新把产品讨论链路和 memory worker 链路混在一起。

## 7. 推荐派发方式

第一批：

- 一个 implement agent 负责 `W0 + W1 + W2 + W3 + W4`，因为都属于 brainstorm product loop 和前后端接线，同一 owner 负责更安全。
- 完成后再派 `gpt-5.5 xhigh` check。

第二批：

- 另一个 implement agent 负责 `W5 Minimal Scheduler / Worker Dispatch For Core`。
- 只有在 W4 的 Brainstorm batch review contract 稳定后再开始。

不建议并行：

- W2/W3/W4 不应拆给不同 agent。
- W5 不应早于 W4。
- Legacy session repair/backfill 不应和 Stage W 并行，除非 fresh seed 验证失败。

## 8. 下一 session 不要做的事

1. 不要把 Stage V 重新说成完整 brainstorm 完成。
2. 不要为了旧手测 session 先做复杂 repair/backfill。
3. 不要把 natural language parser 加回 `StoryBrainstormService`。
4. 不要让 brainstorm 输出 memory routing fields。
5. 不要把 Recall / Archival 纳入 brainstorm direct edit。
6. 不要测试 full RP/TRPG runtime、branch merge、SuperDoc/WebView。
7. 不要主脑直接编码，除非用户明确改变规则。

## 9. 已知工作树情况

当前 worktree 很脏，包含 runtime、setup、retrieval 等多条线的未提交改动。

下一 session 必须先跑：

```powershell
git status --short
```

不要 revert 不属于当前 Stage W 的改动。

本 handoff 只新增文档，不代表其它脏改动都属于 Stage W。

## 10. 最短启动步骤

1. 确认当前 task：

```powershell
python .\.trellis\scripts\task.py current
```

2. 读本 handoff。
3. 读 `story-runtime-execution-plan.md` 的 Stage V 段落。
4. 读 `story-runtime-branch-aware-memory-product-foundation-spec.md` 的 V4 段落。
5. 先做 W0 fresh seed validation。
6. 若 W0 通过，进入 W1-W4 brainstorm product loop。
7. 模块完成后按 Trellis 流程派 `trellis-check`，不要跳 check。
