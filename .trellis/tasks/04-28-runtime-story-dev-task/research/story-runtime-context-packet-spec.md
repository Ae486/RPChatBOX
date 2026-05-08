# Story Runtime Context / Packet Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Module: Context Orchestration / Packet
>
> Status: draft-v1

## 1. 范围

本规格书负责冻结：

- `WritingPacket`
- `WorkerContextPacket`
- Context Orchestration Layer 的组包职责
- packet 允许/禁止进入内容
- token budget / usage metadata 的使用边界

这份文档不负责：

- scheduler 如何选择 worker
- writer 如何生成正文
- retrieval card 的生成算法
- post-write 的治理判断

## 2. 设计目标

这一层要解决 5 个问题：

1. writer 为什么不能拿全量上下文
2. worker packet 和 writer packet 为什么必须分开
3. 哪些内容能进 writer packet，哪些绝对不能进
4. 如何让 token 裁剪和实际 usage 统计不混线
5. 如何在后续 mode 扩展时不改 packet 主骨架

## 3. 当前实现判断

当前后端：

- `writing_packet_builder.py`
  - 已有 deterministic builder 雏形
  - 但仍是 MVP packet 形态

- `writing_runtime.py`
  - 当前 `WritingPacket` 模型太薄
  - 需要升级为 story runtime writer packet contract

- `story_turn_domain_service.py`
  - 当前已把 packet build 和 runtime retrieval section 接起来
  - 可作为迁移入口参考

结论：

- 现有 builder 和 packet 可作为实现素材
- 但规格书必须先把新 packet 合同冻结，再决定 adapter 还是重写

## 4. 文件落位建议

## 4.1 复用现有文件

- `backend/rp/models/writing_runtime.py`
- `backend/rp/services/writing_packet_builder.py`
- `backend/rp/services/runtime_read_manifest_service.py`

## 4.2 新增文件建议

- `backend/rp/models/context_packet_contracts.py`
- `backend/rp/services/context_orchestration_service.py`
- `backend/rp/services/worker_context_packet_service.py`

说明：

- `writing_packet_builder.py` 可继续保留，但后续更像 `WritingPacketBuilderAdapter`
- 真正的 packet 组装规则应上提到 `ContextOrchestrationService`

## 5. 核心对象

## 5.1 WritingPacket

建议字段：

- `packet_id: str`
- `identity: MemoryRuntimeIdentity`
- `session_id: str`
- `branch_head_id: str`
- `turn_id: str`
- `chapter_workspace_id: str | None`
- `output_kind: str`
- `phase: str`
- `operation_mode: str`
  - `writing`
  - `rewrite`
  - `discussion`

- `system_sections: list[str]`
- `core_view_sections: list[PacketSection]`
- `recent_raw_turn_sections: list[PacketSection]`
- `mode_sidecar_sections: list[PacketSection]`
- `retrieval_card_sections: list[PacketSection]`
- `review_overlay_sections: list[PacketSection]`
- `user_instruction: str`
- `writer_contract: dict`
- `packet_summary_metadata: dict`
- `trace_refs: list[str]`

### PacketSection

建议字段：

- `section_id: str`
- `label: str`
- `source_kind: str`
- `source_ref_ids: list[str]`
- `items: list[str]`
- `metadata_json: dict`

## 5.2 WorkerContextPacket

worker packet 不与 writer packet 混用。

建议字段：

- `packet_id: str`
- `identity: MemoryRuntimeIdentity`
- `worker_id: str`
- `phase: str`
- `mode: str`
- `session_refs: list[str]`
- `recent_turn_refs: list[str]`
- `core_projection_refs: list[str]`
- `sidecar_refs: list[str]`
- `retrieval_refs: list[str]`
- `workspace_refs: list[str]`
- `forbidden_context: list[str]`
- `token_budget: dict`
- `packet_metadata: dict`
- `trace_refs: list[str]`

