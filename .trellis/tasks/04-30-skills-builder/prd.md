# Skills Builder

## Goal

为 SetupAgent 引入 **Stage SkillPack** 概念，使 agent 在不同 setup wizard stage 上装载专业能力包（persona + content 骨架建议 + 引导风格 + 澄清模板 + 禁区），用完即卸。本任务只交付：

1. 运行时 SkillPack 装载 / 硬卸载机制（前端 wizard_stage → 后端 turn 输入 → SetupAgentPromptService 装入 system prompt）。
2. 一个完整 SkillPack 内容样板：**`characterDesign`**（角色设定 wizard stage）。

不在本任务范围内：其他 6 个 wizard stage 的 SkillPack 内容；SkillPack 自动选择 / 启发式判定；现行 `SetupStepId` 枚举重构；`foundation` 内 rule domain 是否独立成 stage 的决定；preset 库的实装；硬性 ready 阈值与 agent 自动 commit 判定。

## Current Code Baseline

### 后端 SetupStepId（`backend/rp/models/setup_workspace.py:32-37`）

四个粗粒度 step：

```python
class SetupStepId(StrEnum):
    STORY_CONFIG = "story_config"
    WRITING_CONTRACT = "writing_contract"
    FOUNDATION = "foundation"
    LONGFORM_BLUEPRINT = "longform_blueprint"
```

### 前端 Wizard Stage（`lib/pages/prestory_setup_page.dart:2407-2419`）

七个 UX 级 stage，是用户实际感知的"步骤"粒度：

```dart
enum _SetupWizardStage {
  worldBackground('世界观背景'),
  characterDesign('角色设定'),
  plotBlueprint('伏笔剧情设计'),
  writerConfig('作家配置'),
  workerConfig('worker配置'),
  overview('全览'),
  activate('activate');
}
```

### 现行映射（`lib/pages/prestory_setup_page.dart:1550-1568`）

前端把 7 个 wizard stage 折叠成 4 个后端 SetupStepId：

| Wizard Stage | 落到的 SetupStepId |
|---|---|
| worldBackground | foundation |
| **characterDesign** | **foundation** ← 与 worldBackground 同坑 |
| plotBlueprint | longform_blueprint |
| writerConfig | writing_contract |
| workerConfig | story_config |
| overview / activate | null |

进一步，`_characterFoundationEntries` 用 `domain == "character"` 过滤，`_worldFoundationEntries` 用 `domain != "character"` 过滤（`prestory_setup_page.dart:1737-1750`），即前端 worldBackground = foundation 中 world+rule 两个 domain 合并。

### 关键缺口

前端在 turn 请求里**只传 `target_step`（4 stage 之一），不传 `wizard_stage`**。后端 `SetupAgentExecutionService` / `SetupAgentPromptService` 因此**完全看不到** worldBackground / characterDesign 的区别 —— 两者都是 `target_step="foundation"`。Stage-level skill 装载机制无从触发。

### 现行 stage 区分点（仅 prose）

`backend/rp/services/setup_agent_prompt_service.py::_stage_overlay`（`L82-103`）按 `SetupStepId` 给一段 3-5 行的 prose overlay。它只到 4-stage 粒度，不带 persona、不带骨架建议、不带引导风格、不带澄清模板。

### Reference: SillyTavern 写卡工具的 character 设计哲学（背景研究）

参考 `C:/Users/55473/Desktop/4.5.1/萧谴写卡助手版_V4.5.1` 一手数据：业界主流 character card 工具走 **preset / tag 驱动 + 自由 prose** 路线，而非刚性字段 schema。这个调研结论直接影响 SkillPack 设计：character entry `content` 字典只有"推荐骨架 + 题材自适应 extras"，不强制刚性 schema、不做 pydantic 验证。

## Concept: Stage SkillPack

### Definition

SkillPack = 绑定到某一 wizard_stage 的**装载式专家能力包**。一个 turn 至多装载一个 SkillPack（与当前 `wizard_stage` 一一对应）。Wizard stage 切换 → 旧 SkillPack 不再出现在 system prompt（硬卸载），新 SkillPack 装入。

### 设计原则

1. **不当裁判**：SkillPack **不**给 agent 自动判定 ready / commit 的硬阈值。Stage 推进与 commit 主动权在用户手里。
2. **引导优先**：SkillPack 提供 persona + 引导风格描述 + 澄清问句模板，让 agent **引导用户、追问盲区、发散思路**，不做"卡流程"的检查表。
3. **骨架推荐而非强制**：content 字段提建议而不强制 schema；题材敏感的字段走 `extras` 自由扩展槽。
4. **硬卸载**：stage 切换后旧 SkillPack 字符级不出现在新 system prompt 中。
5. **语言分层**：persona / objectives / forbidden / facilitation 用英文（LLM 系统级指令更稳）；clarification_templates 用中文（直接发给中文用户的话术）。

