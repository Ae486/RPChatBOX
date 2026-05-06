# Story Runtime Technical Research And Pseudocode

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Date: 2026-05-05
>
> Purpose: 对可复用框架/轮子进行调研，并给出 story runtime 初步细节设计与伪代码。

## 1. 外部技术调研结论

## 1.1 Anthropic: workflow 优先于复杂 agent 框架

官方文章《Building Effective AI Agents》的要点非常贴近本项目：

- 先找最简单可行方案，再加复杂度
- workflow 适合可控、可验证的多步任务
- orchestrator-workers 适合“子任务数量和形态要看输入”的复杂任务
- routing 适合分类后走不同下游
- parallelization 适合明确可并行的子任务
- 框架可以用，但不要被框架抽象带偏；理解底层比引框架本身更重要

对本项目的直接启发：

1. story runtime 应该坚持“重 workflow，轻 agent”
2. 不该为 worker 再套新的 agent framework
3. scheduler / worker / writer / post-write 的组合，本质上是 workflow 设计问题

## 1.2 LangGraph: 适合作为 runtime 外壳，但不是 memory 分支系统

官方文档确认：

- 支持 `StateGraph`
- 支持 conditional edges
- 支持 `Send` 动态派发 worker
- 支持 subgraphs
- 支持 persistence / time travel / replay / fork

但也很明确：

- 这些能力解决的是 **graph state checkpoint**
- 不是自动替你把外部数据库、memory truth、retrieval visibility、Runtime Workspace 变成 branch-aware

对本项目的直接启发：

1. LangGraph 适合继续做 runtime 外壳
2. post-write 的 worker fan-out，如果后面确实需要并行，可用 `Send`
3. branch / rollback 只能把 LangGraph 当底座，memory/text/workspace 的隔离仍要项目自己实现
4. subgraph 可以作为后续“writer retrieval loop”或“chapter lifecycle”隔离结构的参考，但第一阶段没必要先上

## 1.3 OpenAI: handoff / routine 值得借鉴，但不适合替换当前骨架

OpenAI 官方 cookbook `Orchestrating Agents: Routines and Handoffs` 给出的重点是：

- 用显式 routine/handoff 管理多 agent 路由
- 保持主流程可控、可解释
- conversation state / background / webhooks 等能力有助于做长流程

对本项目的直接启发：

1. 可以借用“handoff/command surface 明确化”的思想
2. 但不值得为了这个切换到另一整套 agent runtime
3. 现有 LangGraph + 自己的 Memory OS / retrieval / proposal 治理链更合适

---

## 2. 轮子选择结论

## 2.1 继续用的

### A. LangGraph

用途：

- runtime graph shell
- checkpoint
- replay/fork preflight
- conditional routing
- optional `Send` fan-out

结论：

**继续用，而且作为核心 workflow 外壳。**

### B. 现有 retrieval core

用途：

- recall / archival search
- hybrid retrieval
- rerank
- observability

结论：

**继续用，不换框架。**

### C. SQLModel / SQLAlchemy 现有持久层模式

用途：

- StoryTurn / BranchHead / RuntimeProfileSnapshot / Runtime Workspace material 持久化

结论：

**继续用，不引入额外 ORM / 事件库。**

### D. Pydantic structured output

用途：

- orchestrator plan
- worker result
- brainstorm summary
- retrieval card / usage hook

结论：

**继续用，作为结构化合同主手段。**

### E. StoryLlmGateway

用途：

- 统一 provider/model 解析
- usage metadata 获取

结论：

**继续用，并在 worker / writer 上层加配置。**

## 2.2 不建议新引入的

### A. 新 agent framework

例如：

- Letta runtime 本体
- OpenAI Agents SDK 作为主 runtime
- Anthropic Agent SDK 作为主 runtime
- LlamaIndex / Haystack 作为新主 orchestrator

理由：

- 当前项目自己的 Memory OS、proposal/apply、retrieval、setup/runtime 生命周期已经很深
- 切框架会把问题从“设计 runtime”变成“迁移 runtime”
- Anthropic 官方本身也强调：复杂框架容易遮住底层 prompt / tool / workflow 行为

### B. 新 RAG 框架