## 5.3 Read Manifest / Packet Summary

每次 build packet 后，必须留 deterministic read manifest。

最小包含：

- `consumer_kind`
  - `writer_packet`
  - `worker_packet`

- `identity`
- `visible_refs`
- `selected_refs`
- `forbidden_refs`
- `packet_policy`
- `budget_metadata`
- `section_source_summary`

## 5.4 Canonical contract ownership

本规格书是以下对象的 canonical contract：

- `WritingPacket`
- `PacketSection`
- `WorkerContextPacket`
- `RuntimeReadManifestRecord`

其他规格书若需要列出这些对象，只允许列摘要或引用，不再各自定义另一套字段语义。

## 6. Packet 允许进入和禁止进入的内容

## 6.1 writer packet 允许进入

- `Core State` 当前视图 / projection block views
- 近 X 轮 user input / writer output 原文窗口
- longform review overlay
- longform accepted outline / chapter goal / chapter bridge material
- roleplay mode sidecar
- trpg rule card / state card
- retrieval cards 摘要
- 必要的 retrieval expanded content
- system prompt / writer contract

## 6.2 writer packet 禁止进入

- raw authoritative JSON
- raw retrieval hit 全量文本集合
- Runtime Workspace 日志
- worker 中间推理
- tool call trace
- token usage trace
- proposal/apply 内部日志
- branch/control receipts

## 6.3 worker packet 可以进入

- Runtime Workspace refs
- retrieval refs
- worker candidate refs
- packet refs
- read manifest refs
- pending/dirty 相关 refs

关键区别：

- writer packet 面向文本生成，必须窄而干净
- worker packet 面向治理和分析，可以拿更多结构化 refs

## 7. Context Orchestration Layer 职责

## 7.1 负责什么

1. 按 policy 读取可见内容
2. 从 read-side 服务选取 refs
3. 构造 writer packet
4. 构造 worker packet
5. 做预算裁剪
6. 记录 read manifest / packet summary

## 7.2 不负责什么

1. 不判断要不要检索
2. 不决定本轮启用哪些 worker
3. 不把 retrieval 结果直接写成 truth
4. 不接收自由文本 reasoning 再二次猜测内容用途

## 7.3 输入

- `MemoryRuntimeIdentity`
- `RuntimeProfileSnapshot`
- `turn_kind / command_kind / operation_mode`
- read-side refs：
  - core view
  - recent turns
  - sidecars
  - retrieval cards
  - review overlay
- packet policy
- token budget

## 7.4 输出

- `WritingPacket`
- `WorkerContextPacket`
- `RuntimeReadManifestRecord`

## 8. 组包规则

## 8.1 Writer packet 组包顺序

建议顺序：

1. `system_sections`
2. `writer_contract`
3. `core_view_sections`
4. `recent_raw_turn_sections`
5. `mode_sidecar_sections`
6. `retrieval_card_sections`
7. `review_overlay_sections`
8. `user_instruction`

原因：

- 先给 writer 规则
- 再给当前事实
- 再给现场连续性
- 再给 mode 特殊结构
- 再给检索证据
- 最后给当前操作指令

## 8.2 Recent raw turns 规则

冻结口径：

- writer packet 不能只依赖当前视图
- 必须保留近几轮原文窗口
- 原文窗口用于保留语气、细节、节奏、用户即时意图和刚发生但不宜沉淀的内容

## 8.3 Retrieval cards 规则

冻结口径：

- writer 不直接记随机 hit_id / chunk_id
- retrieval 层输出稳定 card / short id
- writer packet 先给摘要
- expanded content 按需加入
- raw retrieval 全量结果不直接入 writer packet

## 8.4 Review overlay 规则

- 只在 longform `rewrite` 或相关 mode 下进入
- 作为 sidecar section，而不是混进 core truth
- 后续由 writer 在 rewrite 中消费

## 8.5 Packet 裁剪规则

