# Story Runtime Product Acceptance Manual QA

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Module: Phase Q / Runtime Product Acceptance / User-facing Integration Gate
>
> Phase S addendum: Product Wiring / Writer Constraint Closure

## Phase S 复测清单

这段是当前 S3 人工复测的主清单。下面保留的 Phase Q 英文清单只作为历史追溯；Q 的结论已经被修正为“后端 foundation acceptance”，不能再代表产品路径通过。

复测目标只有三个：

1. 确认前端 Longform 页面已经能打开 `运行态` 面板。
2. 确认带批注/修订的 rewrite 会把约束传给 writer。
3. 确认 `Accept & Continue` 后的下一段会收到“上一段承接 + 章节进度”约束；如果模型仍然乱写，运行态面板能看出是模型没遵循，还是系统没传约束。

### 复测前准备

1. 启动后端和前端，打开一个 longform story session。
2. 保留一个当前章节，能正常生成一段草稿。
3. 打开页面上的 `运行态` 入口，确认底部面板能打开。
4. 记录本次测试的 `session_id`、当前章节、当前分支、当前 turn。

### 1. 检查运行态入口

操作：

1. 在 Longform 页面点击 `运行态`。
2. 等待底部面板加载完成。

预期看到：

1. 面板能打开，不白屏，不报错。
2. 能看到当前模式、活动分支、选中 turn、活动 snapshot。
3. 能看到 writer packet、review overlay、chapter bridge、job ledger、retrieval、mode sidecar 等区块。
4. 暂时没有数据的区块显示“不可用/暂无”，而不是直接消失或崩溃。

如果失败：

- 没入口：前端可达性问题。
- 有入口但打开报错：前端读取/解析问题。
- 有入口但完全看不到 writer/review/chapter 信息：inspect 映射或展示问题。

### 2. 生成一段初始草稿

操作：

1. 点击生成/续写，让 writer 产出一段待采用草稿。
2. 不要直接当成正文，先保留为 candidate/draft。
3. 打开 `运行态` 面板刷新查看。

预期看到：

1. 页面上能看到草稿或候选。
2. 候选选择只是预览，不应该被描述成“已经成为正文”。
3. `运行态` 里能看到本轮 writer packet / turn / artifact 相关信息。

如果失败：

- 看不到草稿：写作主链或前端展示问题。
- 一选择候选就被当正文：adoption 语义错误。
- 运行态里没有 writer packet：inspect 证据链问题。

### 3. 添加批注/修订并 rewrite

操作：

1. 在草稿上添加一个明确批注，例如：`把“黑曜石”改成“白银钥匙”，并加强 Taki 的动作和情绪。`
2. 如果 UI 支持 tracked change，再添加一个词语替换类修订。
3. 点击 rewrite。
4. rewrite 完成后打开 `运行态` 面板。

预期看到：

1. rewrite 产出的是新候选，不会自动变成正文。
2. `运行态` 的 review overlay / writer packet 区块能看到这条批注或等价摘要。
3. writer packet metadata 能体现 rewrite / target artifact / review overlay section count 等信息。
4. 如果 writer 输出没完全遵循批注，至少运行态证据能证明“约束已经传给 writer”。

如果失败：

- rewrite 完全没有带批注证据：S1 后端约束注入问题。
- 批注存在但 writer 输出没听：模型遵循问题或 prompt 强度问题。
- rewrite 后直接覆盖正文：candidate/adoption 语义问题。

### 4. Accept & Continue

操作：

1. 在多个候选中选择一个你认可的候选。
2. 点击 `Accept & Continue`。
3. 再生成下一段。
4. 打开 `运行态` 面板。

预期看到：

1. 只有点击 `Accept & Continue` 后，候选才成为后续续写基础。
2. 下一段应该接在刚采用的候选之后，不应该跳回大纲前面的部分。
3. `运行态` 里能看到 chapter progress / continuity 信息，例如已采用段落数量、上一段摘录、章节目标、outline 摘要或承接指令。
4. 如果模型仍写偏，运行态证据能区分：是系统没给承接信息，还是模型没遵循承接信息。

如果失败：

