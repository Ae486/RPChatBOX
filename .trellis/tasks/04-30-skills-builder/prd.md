# Skills Builder

## Goal

为 SetupAgent 引入 **Stage SkillPack** 概念，让 agent 在 setup 各 stage 装载专业能力包（persona + 引导风格 + 工具白名单），用完即卸。本任务交付：

1. SkillPack 文件格式（Anthropic Skill 风格 markdown + frontmatter，stage 级一一对应）。
2. SkillPack 装载机制（按 `SetupStageId` 查表 + system prompt 装入 + tool_scope 联动）。
3. 一个完整 Pilot：**`character_design`** stage 的 SkillPack。

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
- `SETUP_STEP_PATCH_TOOLS`（4-stage 旧表，仍是 patch 工具的唯一来源）
- `SETUP_STAGE_PATCH_TOOLS`（新表，**所有 9 个 stage 当前都是空 tuple**，等 SkillPack 填）
- `build_setup_agent_tool_scope(current_step)` 优先查旧表、回退查新表，最终 fallback 到全集

### 6. 旧字段共存（过渡期）

下面这些字段尚未迁移到 SetupStageId：

- `SetupAgentTurnRequest.target_step: SetupStepId | None`（**没有** `target_stage` 字段）
- `SetupWorkspace.current_step: SetupStepId`（必填）/ `current_stage: SetupStageId | None`（nullable 副本）
- 4 个旧 draft 模型（`StoryConfigDraft / WritingContractDraft / FoundationDraft / LongformBlueprintDraft`）仍存在并被 `SetupWorkspace` 引用
- 4 个旧 patch 工具（`setup.patch.story_config / writing_contract / foundation_entry / longform_blueprint`）仍是底层唯一可用 patch
- `_legacy_step_for_stage` 桥接 SetupStageId → SetupStepId

**直接后果**：SkillPack 想做 "stage 用完即扔工具" 必须解决 "如何向 LLM 暴露专属于 character_design 的 patch 工具"。当前**没有** `setup.patch.character_design.entry` 这种工具，只有 `setup.patch.foundation_entry`。Pilot 期 SkillPack 复用 `setup.patch.foundation_entry`，通过 forbidden / facilitation prose 软性约束 agent 写 character entry。

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
| Frontmatter | `name`, `description` | `name`, `description`, `stage_id`, `required_tools_stage_specific` | 一致（多 2 个路由字段）|
| Body 结构 | 自由 markdown | 自由 markdown（约定 sections）| 一致 |
| 装载到哪 | system prompt | system prompt（替代原 `_stage_overlay` 槽位）| 一致 |
| 用完即卸 | 是 | 是（硬卸载）| 一致 |
| **选定机制** | **LLM 看 description 自选** | **后端按 SetupStageId 查表** | **唯一差异点** |

**为何选 deterministic-by-stage**：UI 已显式告诉系统 "用户在 character_design stage"（前端 wizard 选中 + 后端 `current_stage` 字段），让 LLM 再"猜一遍"是冗余。

### 本任务专属设计原则

1. **不当裁判**：SkillPack **不**给 agent 自动判定 ready / commit 的硬阈值。
2. **引导优先**：SkillPack 让 agent 引导用户、追问盲区、发散思路，不做"卡流程"的检查表。
3. **骨架推荐而非强制**：content skeleton 提建议而不强制 schema；题材敏感字段走 `extras` 自由扩展槽。
4. **硬卸载**：stage 切换后旧 SkillPack 字符级不出现在新 system prompt；tool_scope 同步切换。
5. **语言分层**：persona / objectives / forbidden / facilitation 用英文；clarification_templates 用中文。
6. **替代 `_stage_overlay`**：命中 SkillPack 时跳过 `_stage_overlay`，避免双套 stage prose 互冲。
7. **persona swap 而非 You-are 互冲**：base prompt 开头加 "specialist-hat 槽位"，SkillPack body 不写 "You are X"。
8. **工具用完即扔**：SkillPack 在 frontmatter 声明 `required_tools_stage_specific`；tool_scope 优先读 SkillPack。
9. **与 `SetupStageModule` 互补**：Module 是数据层（display_name / draft_block_type / default_entry_types / section_templates），SkillPack 是能力层（persona / 收敛策略 / 工具白名单）。两者一一对应同一个 SetupStageId。