裁剪优先顺序建议：

1. 先保留 system sections 和 user instruction
2. 再保留 core view
3. 再保留 recent raw turns
4. 再保留 mode sidecars
5. 最后裁 retrieval / overlay 的非必要部分

禁止：

- 为了省 token 把近几轮原文全删掉，只剩视图
- 为了省 token 让 Runtime Workspace 日志替代 structured summary

## 9. Token usage 规则

冻结口径：

- 本地预算只用于组包前裁剪辅助
- 实际 token 消费量来自上游 LLM 返回的 usage metadata
- writer / worker 调用完成后，把 usage metadata 回写到 turn/workspace/packet metadata

这意味着：

- `estimated_token_budget` 不是真相
- `actual_usage_metadata` 才是真相

## 10. 伪代码

## 10.1 Build writing packet

```python
def build_writing_packet(identity, operation_mode, packet_policy):
    core_view = read_core_projection(identity)
    recent_turns = read_recent_raw_turns(identity, window=packet_policy.raw_turn_window)
    sidecars = read_mode_sidecars(identity, operation_mode)
    retrieval_cards = read_runtime_retrieval_cards(identity)
    review_overlay = read_review_overlay(identity, operation_mode)

    sections = assemble_sections(
        core_view=core_view,
        recent_turns=recent_turns,
        sidecars=sidecars,
        retrieval_cards=retrieval_cards,
        review_overlay=review_overlay,
    )
    sections = trim_sections_by_budget(sections, packet_policy)

    packet = WritingPacket(
        packet_id=new_id(),
        identity=identity,
        output_kind=resolve_output_kind(identity, operation_mode),
        phase=resolve_phase(identity),
        operation_mode=operation_mode,
        system_sections=build_system_sections(identity),
        core_view_sections=sections.core_view,
        recent_raw_turn_sections=sections.recent_turns,
        mode_sidecar_sections=sections.sidecars,
        retrieval_card_sections=sections.retrieval_cards,
        review_overlay_sections=sections.review_overlay,
        user_instruction=resolve_user_instruction(identity),
        writer_contract=load_writer_contract(identity),
        packet_summary_metadata=sections.summary,
    )
    write_read_manifest(packet)
    return packet
```

## 10.2 Build worker packet

```python
def build_worker_context_packet(identity, worker_id, phase, context_requirements):
    refs = resolve_refs_by_requirements(identity, worker_id, context_requirements)
    packet = WorkerContextPacket(
        packet_id=new_id(),
        identity=identity,
        worker_id=worker_id,
        phase=phase,
        mode=resolve_mode(identity),
        session_refs=refs.session_refs,
        recent_turn_refs=refs.recent_turn_refs,
        core_projection_refs=refs.core_projection_refs,
        sidecar_refs=refs.sidecar_refs,
        retrieval_refs=refs.retrieval_refs,
        workspace_refs=refs.workspace_refs,
        forbidden_context=refs.forbidden_context,
        token_budget=refs.token_budget,
        packet_metadata=refs.metadata,
    )
    write_read_manifest(packet)
    return packet
```

## 11. 测试点

1. writer packet 不含 Runtime Workspace 日志
2. writer packet 一定包含近几轮原文窗口
3. worker packet 能引用 workspace refs
4. retrieval cards 使用 short ids，而非随机 hit ids 暴露给 writer
5. usage metadata 回写后，packet summary 可读到实际消耗
6. branch switch 后，writer packet 只读当前 active branch 的可见内容

## 12. 已知风险

1. 当前 `writing_runtime.py` 的 `WritingPacket` 太薄，后续要注意是扩展还是新建更正式的 contract 模型文件
2. 如果 dev 继续把 builder 当作纯 longform 组件，不上提为 context orchestration，后续 rp/trpg 会再次分叉
3. packet section 若无统一 `source_ref_ids`，后续 debug/eval 很难准确定位组包来源