### Data structure（运行时 contract）

```python
class FieldHint(BaseModel):
    """One recommended field within a stage's content skeleton.
    Recommendation only — never a pydantic-validated requirement on the entry."""
    path: str                                     # e.g. "content.identity.name"
    nullable: bool = True                         # 全部默认可空
    note: str                                     # short EN note: what this field carries

class ClarificationTemplate(BaseModel):
    """Reusable prompt the agent may adapt when asking the user."""
    intent: str                                   # EN, why ask
    template: str                                 # ZH, the actual question form

class StageSkillPack(BaseModel):
    name: str                                     # e.g. "character_design.v1"
    wizard_stage: str                             # e.g. "characterDesign"
    persona: str                                  # EN persona prose
    objectives: list[str]                         # EN, what this stage tries to converge
    forbidden: list[str]                          # EN, hard taboos in this stage
    facilitation_principles: list[str]            # EN, how the agent leads/asks/diverges
    content_skeleton: list[FieldHint]             # recommended (non-enforced) entry fields
    clarification_templates: list[ClarificationTemplate]
    # —— deferred slots (Pilot 不实装，但数据结构预留) ——
    personas: list[dict] | None = None            # multi-persona library, future
    selection_strategy: str | None = None         # "default"|"ask"|"auto"|"fusion", future
    preset_library: list[dict] | None = None      # tag-driven preset library, future
```

> **Drop**：原 `ready_criteria: list[str]` 字段从数据结构移除（按 C 转向，不当裁判）。
> **Add**：`facilitation_principles`（agent 引导风格） + `content_skeleton`（推荐骨架）。

### Loading / unloading 语义

- **装载**：当 turn 请求带 `wizard_stage = X` 且存在对应 SkillPack 时，`SetupAgentPromptService.build_system_prompt(...)` 在现有 `_stage_overlay` 之后追加 SkillPack 渲染段。
- **硬卸载**：下一 turn 若 `wizard_stage` 变更或为 None，新 system prompt 不再包含旧 SkillPack 任何内容。无 "former skill summary" 软过渡（如有需要走 `prior_stage_handoffs`，那是已存在的 stage 级 handoff，不在本任务变更范围）。
- **未匹配**：`wizard_stage` 为 None 或在 SkillPack 注册表中无对应条目时，behavior 与现行一致（仅基础 prompt + `_stage_overlay`）。

### Render 形态（追加到 system prompt 的段落）

```
[Stage Skill Pack: character_design.v1]
Persona:
{persona}

Objectives:
- {objectives[0]}
- ...

Forbidden:
- {forbidden[0]}
- ...

Facilitation principles:
- {facilitation_principles[0]}
- ...

Recommended content skeleton (suggestions only, not a hard schema):
- {content_skeleton[0].path} — {content_skeleton[0].note}
- ...

Clarification templates (use the Chinese template verbatim or adapt; do not translate):
- intent: {clarification_templates[0].intent}
  template: {clarification_templates[0].template}
- ...
[/Stage Skill Pack]
```

### 注册表

后端维护 `STAGE_SKILL_PACKS: dict[str, StageSkillPack]`，key 为 wizard_stage name。Pilot 只注册 `characterDesign`。

## Pilot Scope: characterDesign SkillPack

### Persona (EN)

```
You are a senior dramatist and character writer. Your craft is shaping believable
people: motivation arcs, internal contradictions, voice, relational tension, and
how each character lives inside the story's world rules. In this turn you stay
strictly inside the character-design stage — you elicit, propose, and refine
character entries; you do not write scenes, dialogue, or plot beats.
```

### Objectives (EN)

1. Help the user articulate the core cast — at least the protagonist, plus other characters the story actually needs.
2. For each character, surface stable identity, motivation (surface vs underlying), capabilities and meaningful limits, voice cues, and how the character fits the already-anchored world / rules.
3. Surface relational tension and conflict sources between characters that downstream plot stages can build on.

### Forbidden (EN)

1. Do not write narrative prose, scenes, or in-story dialogue.
2. Do not invent or assume world or rule facts that the worldview stage has not yet anchored — defer to that stage instead.
3. Do not mutate `writing_contract` or `longform_blueprint` drafts; this stage only produces / refines `FoundationEntry { domain="character" }` items.
4. Do not call `setup.proposal.commit` on your own initiative. Stage advancement and commit are user-driven; only commit when the user explicitly asks.
5. Do not declare the stage "ready" or "done" on the user's behalf. You may summarize what has been covered and gently surface gaps; the user decides when to move on.
6. Do not force every recommended field to be filled — the content skeleton is a checklist of *dimensions to consider*, not required columns.