- 下一段使用了未采用候选：adoption/selection 语义问题。
- 下一段跳回旧大纲且运行态缺少 chapter progress：S1 continuity packet 问题。
- 运行态有 chapter progress 但输出仍跳：模型遵循问题，需要后续 prompt/约束强化，不是产品入口缺失。

### 5. 最小通过标准

本轮 S3 通过必须同时满足：

1. Longform 页面能打开 `运行态` 面板。
2. rewrite 的运行态证据能看到 review overlay / 批注约束进入 writer packet。
3. `Accept & Continue` 后的下一次 write 能在运行态证据里看到 chapter progress / continuity 约束。
4. 候选选择和采用语义清楚：选择只是预览，`Accept & Continue` 才改变后续正文基础。
5. 若输出质量仍差，至少能通过运行态证据定位为“模型不遵循”还是“系统没传约束”。

## Phase Q Historical Checklist

## Goal

Manually verify the current longform runtime product path after Q1 automated
backend acceptance passes. This checklist is an acceptance handoff, not a new
feature plan.

It uses only existing surfaces:

- longform story session UI or the existing story turn API;
- `POST /api/rp/story-sessions/{session_id}/turn` with existing command kinds;
- `PATCH /api/rp/story-sessions/{session_id}/runtime-config`;
- `GET /api/rp/story-sessions/{session_id}/runtime/inspect`.

It must not require a new debug panel, a second debug truth store, a new public
mutation command, SuperDoc/WebView, branch UI expansion, active RP/TRPG runtime,
or an eval runner.

## Preconditions

1. Q1 backend acceptance passed:
   `pytest backend/rp/tests/test_story_runtime_product_acceptance.py -q`.
2. A longform story session exists with an active branch head and active runtime
   profile snapshot.
3. The current review surface can expose pending draft/candidate state, or the
   same flow can be driven through the existing `/turn` command route.
4. The inspect route is reachable:
   `GET /api/rp/story-sessions/{session_id}/runtime/inspect`.

Record these identifiers before the run:

| Field | Value |
|---|---|
| `session_id` | |
| active `branch_head_id` | |
| starting `turn_id` | |
| active `runtime_profile_snapshot_id` | |
| tester | |
| date | |

## Pass/Fail Classification

When a step fails, classify it as exactly one primary class:

| Class | Meaning |
|---|---|
| route gap | Existing backend service exists but no current route reaches it |
| contract gap | Existing route/service returns data that violates Q spec |
| UI reachability gap | Backend route works but current product surface cannot expose or invoke it |
| manual-only limitation | Behavior is acceptable but cannot be automated with current test harness |
| out-of-scope request | Failure would require SuperDoc/WebView, branch UI, debug panel, new command semantics, or eval runner |

## Checklist

### 1. Open Longform Runtime Session

Action:

- Open the existing longform story session in the product surface, or fetch the
  session through the existing story session API.
- Identify the active branch head, current turn, and active runtime profile
  snapshot.
- Call inspect:
  `GET /api/rp/story-sessions/{session_id}/runtime/inspect`.

Expected product evidence:

- The session opens on the active story state without falling back to old MVP
  truth.
- Active branch/head/profile identity is visible in the route response or in
  linked session data.

Expected inspect evidence:

- `selection.selected_branch_head_id` matches the active branch.
- `selection.selected_turn_id` is absent only before the first runtime turn; once
  a turn is selected it must match the product-visible turn.
- `runtime_profile_snapshot.runtime_profile_snapshot_id` matches the pinned
  snapshot used by the flow.
- `read_only` is `true`.

Result:

| pass/fail | observed route/command | evidence refs | classification |
|---|---|---|---|
| | | | |

### 2. Write Next Segment

Action:

- Trigger the existing write flow:
  `command_kind = write_next_segment`.
- API equivalent:
  `POST /api/rp/story-sessions/{session_id}/turn`.
- Wait for writer output and draft artifact creation.

Expected product evidence:

- A draft `story_segment` appears.
- Writer output is visible as draft text, not accepted story truth.
- The writer packet summary and runtime usage metadata are retained for debug
  readback.

Expected inspect evidence:

- `writer_packet` contains packet identity and read manifest refs for the turn.
- `writer_packet` / runtime inspect can identify the current beat and covered beat count for this write.
- `runtime_workspace.materials` includes packet/evidence or usage materials for
  the same branch/turn identity.
- Source refs point back to the writer packet/materials rather than raw private
  payload fields.

Result:

| pass/fail | observed route/command | evidence refs | classification |
|---|---|---|---|
| | | | |

### 3. Review Overlay And Rewrite

Action:

- Use the existing review surface to enter suggesting/review mode.
- Add one comment and one tracked change.
- Trigger the existing rewrite flow:
  `command_kind = rewrite_pending_segment`.
- API equivalent:
  `POST /api/rp/story-sessions/{session_id}/turn`.

Expected product evidence:

- Comment and tracked change are preserved as review overlay data.
- Rewrite request carries overlay references into writer-visible structured
  fields.
- Rewrite candidate is visible as a candidate/draft and is not adopted
  automatically.

Expected inspect evidence:

- Review overlay material remains Runtime Workspace sidecar/evidence.
- Candidate refs and overlay refs preserve full runtime identity.
- Canonical continuation base is unchanged before adoption.

Result:

| pass/fail | observed route/command | evidence refs | classification |
|---|---|---|---|
| | | | |

### 4. Select, Adopt, And Continue

Action:

- If multiple candidates exist, select the desired candidate through the current
  candidate selector.
- Trigger existing Accept & Continue semantics:
  `command_kind = accept_pending_segment`.
- Do not use or add a public `accept_and_continue` command name. In Q,
  `accept_and_continue` is only the semantic acceptance label for the existing
  `accept_pending_segment` / Accept & Continue flow.
- Trigger a later `write_next_segment` to confirm continuation base.

Expected product evidence:

- Selection is reversible and does not itself become adoption.
- Adoption is explicit.
- The next write uses the adopted candidate, not an unadopted selected or visible
  candidate.
- The next write targets the next pending beat instead of reusing the already
  covered beat.

Expected inspect evidence:

- Adoption receipt or equivalent Runtime Workspace evidence identifies the
  selected candidate and continuation source.
- Source refs include the selected/adopted candidate and any selection receipt.
- Beat progress shows the adopted beat as covered only after
  `accept_pending_segment` / Accept & Continue.
- No new public mutation command appears in logs, routes, or docs.

Result:

| pass/fail | observed route/command | evidence refs | classification |
|---|---|---|---|
| | | | |

### 5. Complete Chapter And Start Next Chapter

Action:

- Trigger the existing chapter completion flow:
  `command_kind = complete_chapter`.
- Start or inspect the next chapter packet for target chapter `N + 1`.

Expected product evidence:

- Chapter completion consumes adopted draft, accepted outline, and chapter goal.
- Pending rewrite candidates without adoption do not become canonical truth.
- The next chapter can read the active-branch bridge.
- The bridge summary is treated as next-chapter sidecar material, not visible
  chapter prose or Core/Recall truth.

Expected inspect evidence:

- `chapter_bridge.latest_for_target_chapter` exists for the active branch and
  target chapter.
- `chapter_progress.latest_for_chapter` shows the covered beats that fed the
  chapter-close summary.
- Bridge `source_refs` point to adopted output/adoption receipt/accepted chapter
  material.
- Sibling branch bridge material is absent from the active branch read.

Result:

| pass/fail | observed route/command | evidence refs | classification |
|---|---|---|---|
| | | | |

### 6. Apply Runtime Config Patch

Action:

- Patch a future-turn-only runtime setting, for example packet budget:
  `PATCH /api/rp/story-sessions/{session_id}/runtime-config`.
- Record previous and published snapshot ids from the response/control history.
- Start a later turn after the patch.

Expected product evidence:

- A new immutable `RuntimeProfileSnapshot` is published.
- Existing in-progress or already-started turn/job keeps its pinned snapshot.
- Future turns use the new active snapshot.
- Story rollback, if run through existing controls, does not revert runtime
  config control history.

Expected inspect evidence:

- `runtime_config.control_history` includes previous and published snapshot ids.
- Selected turn identity still reports its originally pinned snapshot.
- Later turn identity reports the published snapshot.