## 文件形态与目录结构

```
backend/rp/services/setup_stage_skill_packs/
  __init__.py                                  # 启动扫描目录、构 REGISTRY
  registry.py                                  # SkillPackRecord + load_registry()
  character_design/
    SKILL.md                                   # Pilot 唯一交付的内容文件
  # 未来：world_background/SKILL.md / plot_blueprint/SKILL.md / ...
```

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
required_tools_stage_specific:
  - setup.patch.foundation_entry           # 过渡期使用（带 prose 约束 domain=character）
                                           # 粒度统一收尾任务把它替换为 stage 级新 patch 工具
---
```

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
# backend/rp/services/setup_stage_skill_packs/registry.py

class SkillPackRecord(BaseModel):
    """In-memory representation of a parsed SKILL.md."""
    model_config = ConfigDict(extra="forbid")

    name: str                                              # 来自 frontmatter
    stage_id: SetupStageId                                 # 来自 frontmatter
    description: str = ""                                  # 来自 frontmatter；仅文档/日志，不渲染
    body: str                                              # markdown 主体（去掉 frontmatter）
    required_tools_stage_specific: tuple[str, ...] = ()    # 来自 frontmatter

STAGE_SKILL_PACKS: dict[SetupStageId, SkillPackRecord]     # 启动时由 load_registry() 填充
```

唯一 pydantic 类。无 `FieldHint` / `ClarificationTemplate` 等子结构 —— 这些都是 markdown body 里的列表项，按需阅读，不需要程序化访问。

## 装载 / 卸载语义

### 装载（命中）

当当前 turn 的 stage 命中 `STAGE_SKILL_PACKS[stage_id]` 时：

1. **system prompt** 改造（详见下文 Base Prompt Refactor）：
   - base prompt 开头追加 specialist-hat 引导句
   - 在原 `_stage_overlay` 槽位插入 SkillPack body 的渲染段（不再渲染原 `_stage_overlay`）
2. **tool_scope** 改造：
   - `build_setup_agent_tool_scope` 优先读 SkillPack 的 `required_tools_stage_specific`
   - 与 `SETUP_READ_ONLY_MEMORY_TOOLS` + `SETUP_SHARED_PRIVATE_TOOLS` 合并为最终 visible 列表

### 硬卸载（未命中或切换）

下一 turn 若 stage_id 变更或为 None / 不在注册表：

- system prompt 中**字符级不出现**旧 SkillPack 任何内容、specialist-hat 引导句、`[Stage Skill Pack` 标记段
- tool_scope 回退到现行行为：`SETUP_STEP_PATCH_TOOLS` → `SETUP_STAGE_PATCH_TOOLS` → 全集 fallback 链

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

1. **新增** `backend/rp/services/setup_stage_skill_packs/` 目录与 `character_design/SKILL.md` 文件。
2. **新增** `backend/rp/services/setup_stage_skill_packs/registry.py`：定义 `SkillPackRecord`、`load_registry()`、`STAGE_SKILL_PACKS` 常量、`render_skill_pack(record) -> str`、`get_skill_pack_for_stage(stage_id) -> SkillPackRecord | None`。
3. **改造** `SetupAgentPromptService.build_system_prompt(...)`：
   - 新增 `stage_id: SetupStageId | None = None` 形参
   - 命中 SkillPack 时：开头插入 specialist-hat 引导句；`_stage_overlay` 槽位插入 SkillPack body 渲染段
   - 未命中时：行为与现行字节级一致（保留原 `_stage_overlay`）
