# Skills Builder

## Goal

为 SetupAgent 引入 **Stage SkillPack** 概念，让 agent 在 setup 各 stage 装载 stage-local 专业能力包（persona + 引导风格 + 收敛策略），用完即卸。本任务交付：

1. SkillPack 文件格式（Anthropic Skill 风格 markdown + frontmatter，stage 级一一对应）。
2. SkillPack 装载机制（按 `SetupStageId` 查表，命中即在 system prompt 替换 `_stage_overlay` 输出 + 插入 specialist-hat 引导句）。
3. 一个完整 Pilot：**`character_design`** stage 的 SkillPack。

> **不接管 tool_scope**：stage 工具语义由现有 `setup.truth.write strict pilot` spec 处理（runtime 注入 `stage_id` + `block_type=stage_draft`）。SkillPack 不携工具白名单字段、不改造 `build_setup_agent_tool_scope`。

## Current Code Baseline

> 粒度统一已基本落实（详见 `backend/rp/models/setup_stage.py` 与 `backend/rp/models/setup_drafts.py`）。本节摘录与 SkillPack 直接相关的现状。

### 1. `SetupStageId`（9-stage 权威枚举）

`backend/rp/models/setup_stage.py:10`：

```python
class SetupStageId(StrEnum):
    WORLD_BACKGROUND = "world_background"
    CHARACTER_DESIGN = "character_design"           # Pilot 锚点
    PLOT_BLUEPRINT = "plot_blueprint"
    WRITER_CONFIG = "writer_config"
    WORKER_CONFIG = "worker_config"
    OVERVIEW = "overview"
    ACTIVATE = "activate"
    RP_INTERACTION_CONTRACT = "rp_interaction_contract"   # roleplay 模式专属
    TRPG_RULES = "trpg_rules"                              # trpg 模式专属
```

值用 **snake_case**（与前端 camelCase 不一致，需在前端 stage 字符串发出口统一为 snake_case）。

### 2. `SetupStageModule` 与 `SETUP_STAGE_MODULES` 注册表

每个 stage 已有数据层模块定义（`backend/rp/models/setup_stage.py:36`）：

```python
class SetupStageModule(BaseModel):
    stage_id: SetupStageId
    display_name: str                                     # 中文显示名
    draft_block_type: str                                 # = stage_id.value
    default_entry_types: list[str]                        # 该 stage 的 entry 类型词汇
    default_section_templates: list[SetupDraftSectionTemplate]
    allow_commit: bool = True
    discussion_stage: bool = True                          # overview / activate 为 False
```

例如 `CHARACTER_DESIGN` 模块声明：
- `display_name = "角色设定"`
- `default_entry_types = ["character", "relationship", "group"]`
- `default_section_templates = [{section_id: "summary"}, {section_id: "relationships", retrieval_role: "relationship"}]`

### 3. `MODE_STAGE_PLANS` 模式驱动的 stage 序列

```
longform: world_background → character_design → plot_blueprint → writer_config → worker_config → overview → activate
roleplay: world_background → character_design → rp_interaction_contract → writer_config → worker_config → overview → activate
trpg:     world_background → character_design → trpg_rules → writer_config → worker_config → overview → activate
```

### 4. 数据层统一 draft 容器

`SetupStageDraftBlock`（`setup_drafts.py:119`）：

```python
class SetupStageDraftBlock(BaseModel):
    stage_id: SetupStageId
    entries: list[SetupDraftEntry]                         # 统一 entry 语法
    notes: str | None = None
```

`SetupDraftEntry`（`setup_drafts.py:95`）：含 `entry_id / entry_type / semantic_path / title / sections[]`，sections 带 `retrieval_role` 标记。

`SetupWorkspace.draft_blocks: dict[str, SetupStageDraftBlock]`（`setup_workspace.py:251`）已就位。

### 5. tool_scope 现状

`backend/rp/agent_runtime/profiles.py`：