### Facilitation principles (EN)

1. After each user reply, recap what has just been clarified for which character, then surface one or two unclarified dimensions next — do not dump the whole skeleton at once.
2. When the user is exploring, diverge: offer two or three contrasting directions (e.g., "this protagonist could be driven by guilt, by ambition, or by inherited duty — which resonates?").
3. When the user converges, lock it in via `setup.chunk.upsert` / `setup.truth.write` rather than re-asking the same question.
4. Detect contradictions between newly stated character traits and prior anchors (worldview / earlier character entries / `prior_stage_handoffs`); surface the contradiction and ask which side wins.
5. When `domain="character"` entries appear shallow ("brave protagonist with mysterious past"), probe specifics through scenario-style questions instead of abstract trait labels.
6. Treat the recommended `content` skeleton as a thinking aid — suggest dimensions the user has not addressed, but never block on them.
7. Stay genre-aware: if the worldview stage anchored a fantasy world, capabilities may include power systems; in a contemporary setting, prefer skills, social capital, occupation. Adapt suggestions to the world that has already been anchored.

### Recommended content skeleton (suggestions, not enforced)

每条都是 `FieldHint { path, nullable=True, note }`。Agent 把它当"考虑维度"，不当必填栏。

| path | note (EN) |
|---|---|
| `content.identity.name` | Display name. |
| `content.identity.gender` | Optional gender / presentation. |
| `content.identity.role_in_story` | Story role: protagonist / co-lead / antagonist / mentor / foil / supporting / one-shot / ... |
| `content.appearance` | Free-form prose; visual identity that affects voice or scene staging. |
| `content.personality` | Core personality prose. |
| `content.background` | Origin, formative events. |
| `content.motivation.surface` | Stated / surface goal. |
| `content.motivation.real` | Underlying drive, fear, or need beneath the surface goal. |
| `content.capabilities` | Strengths, skills, resources, *and* meaningful limits. Genre-adaptive. |
| `content.relations` | List of relations: each item references another character + relation type + one-line note. |
| `content.voice` | Diction, pace, signature phrasing cues. |
| `content.world_fit` | How this character is shaped by / pushes against anchored world or rule facts. |
| `content.extras` | Free-form dict for genre-specific fields (修真境界 / 都市职业 / 悬疑秘密 / etc.). |

### Clarification templates (intent EN, template ZH)

| intent | template |
|---|---|
| Probe motivation depth (surface vs real) | 角色 X 表面上想要 Y，但他真正怕失去的是什么？ |
| Probe meaningful limits | 在这个世界的规则下，X 做不到的事情是什么？哪种处境会让他最狼狈？ |
| Probe relation type | 角色 X 与 Y 的关系，最贴近合作 / 对抗 / 暧昧 / 利用 / 镜像 / 师承 中的哪一种？ |
| Probe voice differentiation | X 在紧张和放松时分别会怎么说话？跟 Y 的说话方式有什么明显差别？ |
| Probe conflict source | 这一组角色之间最尖锐的冲突来自哪里：利益、价值观、过去的恩怨，还是性格相克？ |
| Surface contradiction with anchored facts | 你刚才提到 X 会用魔法，但 worldview 阶段我们说过这个世界没有魔法体系。要更新世界设定还是改 X 的能力线？ |
| Diverge candidates | 关于 X 的核心动机，有三个方向可以走：A 复仇驱动，B 救赎驱动，C 守护驱动。你倾向哪个？或者还有其他方向？ |

## Backend & Frontend Contract Changes

### Backend

1. `SetupAgentTurnRequest`（`backend/rp/models/setup_agent.py`）新增字段 `wizard_stage: str | None = None`，默认 None 保留与未升级前端的兼容。
2. `SetupAgentExecutionService` 把 `wizard_stage` 透传到 prompt assembly path（不影响 tool_scope、不影响 graph routing）。
3. `SetupAgentPromptService.build_system_prompt(...)` 新增 `wizard_stage: str | None` 形参；若命中 `STAGE_SKILL_PACKS[wizard_stage]`，在 `_stage_overlay` 之后追加 SkillPack 渲染段；未命中时 behavior 与现行字节级一致。
4. 新增 `backend/rp/services/setup_stage_skill_packs.py`：定义 `StageSkillPack` / `FieldHint` / `ClarificationTemplate` 数据结构、注册表 `STAGE_SKILL_PACKS`、`render_skill_pack(...)` 渲染函数。Pilot 只注册 `characterDesign`。

