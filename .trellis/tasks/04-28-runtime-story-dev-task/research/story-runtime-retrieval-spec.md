# Story Runtime Writer-side Retrieval Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Module: Writer-side Retrieval
>
> Status: draft-v1

## 1. 范围

本规格书负责冻结：

- writer-side bounded retrieval
- retrieval cards
- short id / expand 语义
- retrieval usage hook
- knowledge gap / miss 处理
- retrieval 与 Runtime Workspace 的对接

这份文档不负责：

- retrieval-core 的底层召回算法
- reranker / graph expansion 的内部策略
- post-write 治理逻辑
- packet 组装总规则

## 2. 设计目标

这一层要解决 8 个问题：

1. writer 怎么判断自己缺信息
2. 为什么 retrieval 不做创作性总结
3. 为什么要先给卡片和摘要，而不是直接灌全文
4. 为什么要有 short id
5. expand 为什么只能针对已返回卡片
6. final output 前为什么必须补 usage hook
7. miss / retry / knowledge gap 怎么处理
8. retrieval 命中为什么不能自动进入 Core State

## 3. 当前实现判断

当前后端里：

- `retrieval_broker.py`
  - 已有 branch-aware read/filter 方向

- `retrieval_service.py`
  - 已有 retrieval-core 检索主链

- `runtime_retrieval_card_service.py`
  - 已有把 search result 物化成 Runtime Workspace cards 的雏形
  - 已有 expand / usage record / writer visible materials 能力

结论：

- 当前 `RuntimeRetrievalCardService` 是最好的直接复用基础
- 但 writer-side retrieval 的 loop、usage gating、knowledge gap 规则还没有被规格化

## 4. 文件落位建议

## 4.1 复用现有文件

- `backend/rp/services/runtime_retrieval_card_service.py`
- `backend/rp/services/retrieval_broker.py`
- `backend/rp/services/retrieval_service.py`
- `backend/rp/services/runtime_workspace_material_service.py`

## 4.2 新增文件建议

- `backend/rp/models/retrieval_runtime_contracts.py`
- `backend/rp/services/writing_worker_retrieval_loop_service.py`
- `backend/rp/services/writer_retrieval_usage_guard_service.py`

说明：

- `RuntimeRetrievalCardService` 继续负责 materialization / expand / usage record
- `WritingWorkerRetrievalLoopService` 负责 writer 侧工具循环与 gating

## 5. 核心对象

## 5.1 RetrievalCard

产品语义：

- writer 可见的稳定引用材料
- 不是 story truth

建议字段：

- `material_id: str`
- `short_id: str`
- `search_kind: str`
  - `recall`
  - `archival`

- `query_text: str`
- `hit_id: str`
- `domain: str`
- `domain_path: str | None`
- `title: str | None`
- `summary: str | None`
- `excerpt: str | None`
- `score: float | None`
- `source_refs: list[str]`
- `visibility: str`
- `lifecycle: str`
- `metadata_json: dict`

关键约束：

- writer 永远引用 `short_id` 或 `material_id`
- 不直接记随机 chunk id / hit id

## 5.2 ExpandedRetrievalChunk

建议字段：

- `material_id: str`
- `parent_card_material_id: str`
- `short_id: str`
- `chunk_id: str`
- `title: str | None`
- `text: str`
- `token_count: int | None`
- `source_refs: list[str]`
- `visibility: str`
- `lifecycle: str`
- `metadata_json: dict`

关键约束：

- expand 只允许针对已返回 card
- expanded chunk 仍然只是 turn-local evidence

## 5.3 RetrievalUsageRecord

建议字段：

- `material_id: str`
- `identity: MemoryRuntimeIdentity`
- `used_card_short_ids: list[str]`
- `expanded_card_short_ids: list[str]`
- `unused_card_short_ids: list[str]`
- `used_card_material_ids: list[str]`
- `used_expanded_chunk_material_ids: list[str]`
- `unused_card_material_ids: list[str]`
- `missed_query_material_ids: list[str]`
- `knowledge_gaps: list[KnowledgeGapItem]`
- `usage_kind: str`
  - `writer_explicit`

- `source_refs: list[str]`
- `visibility: str`
- `lifecycle: str`
- `metadata_json: dict`

### KnowledgeGapItem

建议字段：

- `gap_id: str`
- `query_text: str`
- `gap_kind: str`
  - `miss`
  - `insufficient_detail`
  - `rule_required`

- `mode_policy_resolution: str`
  - `continue_conservatively`
  - `continue_avoid_detail`
  - `stop_and_request_rule`

- `notes: str | None`

关键约束：

- final output 前必须有 usage record
- post-write 只读取 usage record，不从自然语言里猜 writer 用了哪些卡
- writer tool API 可以提交 short ids；runtime guard 必须在持久化前解析成 material ids

## 5.4 RetrievalMissMaterial

当前已有 `RETRIEVAL_MISS` material kind。

建议字段：

- `material_id: str`
- `query_text: str`
- `search_kind: str`
- `attempt_index: int`
- `miss_reason: str`
- `source_refs: list[str]`
- `metadata_json: dict`

用途：

- 记录检索 miss
- 支撑 bounded retry 与 knowledge gap