Result:

| pass/fail | observed route/command | evidence refs | classification |
|---|---|---|---|
| | | | |

### 7. Story Evolution Visibility

Action:

- Use an existing governed Archival Story Evolution path, if exposed in the
  current environment, to evolve a current-branch archival item.
- If product UI does not expose this path, rely on Q1 automation and manually
  inspect the existing debug/read route evidence for a seeded evolution item.

Expected product evidence:

- Evolution creates version/supersession/reindex evidence.
- Default visibility is current branch.
- Hidden or superseded evolved chunks are not returned by retrieval.

Expected inspect evidence:

- `story_evolution.items` includes evolution id, source refs, visibility, and
  reindex/memory-event evidence where applicable.
- Inspect output exposes this evidence as debug/read metadata, not as story truth.

Result:

| pass/fail | observed route/command | evidence refs | classification |
|---|---|---|---|
| | | | |

### 8. Mode Sidecar Isolation

Action:

- Inspect a packet/turn where no explicit sidecar slot was requested.
- If a TRPG/rule-card seed exists, inspect it through existing runtime debug/read
  surfaces only. Do not start active RP/TRPG runtime behavior for Q.

Expected product evidence:

- Rule cards and rule state cards remain Runtime Workspace sidecars.
- A packet without explicit `context_requirements.sidecar_slot_ids` has empty
  `sidecar_refs`.
- Generic `workspace_refs` do not include rule sidecars.

Expected inspect evidence:

- `mode_sidecars.materials` carry formal `source_refs`.
- Sidecar classification uses stable fields such as `section_family`,
  `source_kind`, or `section_id`, not human labels or private payload spelunking.
- Rule-card material is not visible as Core, Recall, or Archival truth.

Result:

| pass/fail | observed route/command | evidence refs | classification |
|---|---|---|---|
| | | | |

### 9. Runtime Inspect Read Surface

Action:

- Call:
  `GET /api/rp/story-sessions/{session_id}/runtime/inspect`.
- Include `turn_id`, `branch_head_id`, and `target_chapter_index` when available
  to force exact-identity or explicit branch-scoped reads.

Expected product evidence:

- One bundle can explain the current flow without private payload spelunking.
- The route is read-only and does not create new truth.

Expected inspect evidence:

- Bundle includes applicable runtime config, story evolution, chapter bridge,
  mode sidecars, writer packet summary, read manifests, Runtime Workspace
  materials, branch/head/turn/profile identity, and boundaries.
- `read_only` is `true`.
- `boundaries` includes read-only/debug and sidecar-source-ref constraints.

Result:

| pass/fail | observed route/command | evidence refs | classification |
|---|---|---|---|
| | | | |

### 10. Branch-Visible Read Behavior

Action:

- If existing branch controls are exposed, switch or inspect branch-visible reads
  through those controls.
- Otherwise, call inspect with explicit `branch_head_id`/`turn_id` parameters for
  available active and sibling branch fixtures.

Expected product evidence:

- Sibling branch pending revision, chapter bridge material, sidecar material, and
  evolved chunks do not leak into the active branch.
- Unknown or cross-story branch ids fail closed.

Expected inspect evidence:

- Exact-identity or branch-scoped filtering controls all returned materials.
- A branch/turn mismatch returns an error rather than best-effort mixed evidence.

Result:

| pass/fail | observed route/command | evidence refs | classification |
|---|---|---|---|
| | | | |

## Final Manual QA Summary

| Area | Pass/Fail | Evidence refs | Notes |
|---|---|---|---|
| Longform write/review/rewrite/adopt/continue | | | |
| Chapter completion / next chapter bridge / beat progress | | | |
| Runtime config hot update / snapshot pin | | | |
| Story Evolution visibility / retrieval exclusion | | | |
| Mode sidecar / rule card isolation | | | |
| Inspect route read-only debug bundle | | | |
| Branch-visible read isolation | | | |

## Escalation Rule

Escalate a grill question only when the mismatch cannot be resolved from the Q
spec, development spec, execution plan, or existing route/service contracts.
Do not invent new Q semantics during manual QA.