理由：

- 当前 retrieval core 已经比 story runtime 更成熟
- story runtime 缺的是 runtime identity / usage / promotion，而不是 retriever 本身

---

## 3. 模块级初步细节设计

## 3.1 Runtime Identity

### 推荐数据模型

```python
class RuntimeProfileSnapshot(BaseModel):
    snapshot_id: str
    story_id: str
    mode: str
    version: int
    compiled_worker_policy: dict
    compiled_writer_policy: dict
    compiled_retrieval_policy: dict
    compiled_packet_policy: dict
    compiled_permission_profile: dict
    created_at: datetime
```

补充口径：

- `RuntimeProfileSnapshot` 是持久化实体，不是只存在于内存中的编译结果。
- turn 开始时由确定性逻辑绑定到一份已发布 snapshot。
- 运行中的 turn 不跟随 runtime 面板热更新漂移；热更新只影响后续 turn。

```python
class BranchHead(BaseModel):
    branch_head_id: str
    session_id: str
    parent_branch_head_id: str | None
    parent_turn_id: str | None
    head_turn_id: str | None
    status: str


class StoryTurn(BaseModel):
    turn_id: str
    session_id: str
    branch_head_id: str
    turn_kind: str
    command_kind: str
    profile_snapshot_id: str
    status: str
    created_at: datetime
```

### 伪代码

```python
def allocate_runtime_identity(session_id: str, command_kind: str) -> MemoryRuntimeIdentity:
    session = story_session_repo.require(session_id)
    branch = branch_repo.require_active(session_id)
    snapshot = runtime_profile_repo.require_active(session_id)
    turn = turn_repo.create(
        session_id=session.session_id,
        branch_head_id=branch.branch_head_id,
        command_kind=command_kind,
        profile_snapshot_id=snapshot.snapshot_id,
    )
    return MemoryRuntimeIdentity(
        story_id=session.story_id,
        session_id=session.session_id,
        branch_head_id=branch.branch_head_id,
        turn_id=turn.turn_id,
        runtime_profile_snapshot_id=snapshot.snapshot_id,
    )
```

补充口径：

- `Turn` 的创建、编号、身份绑定、状态推进都由确定性逻辑完成。
- LLM 不负责“决定是否新建 turn”，也不负责“本轮属于哪条 branch / 用哪个 snapshot”。
- LLM 只消费已经分配好的 runtime identity。

---

## 3.2 Scheduler / Orchestrator

### 设计要点

- LLM 输出 structured plan
- Scheduler 做 deterministic validate
- worker plan 不直接等于 worker execution

### 伪代码

```python
async def run_scheduler_phase(input_ctx: SchedulerInput) -> list[WorkerExecutionPlan]:
    descriptor_set = worker_registry.list_enabled(
        snapshot_id=input_ctx.identity.runtime_profile_snapshot_id
    )
    raw_plan = await orchestrator_worker.plan(input_ctx)
    validated = []
    for item in raw_plan.items:
        descriptor = descriptor_set.get(item.worker_id)
        if descriptor is None:
            validated.append(build_rejected_plan(item, reason="worker_not_enabled"))
            continue
        if not permission_service.allows_phase(descriptor, item.phase):
            validated.append(build_rejected_plan(item, reason="phase_not_allowed"))
            continue
        if not budget_service.allows(item, input_ctx.budget):
            validated.append(build_degraded_plan(item, reason="budget_limited"))
            continue
        validated.append(materialize_execution_plan(item, descriptor))
    return validated
```

---

## 3.3 Worker Registry / Executor

### 推荐接口

```python
class WorkerExecutor(Protocol):
    async def run(self, packet: WorkerContextPacket) -> WorkerResult: ...


class WorkerDescriptor(BaseModel):
    worker_id: str
    owned_domains: list[str]
    read_domains: list[str]
    supported_phases: list[str]
    execution_mode: str
    tool_allowlist: list[str]
    provider_model_ref: str | None
```

### 兼容执行器

第一阶段把 `LongformSpecialistService` 包成：

```python
class LongformMemoryWorkerExecutor:
    async def run(self, packet: WorkerContextPacket) -> WorkerResult:
        bundle = await longform_specialist.analyze(...)
        return adapt_specialist_bundle_to_worker_result(bundle)
```