### Frontend

1. `lib/pages/prestory_setup_page.dart` 在调用 setup turn 入口处补传 `wizardStage = _selectedStage.name`（与 `_targetStepForStage` 同处）。
2. AI 客户端 / dio 调用层：`RpSetupAgentTurnRequest` 序列化新增 `wizard_stage` 字段。

## Out of Scope

1. 其他 6 个 wizard stage 的 SkillPack 内容（worldBackground / plotBlueprint / writerConfig / workerConfig / overview / activate）。
2. SkillPack 自动 / 启发式选择机制（Pilot 完全由前端 wizard_stage 字段驱动）。
3. SkillPack persona library 多 persona / fusion 选择机制（数据结构 `personas` / `selection_strategy` 槽位预留 None，逻辑不实装）。
4. SkillPack preset 库（数据结构 `preset_library` 槽位预留 None，参考萧谴 character preset 设计的实装拆为后续任务）。
5. `SetupStepId` 枚举重构（不动）。
6. `_targetStepForStage` 现行折叠映射的语义调整（不动）。
7. `FoundationEntry.content` dict 的强 schema 化与 pydantic 验证（明确不做；SkillPack 的 `content_skeleton` 仅是建议）。
8. SkillPack 卸载时的"former skill summary"软过渡（明确不做，硬卸载）。
9. SkillPack 与 `tool_scope` / `setup.discussion.update_state` 的进一步联动（沿用现有 stage-aware tool scope 行为）。
10. Agent 自动 ready 判定 / 自动 `setup.proposal.commit`（明确不做；用户主动权）。

## Deliverables

1. 新增 spec：`.trellis/spec/backend/rp-setup-agent-stage-skill-pack.md`（运行时契约）。
2. 后端代码：`backend/rp/services/setup_stage_skill_packs.py` + `SetupAgentPromptService` / `SetupAgentTurnRequest` / `SetupAgentExecutionService` 接入。
3. 前端代码：`prestory_setup_page.dart` 与 setup turn 客户端层补传 `wizard_stage`。
4. 测试：
   - `backend/rp/tests/test_setup_agent_stage_skill_packs.py`（新文件）：
     - `STAGE_SKILL_PACKS["characterDesign"]` 存在；persona / objectives / forbidden / facilitation_principles / content_skeleton / clarification_templates 全部非空。
     - `render_skill_pack(pack)` 输出包含本 PRD 列出的 persona、forbidden 第 4/5 条（不自动 commit / 不自动判 ready）、`content.motivation.real` 等关键标识，且包含中文 clarification 模板原文。
     - `personas` / `selection_strategy` / `preset_library` 槽位为 None。
   - `backend/rp/tests/test_setup_agent_prompt_service.py`：
     - `wizard_stage="characterDesign"` 时 system prompt 中包含 `[Stage Skill Pack: character_design.v1]` 标记段及关键 persona / forbidden 字符串。
     - `wizard_stage=None` 或未注册值时 system prompt 与现行字节级一致（无 `[Stage Skill Pack` 字串）。
     - 同 turn 仅装载一个 SkillPack；不同 wizard_stage 调用之间互不污染（同一 prompt service 实例先后两次调用不残留）。
   - `backend/rp/tests/test_setup_agent_execution_service_v2.py`：新字段 `wizard_stage` 从 `SetupAgentTurnRequest` 透传到 prompt service，渲染段落出现在最终 system prompt 中。
5. `.trellis/spec/backend/index.md` 索引追加新 spec 条目与 pre-development checkbox。

## Acceptance

1. 前端在 characterDesign stage 发起 turn 时，后端 system prompt 中出现 `[Stage Skill Pack: character_design.v1]` 渲染段，包含本 PRD 列出的 persona / forbidden / facilitation / content skeleton / clarification 模板核心字段。
2. 用户切到任一非 characterDesign wizard stage（或 wizard_stage 为 None）后，下一 turn 的 system prompt 中**完全不出现** `[Stage Skill Pack` 字符串、不出现 character SkillPack 任何 persona / facilitation / clarification 内容（硬卸载）。
3. 未升级前端（不传 wizard_stage）的 turn 行为与现行**字节级**一致，无回归。
4. `characterDesign` SkillPack 的 persona / objectives / forbidden / facilitation_principles / content_skeleton / clarification_templates 与本 PRD 内容一致。
5. SkillPack 数据结构中 `personas` / `selection_strategy` / `preset_library` 槽位存在但 Pilot 全部为 None。
6. SkillPack 不引入任何让 agent 自动判 ready / 自动 commit / 自动声明阶段完成的语句。
7. 新增 spec 与 index 检查项就位，单元测试通过。