- `SETUP_READ_ONLY_MEMORY_TOOLS`（6 个 memory.* 只读工具）
- `SETUP_SHARED_PRIVATE_TOOLS`（11 个 setup.* 共享工具：discussion / chunk / truth / question / asset / proposal.commit / read.* / truth_index.*）
- `SETUP_STEP_PATCH_TOOLS`（4-stage 旧表，legacy 兼容用）
- `SETUP_STAGE_PATCH_TOOLS`（**有意保持空 tuple**，per spec `rp-setup-agent-strict-truth-write-tool-pilot.md` —— stage 写入由 `setup.truth.write` 接管，不拆独立 patch tool）
- `build_setup_agent_tool_scope(stage_or_step_value)` 已就位，由 adapter 用 `selected_stage.value` 调用

**SkillPack 不接管该层**。stage 隔离的工具语义已由 `setup.truth.write strict pilot` 处理（runtime 注入 `stage_id` + `block_type=stage_draft`）。

### 6. 旧字段共存（过渡期，对 SkillPack 影响极小）

- 4 个旧 draft 模型（`StoryConfigDraft / WritingContractDraft / FoundationDraft / LongformBlueprintDraft`）仍存在并被 `SetupWorkspace` 引用（粒度统一收尾任务负责迁移到 `SetupStageDraftBlock`）
- 4 个旧 patch 工具（`setup.patch.story_config / writing_contract / foundation_entry / longform_blueprint`）仍是 legacy fallback；新 stage 写入走 `setup.truth.write + block_type=stage_draft`
- `_legacy_step_for_stage` 桥接 SetupStageId → SetupStepId（用于 legacy 字段读写）

**SkillPack 与这些过渡现状解耦**：SkillPack 只管 system prompt 中 stage-local prose；不引用 4 个旧 draft 模型、不引用 patch 工具名。SkillPack body 引用 entry shape 时按新容器 `SetupStageDraftBlock` 与 `SetupDraftEntry` 写。

## 设计原则

### 来自 Anthropic Agent Skills 设计指南（采纳）