---

## 3.4 Context Orchestration

### 设计要点

- 对 worker 和 writer 分别组包
- 不承担“决定检索与否”
- 不把 raw truth/raw hit/logs 塞给 writer

### writer packet 伪代码

```python
def build_writing_packet(input_ctx: WriterPacketInput) -> WritingPacket:
    system_sections = writer_prompt_service.render_contract(
        snapshot=input_ctx.snapshot,
        operation_mode=input_ctx.operation_mode,
    )
    context_sections = []
    context_sections += projection_slot_service.pick_writer_slots(input_ctx)
    context_sections += recent_turn_window_service.build_sections(input_ctx)
    context_sections += mode_sidecar_service.build_sections(input_ctx)
    context_sections += retrieval_card_service.build_sections(input_ctx)
    context_sections += review_overlay_service.build_sections(input_ctx)
    return WritingPacket(
        packet_id=uuid4().hex,
        session_id=input_ctx.identity.session_id,
        chapter_workspace_id=input_ctx.chapter_workspace_id,
        output_kind=input_ctx.output_kind,
        phase=input_ctx.phase,
        system_sections=system_sections,
        context_sections=context_sections,
        user_instruction=input_ctx.user_instruction,
        metadata={
            "identity": input_ctx.identity.model_dump(mode="json"),
            "operation_mode": input_ctx.operation_mode,
        },
    )
```

---

## 3.5 Writer Retrieval Loop

### 设计要点

- writer 自己判断信息不足
- 只能调用受控 retrieval 工具
- summary first, expand on demand
- final output 前必须写 usage hook

### 伪代码

```python
async def run_writer(packet: WritingPacket, tool_policy: WriterToolPolicy) -> WriterRunResult:
    attempts = 0
    cards_used = []
    expanded_cards = []
    while attempts < tool_policy.max_retrieval_attempts:
        model_output = await writer_model.step(packet)
        if model_output.kind == "tool_call" and model_output.tool_name == "retrieval.search":
            attempts += 1
            cards = await retrieval_tool.search(model_output.arguments)
            runtime_workspace.record_cards(cards)
            packet = packet_overlay_service.attach_cards(packet, cards)
            continue
        if model_output.kind == "tool_call" and model_output.tool_name == "retrieval.expand":
            expanded = await retrieval_tool.expand(model_output.arguments["card_id"])
            runtime_workspace.record_expanded_chunk(expanded)
            expanded_cards.append(expanded.short_id)
            packet = packet_overlay_service.attach_expanded(packet, expanded)
            continue
        if model_output.kind == "final_text":
            cards_used = usage_extractor.extract_used_cards(model_output)
            runtime_workspace.record_usage(
                used_cards=cards_used,
                expanded_cards=expanded_cards,
            )
            return WriterRunResult(
                text=model_output.text,
                used_cards=cards_used,
                expanded_cards=expanded_cards,
            )
    raise WriterLoopError("writer_retrieval_attempt_limit_exceeded")
```

---

## 3.6 Runtime Workspace Persistence

### 推荐实现

不要继续用 in-process store。

推荐直接新增持久化表：

```python
class RuntimeWorkspaceMaterialRecord(SQLModel, table=True):
    material_id: str = Field(primary_key=True)
    story_id: str
    session_id: str
    branch_head_id: str
    turn_id: str
    profile_snapshot_id: str
    material_kind: str
    domain: str
    short_id: str | None = None
    lifecycle: str
    visibility: str
    payload_json: dict
    metadata_json: dict
    created_by: str
    created_at: datetime


class RuntimeWorkspaceEventRecord(SQLModel, table=True):
    event_id: str = Field(primary_key=True)
    story_id: str
    session_id: str
    branch_head_id: str
    turn_id: str
    event_kind: str
    payload_json: dict
    created_at: datetime
```

### 保留策略

- raw card / expanded chunk：调度完成后可过期
- usage / trace / refs：长期保留
- pending worker candidate：直到 apply / invalidate / rollback

---

## 3.7 Post-write Maintenance

### 设计要点

