# Story Runtime Branch / Rollback Productization Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Module: Branch / Rollback
>
> Stage: productization closure after Phase T
>
> Status: draft-v1

## 1. Scope

本规格书只负责把既有 Branch / Rollback 后端能力变成用户可达、可验证的产品路径：

- longform 页面显示当前 active branch；
- 历史正文段落提供 `从这里分支` 和 `回退到这里` 两个明确动作；
- branch 面板提供最小 branch 查看 / 切换 / 删除能力；
- branch create 后立即切换 active branch，并刷新当前线性正文；
- rollback 后当前 active branch 只显示 rollback 目标及之前的可见历史；
- 前端能看到 fork 点、origin branch、branch control receipt 摘要；
- API / frontend / inspect / tests 对齐同一套应用层 truth。

本规格书不负责：

- 旧 session / 老 outline / 老 artifact 兼容迁移；
- 完整树状消息流、分支对比、branch merge；
- physical purge；
- LangGraph fork/replay 产品入口；
- 跨分支 Story Evolution 自动传播；
- roleplay / TRPG active runtime；
- eval runner / grader。

## 2. Evidence

### 2.1 Existing task docs

- `prd.md:451-459` 已冻结 rollback 与 branch 的区别：rollback 后目标 turn 之后内容对当前主线失效；如果要保留旧未来，那是 branch；branch control actions 不创建 story turn。
- `prd.md:524-528` 已冻结第一版 branch UX：active branch 线性展示、`从这里分支` 入口、最小 branch 面板、创建后立即切换、fork 后旧未来从主视图消失、pending/workspace 不跨 branch。
- `story-runtime-branch-rollback-spec.md:41-74` 已冻结 rollback / branch 产品语义和统一锚点：rollback 只认 `Turn`，branch create 只从 `settled turn` 派生。
- `story-runtime-branch-rollback-spec.md:297-339` 已冻结最小前端约束：主聊天区只显示 active branch 线性历史；动作必须区分 `回退到这里` 和 `从这里分支`，禁止模糊的“从这里继续”。
- `story-runtime-branch-rollback-spec.md:428-439` 已列出测试点：branch create 立即 switch、不创建 turn、fork 前共享 truth、fork 后 pending/workspace 隔离、rollback 不污染 writer packet / inspect。
- `story-runtime-langgraph-branch-rollback-preflight.md:13-18` 已明确 LangGraph 是执行壳，不是产品 branch / rollback truth。
- `story-runtime-langgraph-branch-rollback-preflight.md:93-122` 已明确第一阶段可承诺与不能承诺：应用层 `StorySession / BranchHead / Turn / RuntimeProfileSnapshot` 是 truth；checkpoint 只是技术锚点；不做 physical purge、merge、跨分支 evolution。
- `prd.md:766-767` 提到的 physical deletion 是后续最终清理能力；当前 productization closure 只承诺 visibility-first hide / status transition，不把 purge 纳入实现、验收或 QA。
- `story-runtime-execution-plan.md:840-864` 已记录 R/J/K/L/M/N/O/P/Q/S/T 完成，T 后应进入新的产品验收或下一 FIFO 阶段。

### 2.2 Existing code facts

- `StoryRuntimeIdentityService.create_branch_from_turn(...)` 已能从 settled turn 创建新 branch，并立即更新 `StorySession.active_branch_head_id`。
- `StoryRuntimeIdentityService.switch_branch(...)` / `delete_branch(...)` 已有服务级能力，并写 branch control receipt。
- `StoryRuntimeIdentityService.rollback_to_turn(...)` 已要求目标 turn settled、属于当前 active branch、不创建 story turn、隐藏 later turns、invalidate later Runtime Workspace materials、写 rollback receipt。
- `BranchVisibilityResolver` 与 `StorySessionService` 已有 active branch visibility / rollback hidden turn 过滤基础。
- `backend/api/rp_story.py` 当前只暴露 `/runtime/inspect`、`/runtime/debug`、`/turn`、revision review 等路径；没有用户可调用的 branch create/switch/delete/rollback route。
- `BackendStoryService` 当前只封装了 session、runtime config、runtime inspect、revision review 和 turn stream；没有 branch mutation client methods。
- `LongformStoryPage` 当前有 runtime inspect 只读入口；`StoryRuntimeInspectionSheet` 明确只展示 receipt 摘要，不实现 branch 操作面板。