4. **改造** `build_setup_agent_tool_scope(...)`（在 `backend/rp/agent_runtime/profiles.py`）：
   - 新增 `stage_id: SetupStageId | None = None` 形参
   - 命中 SkillPack 时：返回 `SETUP_READ_ONLY_MEMORY_TOOLS + SETUP_SHARED_PRIVATE_TOOLS + pack.required_tools_stage_specific`
   - 未命中时：保留现有行为

### Backend 桥接（依赖粒度统一收尾任务）

下面字段是 SkillPack 路由的入口，**当前后端未提供**，需协调 / 后续任务补：

5. `SetupAgentTurnRequest.target_stage: SetupStageId | None`（新字段）
6. `SetupGraphState.target_stage: str | None`（state TypedDict 加字段）
7. `SetupGraphRunner._initial_state` 复制 target_stage
8. `SetupGraphNodes._request_from_state` 反序列化 target_stage
9. `SetupRuntimeAdapter.build_turn_input` 把 stage_id 透传给 `build_system_prompt` 与 `build_setup_agent_tool_scope`，并在 `RpAgentTurnInput.metadata` 写 `stage_id` / `skill_pack_name` 供 trace
10. API 路由 `backend/api/rp_setup.py` 的 langfuse `metadata` 加 `stage_id`

详见 `docs/research/rp-redesign/agent/cooperation/claude-skill-pack-pipeline-integration-proposal.md`（已基于现状更新）。

### Frontend（本任务范围内最小改动）

1. `lib/pages/prestory_setup_page.dart` 在 turn 调用入口处补传 `targetStage`：
   - 来源 = `_selectedStage` 转换到 SetupStageId snake_case 字符串值（`worldBackground` → `"world_background"`）
   - 字段名 = `target_stage`（与后端 `SetupAgentTurnRequest.target_stage` 一致）
2. AI 客户端 / dio 调用层：`RpSetupAgentTurnRequest` 序列化新增 `target_stage` 字段。

## Pilot Scope: character_design SkillPack 内容

### 以 markdown 写在 `backend/rp/services/setup_stage_skill_packs/character_design/SKILL.md`

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
required_tools_stage_specific:
  - setup.patch.foundation_entry
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
5. `SetupStepId` 枚举弃用（不本任务做）。
6. 4 个旧 draft 模型（StoryConfigDraft 等）迁移到 SetupStageDraftBlock 统一容器（粒度统一收尾任务负责）。
7. 4 个旧 patch 工具拆分为 stage 级新 patch 工具（如 `setup.patch.character_design.entry`）—— 粒度统一收尾任务负责；本任务期 character_design SkillPack 复用 `setup.patch.foundation_entry`。
8. SkillPack 行为层 eval cases（`backend/rp/eval/cases/setup/skill_pack/<stage_id>/*.json` 路径预定，case JSON 与 ragas 评测拆后续任务）。
9. SkillPack 卸载时的 "former skill summary" 软过渡（明确不做，硬卸载）。
10. Agent 自动 ready 判定 / 自动 `setup.proposal.commit`（明确不做；用户主动权）。
11. `_stage_overlay` 整体弃用（Pilot 仅在命中 SkillPack 时跳过；9 个 stage 全部落地 SkillPack 后再做整体弃用）。
12. mode × stage 注册表（Pilot 简单单键 SetupStageId；未来若 SkillPack 需 mode 维度差异可升级）。

## Deliverables

1. **新增 spec**：`.trellis/spec/backend/rp-setup-agent-stage-skill-pack.md`（运行时契约：SkillPack 文件格式 / 装载机制 / 工具白名单 / 与 `SetupStageModule` 的关系 / 与 `_stage_overlay` 的替代关系 / Eval 模块对接预留）。
2. **更新 spec**：`.trellis/spec/backend/rp-setup-agent-stage-aware-tool-scope.md` 加一节 "SkillPack-driven Tool Scope"，说明 SkillPack 命中时优先读其 `required_tools_stage_specific`。
3. **后端代码**：
   - 新建 `backend/rp/services/setup_stage_skill_packs/{registry.py, character_design/SKILL.md}`
   - 改造 `SetupAgentPromptService.build_system_prompt(...)`
   - 改造 `build_setup_agent_tool_scope(...)`