## 6. Writer-side Retrieval Loop 规则

## 6.1 核心原则

冻结口径：

- writer 自己判断是否缺信息
- retrieval 层只负责 query augment、search、filter、rerank、score、card materialization
- retrieval 不结合当前剧情做创作性总结

## 6.2 Loop 限制

writer retrieval loop 必须受控：

- 只开放 retrieval 相关工具
- 限定最大 attempt 次数
- expand 只针对已返回 card
- final output 前必须有 usage hook

## 6.3 渐进披露

推荐顺序：

1. 先返回 summary cards
2. writer 判断哪些信息不够
3. 对指定 card 请求 expand
4. 再决定是否足够写作

原因：

- 避免一开始把全文灌进上下文
- 降低 token 消耗
- 保持 retrieval 只做 evidence delivery

## 6.4 Miss / Retry 规则

冻结口径：

- writer 可在 bounded attempts 内重试 query
- 超过次数后必须形成 knowledge gap
- mode-specific 行为：
  - longform: 可保守继续写
  - roleplay: 可继续互动但避免编造缺失细节
  - trpg: 若缺硬规则/数值依据，不能静默编造

## 7. Retrieval 与 Runtime Workspace

## 7.1 必须先落入 Runtime Workspace

所有 writer-side retrieval 材料都先落到 Runtime Workspace：

- retrieval cards
- expanded chunks
- miss materials
- usage record

禁止：

- raw hit 直接进 Core State
- retrieval raw materials 直接持久化为 Recall/Archival truth

## 7.2 生命周期

turn 内：

1. search -> cards
2. expand -> expanded chunks
3. final output 前 -> usage record
4. post-write -> block-owner workers 读取 usage record 中 backend-resolved fields / gaps
5. post-write 完成后 -> raw materials `promoted / discarded / expired`

## 7.3 post-write 消费规则

post-write 只处理：

- `used_card_material_ids`
- `used_expanded_chunk_material_ids`
- `knowledge_gaps`

默认不处理：

- 未使用 cards
- 单纯浏览过但没引用的扩展内容

## 8. Retrieval 与 Core State 的边界

冻结口径：

- retrieval 命中只是 evidence，不是事实
- 只有当 block-owner worker 判断“这已经成为当前剧情必须遵守的事实”后
- 才允许通过 permission / proposal / apply / user review 链进入 Core State

也就是说：

- writer retrieval -> Runtime Workspace
- post-write worker -> fact candidate
- governance chain -> Core State / Recall / Archival

## 9. 伪代码

## 9.1 search to cards

```python
def search_to_cards(identity, query_text, search_kind, actor):
    result = retrieval_broker.search(query_text=query_text, search_kind=search_kind, identity=identity)
    cards, miss_material = runtime_retrieval_card_service.materialize_search_result(
        identity=identity,
        result=result,
        actor=actor,
        query_text=query_text,
        search_kind=search_kind,
    )
    return cards, miss_material
```

## 9.2 bounded retrieval loop

```python
def run_writer_retrieval_loop(identity, writer_request):
    attempts = 0
    while attempts < writer_request.max_retrieval_attempts:
        tool_call = ask_writer_for_tool_or_output()
        if tool_call.kind == "final_output":
            ensure_usage_record_exists(identity)
            return tool_call.output
        if tool_call.kind == "search":
            search_to_cards(
                identity=identity,
                query_text=tool_call.query_text,
                search_kind=tool_call.search_kind,
                actor="writer.retrieval",
            )
        elif tool_call.kind == "expand":
            runtime_retrieval_card_service.expand_cards(
                identity=identity,
                card_material_ids=tool_call.card_material_ids,
                actor="writer.retrieval",
            )
        elif tool_call.kind == "usage":
            runtime_retrieval_card_service.record_writer_usage(
                identity=identity,
        used_card_ids=tool_call.used_card_short_ids,
        used_expanded_chunk_ids=tool_call.used_expanded_card_short_ids,
        missed_query_ids=tool_call.missed_query_short_ids,
        actor="writer.retrieval",
    )
        attempts += 1
    record_knowledge_gap(identity)
    return conservative_final_output()
```

## 9.3 usage guard

```python
def ensure_usage_record_exists(identity):
    if runtime_workspace_has_retrieval(identity) and not runtime_workspace_has_usage_record(identity):
        raise WriterRetrievalUsageError("writer_retrieval_usage_missing")
```

## 10. 测试点

1. writer 可以拿到稳定 short ids 的 cards
2. expand 只能作用于已返回 card
3. miss 会生成 `RETRIEVAL_MISS`
4. final output 前缺 usage record 会失败
5. post-write 只消费 used cards / expanded chunks / gaps
6. retrieval raw hit 不直接进入 Core State

## 11. 已知风险

1. 当前 `RuntimeRetrievalCardService.record_writer_usage()` 还没显式记录 writer-facing short ids、`unused_card_material_ids` 与结构化 `knowledge_gaps`；实现时要补齐
2. 如果 dev 让 writer 直接引用底层 `chunk_id`，后续 expand、usage、post-write 都会不稳定
3. 如果 retrieval 层开始做剧情总结，会重新把 retrieval 和 writer 的职责混在一起