### 2.3 Framework / wheel research

- LangGraph 官方 time-travel / persistence 能 replay 和 fork graph checkpoint；`update_state` 会从旧 checkpoint 创建新 checkpoint，不修改原历史。该能力适合作为 debug / graph shell 技术锚点，不可替代 RP 外部 Memory OS / Runtime Workspace / retrieval visibility 的应用层真相。
- OpenAI Structured Outputs 与 Anthropic structured outputs / strict tool use 都支持 JSON Schema 约束。它们适合用于 LLM 输出合同，例如 future branch summary；本阶段 branch/rollback 是 deterministic product action，不应引入 LLM。
- `badlogic/pi-mono` 只作为外部 UX 参考：可借鉴其“线性当前分支 + 显式 fork/switch + fork 保留历史”的轻量产品手感；本阶段不引入依赖、不复制 JSONL tree/store，也不实现完整树状 UI。

## 3. Product Contract

### 3.1 Branch indicator

Longform 页面顶部必须显示当前 active branch 的可读标识：

- branch name；
- branch short id；
- fork origin / fork base 摘要，如果存在；
- 当前页面只显示 active branch 的线性正文。

如果当前 session 只有默认 branch，也应显示轻量标识，避免用户误以为 branch 能力不可用。

### 3.2 Turn-level actions

每个已 settled 且当前 visible 的正文段落 / turn 操作区提供：

- `从这里分支`
- `回退到这里`

动作约束：

- 二者不能合并为“从这里继续”；
- 对 pending / draft / rewrite candidate 不提供 branch / rollback 锚点；
- 对 rollback hidden 的 turn 不提供入口；
- 对非当前 active branch 的 turn，不能执行 rollback；
- branch create 只允许 settled turn；
- rollback 只允许当前 active branch 的 settled turn。

### 3.3 Branch panel

第一版 branch panel 是列表，不是树状图。必须展示：

- branch name；
- branch id short label；
- 是否 current；
- status / visibility；
- origin branch；
- fork origin turn；
- fork base turn；
- head turn；
- latest branch control receipt 摘要。

第一版动作：

- switch to branch；
- delete branch；
- close panel / refresh。

删除约束：

- 默认 branch 不可删除；
- current active branch 不可删除，除非后续规格明确 fallback 规则；
- delete 是 hide / status transition，不能 physical purge shared truth。

### 3.4 Branch create UX

用户点击 `从这里分支` 后：

1. 前端调用 branch create API；
2. 后端从 settled turn 派生 branch，只创建 branch head / receipt，不复制整套 memory；
3. 后端立即切换 `StorySession.active_branch_head_id`；
4. 返回最新 chapter snapshot 和 branch control receipt；
5. 前端刷新当前线性正文；
6. fork 点之后旧 branch 的未来内容不再显示在主正文；
7. 页面顶部 branch indicator 更新为新 branch；
8. fork 点附近显示轻量提示。

### 3.5 Rollback UX

用户点击 `回退到这里` 后：

1. 前端显示确认文案，说明目标 turn 之后内容会从当前主线隐藏，但不是物理删除；
2. 后端执行 rollback visibility transition，不创建新 turn；
3. 后端返回最新 chapter snapshot 和 rollback receipt；
4. 前端刷新当前线性正文；
5. 后续 write/rewrite packet 不得读到 rollback hidden future materials；
6. inspect 面板能看到 rollback receipt 和 hidden/cutoff 证据。

### 3.6 Snapshot / truth ownership

Branch / rollback 产品路径的 canonical truth 是：

```text
StorySession.active_branch_head_id
BranchHeadRecord
StoryTurnRecord
BranchControlReceiptRecord
RuntimeWorkspaceMaterialRecord lifecycle / visibility
BranchVisibilityResolver read scope
```

LangGraph checkpoint pointer 只能作为 settled turn 的 graph shell technical anchor。任何 UI、API、writer packet、inspect 判断都不能把 LangGraph checkpoint 当作 branch truth。

## 4. API Contract

新增 product route 建议落在 `backend/api/rp_story.py`，委托 `StoryRuntimeController` 或一个 thin controller facade 调用既有 `StoryRuntimeIdentityService`。

### 4.1 Create branch

```http
POST /api/rp/story-sessions/{session_id}/branches
```

Request:

```json
{
  "origin_turn_id": "turn:...",
  "branch_name": "alternate future"
}
```