4. **协调依赖**（不在本任务交付，但 `claude-skill-pack-pipeline-integration-proposal.md` 列出，需粒度统一收尾任务承接）：
   - `SetupAgentTurnRequest.target_stage` 字段
   - `SetupGraphState.target_stage` + 透传链
   - API langfuse metadata 加 stage_id
   - adapter metadata 加 skill_pack_name
5. **前端代码**：
   - `prestory_setup_page.dart` 在 turn 调用处补传 `targetStage`（snake_case stage_id）
   - 客户端层 `RpSetupAgentTurnRequest` 序列化新字段
6. **测试**：
   - `backend/rp/tests/test_setup_stage_skill_packs.py`（新文件）：
     - `STAGE_SKILL_PACKS[SetupStageId.CHARACTER_DESIGN]` 存在；name / stage_id / description / body / required_tools_stage_specific 全部非空且符合 PRD 内容。
     - `render_skill_pack(record)` 输出**不出现**字面量 "You are"；包含 "Specialist hat" 段；包含 forbidden 中"不自动 commit / 不自动判 ready"两条；包含 `motivation.real`、`world_fit` 等关键关键词；包含中文 clarification 模板原文。
   - `backend/rp/tests/test_setup_agent_prompt_service.py`：
     - `stage_id=SetupStageId.CHARACTER_DESIGN` 时 system prompt 中：
       - 出现 `[Stage Skill Pack: character-design.v1]` 标记段；
       - 出现 specialist-hat 引导句；
       - **不出现** foundation 的 `_stage_overlay` 原文；
       - 仅出现一个 "You are SetupAgent" 身份声明。
     - `stage_id=None` 或未注册值时 system prompt 与现行**字节级一致**。
   - `backend/rp/tests/test_setup_agent_tool_scope.py`：
     - `stage_id=SetupStageId.CHARACTER_DESIGN` 时 `build_setup_agent_tool_scope(...)` 返回的列表包含 `setup.patch.foundation_entry` 与共享 tools。
     - 不命中 SkillPack 时回退到现行行为。
7. **更新 `.trellis/spec/backend/index.md`**：追加新 spec 条目与 pre-development checkbox。

## Acceptance

1. 当 turn 携带 `stage_id = SetupStageId.CHARACTER_DESIGN` 时，后端 system prompt 中出现 `[Stage Skill Pack: character-design.v1]` 渲染段。
2. 命中 SkillPack 时**不**出现现行 foundation `_stage_overlay` 原文。
3. system prompt 中只出现一个 "You are SetupAgent" 身份声明；SkillPack body 不写 "You are X"。
4. tool_scope 命中 SkillPack 时包含 `setup.patch.foundation_entry` 与共享 tools；未命中时回退到现行行为。
5. 用户切到任一非 character_design stage（或 stage_id 为 None）后，下一 turn 的 system prompt 中**完全不出现** SkillPack 任何内容（硬卸载）；同时**恢复**原 `_stage_overlay`。
6. 未升级前端（不传 stage_id）的 turn 行为与现行**字节级**一致，无回归。
7. `character_design` SkillPack 文件位于 `backend/rp/services/setup_stage_skill_packs/character_design/SKILL.md`，frontmatter 含 `name / stage_id / description / required_tools_stage_specific`，body 含本 PRD 列出的全部 sections。
8. SkillPack 不引入任何让 agent 自动判 ready / 自动 commit / 自动声明阶段完成的语句。
9. 新增 spec 与 index 检查项就位，单元测试通过。