- writer 输出后先落最小日志
- 再按触发条件决定是否做完整调度
- 完整调度内先刷新 view，再做重沉淀

### 伪代码

```python
async def handle_post_write(turn: StoryTurn, writer_result: WriterRunResult) -> None:
    runtime_workspace.record_writer_output(turn, writer_result)
    runtime_workspace.record_token_usage(turn, writer_result.usage)

    if not post_write_trigger_service.should_run_full_maintenance(turn):
        pending_service.mark_pending(turn.turn_id, reason="frequency_gate")
        return

    plans = await scheduler.plan_post_write(turn)
    results = await worker_runner.run_all(plans)

    projection_requests = collect_projection_requests(results)
    proposal_candidates = collect_proposal_candidates(results)
    recall_candidates = collect_recall_candidates(results)
    archival_candidates = collect_archival_candidates(results)

    projection_refresh_dispatch.refresh_first(turn.identity, projection_requests)
    proposal_dispatch.submit_governed(turn.identity, proposal_candidates)
    recall_dispatch.materialize(turn.identity, recall_candidates)
    archival_dispatch.ingest(turn.identity, archival_candidates)
```

---

## 3.8 Longform Brainstorm / Review

### 设计要点

- brainstorm 不直接改 block
- 只产出 summary items
- user edit / reject / apply
- apply 后交调度器

### 伪代码

```python
async def run_longform_brainstorm(input_text: str, context: BrainstormContext) -> BrainstormSummary:
    summary = await brainstorm_writer.summarize(
        input_text=input_text,
        context=context,
    )
    return normalize_summary_items(summary)


async def apply_brainstorm_summary(
    identity: MemoryRuntimeIdentity,
    items: list[BrainstormItem],
) -> ApplySummaryResult:
    confirmed = [item for item in items if not item.rejected]
    if not confirmed:
        return ApplySummaryResult(status="noop")
    plans = await scheduler.plan_summary_apply(identity=identity, items=confirmed)
    results = await worker_runner.run_all(plans)
    projection_refresh_dispatch.refresh_first(identity, collect_projection_requests(results))
    proposal_dispatch.submit_governed(identity, collect_proposal_candidates(results))
    return ApplySummaryResult(status="applied")
```

---

## 4. 推荐的现成轮子与直接复用点

| 目标 | 直接复用 | 不建议 |
|---|---|---|
| runtime graph | LangGraph `StateGraph` / conditional edges / persistence | 切到新 agent framework |
| dynamic worker dispatch | LangGraph `Send`，但只在确实需要 fan-out 时用 | 一开始就全面并行化 |
| structured contracts | Pydantic models | 自由文本解析 |
| model/provider routing | `StoryLlmGateway` + existing registries | 新建独立 provider stack |
| governed memory writes | `ProposalWorkflowService` / `ProposalApplyService` | 让 worker 直接写库 |
| retrieval | 当前 `RetrievalBroker` / `RetrievalService` | 引新 RAG 框架替代 |
| debug/trace | 现有 runtime debug + retrieval observability + memory inspection | 重造 observability 平台 |

---

## 5. 当前设计下的关键技术判断

1. **LangGraph 是合适外壳，但不是 memory branch 系统**
2. **当前 retrieval core 足够强，不该重写**
3. **Runtime Workspace 持久化是前置切片，不是优化项**
4. **新 runtime 的关键不是 prompt，而是 contract + identity + scheduler + workspace**
5. **worker 的重点是“治理 memory”，不是“生成很多文字”**

---

## 6. Research Sources

- Anthropic, *Building Effective AI Agents*  
  https://www.anthropic.com/research/building-effective-agents

- LangGraph official docs, *Workflows and agents*  
  https://docs.langchain.com/oss/python/langgraph/workflows-agents

- LangGraph official docs, *Use time-travel*  
  https://docs.langchain.com/oss/javascript/langgraph/use-time-travel

- LangGraph official docs, *Subgraphs*  
  https://docs.langchain.com/oss/python/langgraph/use-subgraphs

- OpenAI Cookbook, *Orchestrating Agents: Routines and Handoffs*  
  https://developers.openai.com/cookbook/examples/orchestrating_agents