Response:

```json
{
  "data": { "chapter_snapshot": "RpChapterSnapshot json" },
  "receipt": { "BranchControlReceipt json" }
}
```

### 4.2 Switch branch

```http
POST /api/rp/story-sessions/{session_id}/branches/{branch_head_id}/switch
```

Response contract 同 create branch。

### 4.3 Delete branch

```http
DELETE /api/rp/story-sessions/{session_id}/branches/{branch_head_id}
```

Response contract 同 create branch。

### 4.4 Rollback

```http
POST /api/rp/story-sessions/{session_id}/rollback
```

Request:

```json
{
  "target_turn_id": "turn:..."
}
```

Response contract 同 create branch。

### 4.5 Error contract

API must preserve stable backend error codes where possible:

- `runtime_branch_control_invalid_turn`
- `runtime_branch_head_not_found`
- `runtime_identity_resolution_failed`
- `story_session_not_found`

Frontend should render concise user-facing error text and keep current snapshot unchanged on failure.

## 5. Frontend Contract

### 5.1 Service methods

`BackendStoryService` must add methods:

- `createBranchFromTurn(...)`
- `switchBranch(...)`
- `deleteBranch(...)`
- `rollbackToTurn(...)`

They should return one typed envelope containing:

- `RpChapterSnapshot snapshot`
- `Map<String, dynamic> receipt`

### 5.2 Longform page changes

`LongformStoryPage` owns product entry because first target is longform writing flow.

Required UI:

- branch indicator in header；
- branch panel button；
- branch list bottom sheet / side sheet；
- per-segment action menu；
- rollback confirmation；
- success/error snackbar；
- refresh snapshot after every control action。

Do not add:

- complex graph/tree visualization；
- diff / compare view；
- branch merge；
- branch replay from LangGraph；
- debug-only controls pretending to be product controls。

### 5.3 Inspect relation

Runtime inspect remains read-only evidence surface. Product branch actions must not be hidden inside inspect.

Inspect can be used after action to verify:

- active branch id；
- selected turn；
- branch read scope；
- branch control receipts；
- hidden rollback future materials；
- graph checkpoint summary, if available。

## 6. Validation

### 6.1 Backend tests

Required focused tests:

1. create branch route:
   - accepts settled visible turn；
   - writes `branch_created` receipt；
   - immediately updates active branch；
   - does not create story turn；
   - returned snapshot is new active branch linear view。
2. switch branch route:
   - writes `branch_switched` receipt；
   - does not create story turn；
   - returned snapshot uses selected branch。
3. delete branch route:
   - rejects default branch；
   - rejects current branch for first version；
   - hide/status transition does not delete shared truth。
4. rollback route:
   - accepts only current active branch settled turn；
   - writes `rollback_applied` receipt；
   - does not create story turn；
   - hides later turns and invalidates later workspace material；
   - returned snapshot excludes hidden future；
   - inspect / writer packet remain clean after rollback。

### 6.2 Frontend checks

Required scoped checks:

- branch indicator visible；
- branch panel visible and refreshable；
- current branch switch updates visible chapter content；
- create branch from visible segment switches immediately；
- rollback confirmation appears and refreshes visible content；
- inspect remains read-only。

### 6.3 Manual QA scope

Manual QA must only verify implemented product paths:

- branch indicator；
- branch panel；
- create branch from one visible settled segment；
- switch back to origin branch；
- rollback current branch to an earlier visible segment；
- write after rollback and verify hidden future does not influence continuation。

Manual QA must not assert:

- old session migration；
- complex tree view；
- branch compare / merge；
- LangGraph replay/fork as product action；
- full RP/TRPG mode runtime。

## 7. Grill Status

当前无需 grill。理由：

- branch / rollback 的产品语义、锚点、前端最小约束、测试点在既有 task docs 中已经明确；
- 后端服务级能力已经存在，缺口是 product API + frontend product entry；
- 外部框架调研没有推翻现有分层，反而支持继续采用 application truth + graph shell 的架构。

如果实现中发现以下问题，再进入 grill：

- 现有 chapter snapshot 无法表达 active branch 线性正文；
- delete current branch 是否需要自动切 fallback branch；
- branch panel 是否必须显示多层 fork lineage，而不仅是 origin / fork base；
- write after branch create 是否需要显式提示用户当前仍在新 branch。
