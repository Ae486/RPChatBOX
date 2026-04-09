# Provider Model Single Source Plan

## 1. Scope

本文只讨论基础 LLM 请求链中的 `provider/model` 真单源迁移。

目标：

- backend 成为 provider/model 的运行时真源
- Flutter 退为：
  - UI
  - 编辑入口
  - 流式渲染
  - 本地镜像 / 回滚层

不在本文范围：

- MCP runtime
- RP agent
- RAG

## 2. Current State

当前状态分裂如下：

### 2.1 Provider

- backend 已有 provider registry
- Flutter 已能：
  - upsert provider 到 backend
  - delete provider from backend
  - 从 backend 拉 provider summary 回来校准本地镜像

当前问题：

- 本地 `SharedPreferences` 仍保存 provider 完整配置
- backend 还不是绝对单真源，只是“运行时已开始引用 provider_id”

### 2.2 Model

- model 仍完全存储在 Flutter `SharedPreferences`
- backend 目前没有 model registry
- UI 所有 model 列表、增删改、启用状态都以本地为准

结论：

- provider：已完成第一阶段真源迁移
- model：还没有开始真源迁移

## 3. Target Architecture

目标链路：

```text
Flutter Provider/Model UI
  -> backend registry APIs
  -> backend persistent storage
  -> backend runtime read-path
  -> Flutter mirror refresh
```

### 3.1 Backend Responsibilities

backend 负责：

- provider registry
- model registry
- `/v1/chat/completions` runtime provider resolution
- `/models` upstream model listing
- provider/model metadata as source of truth

### 3.2 Flutter Responsibilities

Flutter 负责：

- provider/model 编辑页
- model selector UI
- 本地镜像缓存
- backend 不可用时的回滚体验

## 4. Migration Strategy

### Phase A. Backend Model Registry Foundation

新增 backend model registry：

- `GET /api/providers/{provider_id}/models`
- `GET /api/providers/{provider_id}/models/{model_id}`
- `PUT /api/providers/{provider_id}/models/{model_id}`
- `DELETE /api/providers/{provider_id}/models/{model_id}`

设计原则：

- 使用 nested resource，避免与现有 `/models` 健康探测/上游透传冲突
- model 视为 provider 的子资源

### Phase B. Flutter Model Sync

新增 Flutter `BackendModelRegistryService`，负责：

- upsert model
- delete model
- list provider models

`ModelServiceManager` 新增：

- `syncModelsToBackend()`
- `refreshModelMirrorsFromBackend()`

### Phase C. Backend-First Read Path

backend 模式下：

- 先同步本地 models 到 backend
- 再从 backend 拉取 models 校准本地镜像

当前采用保守策略：

- provider 仍保留本地镜像
- model 也保留本地镜像
- backend 开始成为真源，但 Flutter 暂不删除本地镜像层
- 对已知 provider，允许导入 backend-only model
- 对 backend 未返回的本地 model，当前阶段先保留，避免首次接入或同步失败时误丢数据

### Phase D. Final True Source

后续阶段再做：

- Flutter 本地 models 不再当主真源
- selector / provider detail / services page 都以 backend 返回数据为主
- 本地只保留缓存和回滚

## 5. Slice 1 Implementation Goal

第一刀只做：

1. backend model registry
2. Flutter model sync
3. provider delete -> backend model cascade delete
4. backend 模式下 models page 先做 provider+model mirror refresh

第一刀不做：

1. UI 重构
2. conversation settings 迁移
3. backend key custody 深化
4. MCP runtime

## 6. Risks

### R1. Initial backend model registry empty

如果直接从 backend 拉 models，可能把本地已有 models 看成“消失”。

规避：

- 先 `syncModelsToBackend()`
- 再 `refreshModelMirrorsFromBackend()`

### R2. Provider delete leaves orphan models

规避：

- backend provider delete 时级联删除 model registry entries

### R3. UI still reads local mirrors

这是当前阶段的刻意设计，不算 bug。

原因：

- 降低切换风险
- 允许快速回滚

## 7. Acceptance Criteria

完成第一刀后应满足：

1. backend 有独立 model registry 持久化
2. Flutter add/update/delete model 会同步 backend
3. backend 模式下，model list 可从 backend 校准本地镜像
4. provider 删除时 backend models 不残留
5. 现有 UI 结构与聊天主链不受影响