参考 [Anthropic Skill Authoring Best Practices](https://docs.anthropic.com/en/docs/agents-and-tools/agent-skills/best-practices)：

- **conciseness is core**：context window 是公共资源，每个 token 必须证明自己值。
- **imperative / infinitive form**：指令用祈使句 / 不定式。
- **second person for agent-facing prose**：persona / objectives / forbidden / facilitation 用 "You..." 第二人称。
- **consistent terminology**：术语固化。
- **degree of freedom matched to task**：character design 任务多解，用高自由度 prose 指引。
- **avoid time-sensitive info**：不写时效性内容。
- **markdown is the canonical format**：SKILL.md 是 markdown + YAML frontmatter，不要 pydantic 化 prose 内容。

### 与 Anthropic Skill 的机制差异（有意为之）

| 维度 | Anthropic Skill | 我们 SkillPack | 一致吗？ |
|---|---|---|---|
| 文件形态 | `skill-name/SKILL.md` 目录格式 | 同样 | 一致 |
| Frontmatter | `name`, `description` | `name`, `stage_id`, `description` | 一致（多 1 个路由字段 stage_id）|
| Body 结构 | 自由 markdown | 自由 markdown（约定 sections）| 一致 |
| 装载到哪 | system prompt | system prompt（替代原 `_stage_overlay` 槽位）| 一致 |
| 用完即卸 | 是 | 是（硬卸载）| 一致 |
| **选定机制** | **LLM 看 description 自选** | **后端按 SetupStageId 查表** | **唯一差异点** |

**为何选 deterministic-by-stage**：UI 已显式告诉系统 "用户在 character_design stage"（前端 wizard 选中 + 后端 `current_stage` 字段），让 LLM 再"猜一遍"是冗余。

### 本任务专属设计原则

1. **不当裁判**：SkillPack **不**给 agent 自动判定 ready / commit 的硬阈值。
2. **引导优先**：SkillPack 让 agent 引导用户、追问盲区、发散思路，不做"卡流程"的检查表。
3. **骨架推荐而非强制**：content skeleton 提建议而不强制 schema；题材敏感字段走 `extras` 自由扩展槽。
4. **硬卸载**：stage 切换后旧 SkillPack 字符级不出现在新 system prompt 中。
5. **语言分层**：persona / objectives / forbidden / facilitation 用英文；clarification_templates 用中文。
6. **替代 `_stage_overlay` 输出（方案 A）**：命中 SkillPack 时，`_stage_overlay` 内部直接返回 SkillPack body，不再返回原 9-stage prose 分支。未命中时（其他 8 个 stage 暂无 SkillPack）回退到现行 `_stage_overlay` prose。  
   - **不动 `_stage_overlay` 函数的 9-stage 分支表**，仅在命中 SkillPack 时短路它的输出 —— 防御性容错优于美观重构。
7. **persona swap 而非 You-are 互冲**：base prompt 开头插入 specialist-hat 引导句（仅命中 SkillPack 时），SkillPack body 不写 "You are X"。
8. **不接管 tool_scope**：SkillPack 不携工具白名单字段、不改 `build_setup_agent_tool_scope`。stage 隔离工具语义由现有 `setup.truth.write strict pilot` spec 处理。
9. **与 `SetupStageModule` 互补**：Module 是数据层（display_name / draft_block_type / default_entry_types / section_templates），SkillPack 是能力层（persona / 收敛策略）。两者一一对应同一个 SetupStageId。

## 文件形态与目录结构

```
backend/rp/agent_runtime/skill_packs/
  __init__.py                                  # 启动扫描目录、构 REGISTRY
  registry.py                                  # SkillPackRecord + load_registry() + render_skill_pack() + get_for_stage()
  character_design/
    SKILL.md                                   # Pilot 唯一交付的内容文件
  # 未来：world_background/SKILL.md / plot_blueprint/SKILL.md / ...
```

放在 `backend/rp/agent_runtime/` 下（与 profiles.py / adapters.py / tools.py 同层），因为 SkillPack 本质是"运行时 prompt 定制"，归属于 agent_runtime 概念。

每个 SkillPack 是一个目录（与 Anthropic Skill 文件格式一致），目录名 = `SetupStageId.value`（snake_case）。`SKILL.md` 是 frontmatter + markdown body。

未来在每个 SkillPack 目录下可加 `references/` 子目录承载 progressive disclosure 的第三层内容（如 character preset 库 / methodology 详解），与 Anthropic 一致。

## SKILL.md frontmatter 与 body

### Frontmatter 必填字段

```yaml
---
name: character-design.v1
stage_id: character_design
description: |
  WHAT: Drives the SetupAgent through the character-design stage —
  elicits the cast, deepens motivation/limits/voice, exposes relational
  tension, and stays scoped to character entries.
  WHEN: SetupStageId.CHARACTER_DESIGN. Loaded automatically by
  SetupAgentPromptService whenever the resolved stage is character_design.
---
```

仅 3 个字段：`name` / `stage_id` / `description`。无工具白名单字段。

> `description` 仅作内部文档与日志，**不渲染入 prompt**。与 Anthropic 的 description 用于 LLM 自选不同，我们走确定性查表，description 退化为人看的文档。

### Body markdown sections（约定）

```markdown
## Specialist hat
（一段 prose，描述本 stage 专业人格视角；以 "A senior dramatist..." 开头，不用 "You are X"）

## Objectives
- bullet list

## Forbidden
- bullet list

## Facilitation principles
- bullet list（描述 agent 引导风格）

## Recommended content skeleton
- `path` — note（推荐 entry sections 字段维度，全可空）

## Clarification templates
- intent: ...（EN）
  template: ...（ZH）
```

## 数据结构（运行时 contract）

```python
# backend/rp/agent_runtime/skill_packs/registry.py

class SkillPackRecord(BaseModel):
    """In-memory representation of a parsed SKILL.md."""
    model_config = ConfigDict(extra="forbid")

    name: str                                              # 来自 frontmatter
    stage_id: SetupStageId                                 # 来自 frontmatter
    description: str = ""                                  # 来自 frontmatter；仅文档/日志，不渲染
    body: str                                              # markdown 主体（去掉 frontmatter）

STAGE_SKILL_PACKS: dict[SetupStageId, SkillPackRecord]     # 启动时由 load_registry() 填充
```

唯一 pydantic 类。无 `FieldHint` / `ClarificationTemplate` 等子结构 —— 这些都是 markdown body 里的列表项，按需阅读，不需要程序化访问。无 `required_tools_stage_specific` 字段 —— SkillPack 不接管 tool_scope。

## 装载 / 卸载语义

### 装载（命中 SkillPack）

当当前 turn 的 stage 命中 `STAGE_SKILL_PACKS[stage_id]` 时，**只改 system prompt**：

1. base prompt 开头追加 specialist-hat 引导句（详见下文 Base Prompt Refactor）
2. `_stage_overlay` 内部短路返回 SkillPack body（方案 A）—— 原 9-stage prose 分支跳过
3. tool_scope 不变（仍由 `build_setup_agent_tool_scope(selected_stage.value)` 处理，按现行逻辑）
4. adapter metadata（可选）加 `skill_pack_name` 供 trace 关联（见 Backend Contract Changes）

### 硬卸载（未命中或切换）

下一 turn 若 stage_id 变更或为 None / 不在注册表：

- system prompt 中**字符级不出现**旧 SkillPack 任何内容、specialist-hat 引导句、`[Stage Skill Pack` 标记段
- `_stage_overlay` 退回正常路径，返回该 stage 的现行 9-stage prose
- tool_scope 不变（一致）

无 "former skill summary" 软过渡。前 stage 真相通过现有 `prior_stage_handoffs` 合同传递。

## Base Prompt Refactor（persona swap）

### Why

现行 `setup_agent_prompt_service.py::build_system_prompt` 开头 "You are SetupAgent..."。SkillPack 若也写 "You are a senior dramatist" 会形成两个 "You are X" 互冲。

### How

修改 `setup_agent_prompt_service.py::build_system_prompt`：

```
You are SetupAgent, the prestory setup assistant.
[SetupAgent operating envelope: prestory only / no active prose / no Memory OS direct mutation / etc.]

{IF SkillPack present:}
For this turn, you operate in the {stage_module.display_name} stage.
While in this stage, take on the perspective of the Specialist hat described in the Stage Skill Pack section below.
Treat the Specialist hat as your guiding voice for this turn, but never break the SetupAgent operating envelope above.
{END IF}

Core rules:
1. ...

{IF SkillPack present:}
[Stage Skill Pack: {pack.name}]
{pack.body}
[/Stage Skill Pack]
{ELSE:}
Current stage objective:
{_stage_overlay}
{END IF}

Longform setup guidance:
- ...

The workspace/context packet is below as JSON. ...
{workspace_snapshot}
```

> SkillPack body 已包含 `## Specialist hat` 等 sections，整体保留作者写的 markdown 结构。

## Backend & Frontend Contract Changes

### Backend（本任务范围内）

1. **新增** `backend/rp/agent_runtime/skill_packs/` 目录与 `character_design/SKILL.md` 文件。
2. **新增** `backend/rp/agent_runtime/skill_packs/registry.py`：定义 `SkillPackRecord`、`load_registry()`、`STAGE_SKILL_PACKS` 常量、`render_skill_pack(record) -> str`、`get_skill_pack_for_stage(stage_id) -> SkillPackRecord | None`。
3. **改造** `SetupAgentPromptService._stage_overlay(...)`（per 方案 A）：
   - 命中 SkillPack 时：短路返回 `render_skill_pack(record)` 输出（含 `[Stage Skill Pack: ...]` 标记段与 markdown body）
   - 未命中时：保留现行 9-stage prose 分支不动
4. **改造** `SetupAgentPromptService.build_system_prompt(...)`：
   - 命中 SkillPack 时：在 base prompt 开头追加 specialist-hat 引导句（紧跟 "You are SetupAgent..." 那段，在 Core rules 之前）
   - 未命中时：行为与现行字节级一致

### Backend 链路（已由粒度统一任务完成，本任务不动）

- ✅ `SetupAgentTurnRequest.target_stage: SetupStageId | None`
- ✅ `SetupGraphState.target_stage` + runner / nodes 透传
- ✅ API langfuse metadata 含 `target_stage`
- ✅ `SetupRuntimeAdapter` 选 `selected_stage` 并传给 `build_system_prompt`

### Backend 可选小改（trace 可观测性）

5. **可选**：`SetupRuntimeAdapter.build_turn_input` 在 `RpAgentTurnInput.metadata` 加一行 `"skill_pack_name": pack.name if pack else None`，便于 langfuse / eval 关联。1 行改动，不阻塞 Pilot；建议一并做。

### Frontend（**已由粒度统一任务完成，本任务不动**）

- ✅ `prestory_setup_page.dart` 已在 turn 调用处传 `targetStage = _targetStageForSelectedStage(workspace)`
- ✅ 客户端层已序列化 `target_stage` 字段

## Pilot Scope: character_design SkillPack 内容

### 以 markdown 写在 `backend/rp/agent_runtime/skill_packs/character_design/SKILL.md`

```markdown
---
name: character-design.v1
stage_id: character_design
description: |
  WHAT: Drives the SetupAgent through the character-design stage —
  elicits the cast, deepens motivation/limits/voice, exposes relational
  tension, and stays scoped to character entries.
  WHEN: SetupStageId.CHARACTER_DESIGN. Loaded automatically by
  SetupAgentPromptService whenever the resolved stage is character_design.
---

## Specialist hat

A senior dramatist and character writer. Your craft is shaping believable
people: motivation arcs, internal contradictions, voice, relational tension,
and how each character lives inside the story's world rules. While operating
in this stage, you elicit, propose, and refine character entries; you do not
write scenes, dialogue, or plot beats.

## Objectives

- Help the user articulate the core cast — at least the protagonist, plus other characters the story actually needs.
- For each character, surface stable identity, motivation (surface vs underlying), capabilities and meaningful limits, voice cues, and how the character fits the already-anchored world / rules.
- Surface relational tension and conflict sources between characters that downstream plot stages can build on.

## Forbidden

- Do not write narrative prose, scenes, or in-story dialogue.
- Do not invent or assume world or rule facts that the world_background stage has not yet anchored — defer to that stage instead.
- Do not mutate writer_config or plot_blueprint drafts; this stage only produces / refines character entries within the character_design draft block.
- Do not call `setup.proposal.commit` on your own initiative. Stage advancement and commit are user-driven; only commit when the user explicitly asks.
- Do not declare the stage "ready" or "done" on the user's behalf. You may summarize what has been covered and gently surface gaps; the user decides when to move on.
- Do not force every recommended content section to be filled — the skeleton is a checklist of *dimensions to consider*, not required columns.

## Facilitation principles

- After each user reply, recap what has just been clarified for which character, then surface one or two unclarified dimensions next — do not dump the whole skeleton at once.
- When the user is exploring, diverge: offer two or three contrasting directions (e.g., "this protagonist could be driven by guilt, by ambition, or by inherited duty — which resonates?").
- When the user converges, lock it in via `setup.chunk.upsert` / `setup.truth.write` rather than re-asking the same question.
- Detect contradictions between newly stated character traits and prior anchors (world_background entries / earlier character entries / `prior_stage_handoffs`); surface the contradiction and ask which side wins.
- When character entries appear shallow ("brave protagonist with mysterious past"), probe specifics through scenario-style questions instead of abstract trait labels.
- Treat the recommended content skeleton as a thinking aid — suggest dimensions the user has not addressed, but never block on them.
- Stay genre-aware: if the world_background stage anchored a fantasy world, capabilities may include power systems; in a contemporary setting, prefer skills, social capital, occupation. Adapt suggestions to the world that has already been anchored.

## Recommended content skeleton (suggestions, not enforced)

Each entry in the character_design draft block follows the SetupDraftEntry shape (entry_id / entry_type / semantic_path / title / sections[]). The character_design SetupStageModule already declares default entry_types of `character`, `relationship`, `group`, and default section templates `summary` and `relationships`.

Suggested section content dimensions for a `character` entry (free-form, all optional):

- `summary.text` — One-paragraph identity blurb covering name, story role (protagonist / co-lead / antagonist / mentor / foil / supporting), and a one-sentence pitch.
- `appearance` — Visual identity that affects voice or scene staging.
- `personality` — Core personality prose.
- `background` — Origin, formative events.
- `motivation.surface` — Stated / surface goal.
- `motivation.real` — Underlying drive, fear, or need beneath the surface goal.
- `capabilities` — Strengths, skills, resources, and meaningful limits. Genre-adaptive.
- `voice` — Diction, pace, signature phrasing cues.
- `world_fit` — How this character is shaped by / pushes against anchored world or rule facts.
- `extras` — Free-form genre-specific dimensions (修真境界 / 都市职业 / 悬疑秘密 / etc.).

For a `relationship` entry, fill the `relationships` section with the other character refs, relation type, and a one-line note. For a `group` entry, list members and shared identity / goal.

## Clarification templates

Use the Chinese template verbatim or adapt; do not translate.

- intent: Probe motivation depth (surface vs real)
  template: 角色 X 表面上想要 Y，但他真正怕失去的是什么？
- intent: Probe meaningful limits
  template: 在这个世界的规则下，X 做不到的事情是什么？哪种处境会让他最狼狈？
- intent: Probe relation type
  template: 角色 X 与 Y 的关系，最贴近合作 / 对抗 / 暧昧 / 利用 / 镜像 / 师承 中的哪一种？
- intent: Probe voice differentiation
  template: X 在紧张和放松时分别会怎么说话？跟 Y 的说话方式有什么明显差别？
- intent: Probe conflict source
  template: 这一组角色之间最尖锐的冲突来自哪里：利益、价值观、过去的恩怨，还是性格相克？
- intent: Surface contradiction with anchored world facts
  template: 你刚才提到 X 会用魔法，但 world_background 阶段我们说过这个世界没有魔法体系。要更新世界设定还是改 X 的能力线？
- intent: Diverge candidates
  template: 关于 X 的核心动机，有三个方向可以走：A 复仇驱动，B 救赎驱动，C 守护驱动。你倾向哪个？或者还有其他方向？
```

## Out of Scope

1. 其他 8 个 SetupStageId 的 SkillPack 内容（world_background / plot_blueprint / writer_config / worker_config / overview / activate / rp_interaction_contract / trpg_rules）。
2. SkillPack 自动 / 启发式选择机制（Pilot 完全由 stage_id 字段驱动）。
3. SkillPack persona library 多 persona / fusion 机制（Pilot 不预留数据结构槽位；未来可在 SKILL.md sections 表达）。
4. SkillPack preset 库（萧谴 character preset 设计的实装拆为后续任务；可作为 `references/` 子目录的 markdown 文件）。
5. **SkillPack 接管 tool_scope**（明确不做，per spec `rp-setup-agent-strict-truth-write-tool-pilot.md`：stage 写入由 `setup.truth.write + runtime 注入 stage_id + block_type=stage_draft` 处理，不拆独立 patch tool；SkillPack 不携工具白名单字段）。
6. `SetupStepId` 枚举弃用（不本任务做）。
7. 4 个旧 draft 模型迁移到 SetupStageDraftBlock 统一容器（粒度统一收尾任务负责）。
8. SkillPack 行为层 eval cases（`backend/rp/eval/cases/setup/skill_pack/<stage_id>/*.json` 路径预定，case JSON 与 ragas 评测拆后续任务）。
9. SkillPack 卸载时的 "former skill summary" 软过渡（明确不做，硬卸载）。
10. Agent 自动 ready 判定 / 自动 `setup.proposal.commit`（明确不做；用户主动权）。
11. `_stage_overlay` 整体弃用（Pilot 仅在命中 SkillPack 时短路；9 个 stage 全部落地 SkillPack 后再整体弃用）。
12. mode × stage 注册表（Pilot 简单单键 SetupStageId；未来若 SkillPack 需 mode 维度差异可升级）。

## Deliverables

1. **新增 spec**：`.trellis/spec/backend/rp-setup-agent-stage-skill-pack.md`（运行时契约：SkillPack 文件格式 / 装载机制 / 与 `SetupStageModule` 的关系 / 与 `_stage_overlay` 的方案 A 替代关系 / 与 `setup.truth.write strict pilot` 的解耦说明 / Eval 模块对接预留）。
2. **后端代码**：
   - 新建 `backend/rp/agent_runtime/skill_packs/{__init__.py, registry.py, character_design/SKILL.md}`
   - 改造 `SetupAgentPromptService._stage_overlay(...)` —— 命中 SkillPack 时短路返回 `render_skill_pack(record)` 输出
   - 改造 `SetupAgentPromptService.build_system_prompt(...)` —— 命中 SkillPack 时在 base prompt 开头插入 specialist-hat 引导句
   - **可选**：`SetupRuntimeAdapter.build_turn_input` 在 metadata 加 `skill_pack_name`（trace 用）
3. **测试**：
   - `backend/rp/tests/test_skill_packs_registry.py`（新文件）：
     - `STAGE_SKILL_PACKS[SetupStageId.CHARACTER_DESIGN]` 存在；name / stage_id / description / body 全部非空且符合 PRD 内容
     - `render_skill_pack(record)` 输出**不出现**字面量 "You are"；包含 `[Stage Skill Pack: character-design.v1]` 标记段；包含 "## Specialist hat" / "## Objectives" / "## Forbidden" / "## Facilitation principles" / "## Recommended content skeleton" / "## Clarification templates" 6 个 section header；包含 forbidden 中"不自动 commit / 不自动判 ready"两条；包含 `motivation.real`、`world_fit` 等关键关键词；包含中文 clarification 模板原文（如 "角色 X 表面上想要 Y..."）
   - `backend/rp/tests/test_setup_agent_prompt_service.py`：
     - `current_stage=SetupStageId.CHARACTER_DESIGN` 时 system prompt 中：
       - 出现 `[Stage Skill Pack: character-design.v1]` 标记段
       - 出现 specialist-hat 引导句（如 "While in this stage, take on the perspective of the Specialist hat..."）
       - **不出现** character_design 的现行 `_stage_overlay` 原文（如 "Focus on stable character, relationship..."）
       - 仅出现一个 "You are SetupAgent" 身份声明
     - `current_stage=None` 或非注册 stage 时 system prompt 与现行**字节级一致**（保留原 `_stage_overlay` prose；无 specialist-hat 引导句；无 `[Stage Skill Pack` 字串）
4. **更新 `.trellis/spec/backend/index.md`**：追加新 spec 条目与 pre-development checkbox。

## Acceptance

1. 当 turn 携带 `current_stage = SetupStageId.CHARACTER_DESIGN` 时，后端 system prompt 中出现 `[Stage Skill Pack: character-design.v1]` 渲染段。
2. 命中 SkillPack 时**不**出现 character_design 的现行 `_stage_overlay` 原文（方案 A 短路验证）。
3. system prompt 中只出现一个 "You are SetupAgent" 身份声明；SkillPack body 不写 "You are X"。
4. 用户切到任一非 character_design stage（或 stage_id 为 None）后，下一 turn 的 system prompt 中**完全不出现** SkillPack 任何内容（硬卸载）；同时**恢复**该 stage 的现行 `_stage_overlay` prose。
5. 未升级前端 / `current_stage=None` 的 turn 行为与现行**字节级**一致，无回归。
6. `character_design` SkillPack 文件位于 `backend/rp/agent_runtime/skill_packs/character_design/SKILL.md`，frontmatter 含 `name / stage_id / description`（无 `required_tools_stage_specific`）；body 含本 PRD 列出的 6 个 section。
7. SkillPack 不引入任何让 agent 自动判 ready / 自动 commit / 自动声明阶段完成的语句。
8. SkillPack 不携工具白名单字段、不影响 `build_setup_agent_tool_scope` 行为。
9. 新增 spec 与 index 检查项就位，单元测试通过。
