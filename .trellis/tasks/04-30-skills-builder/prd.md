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

#### 来自 Anthropic 官方 Agent Skills 设计指南（适配后采纳）

参考 [Anthropic Skill Authoring Best Practices](https://docs.anthropic.com/en/docs/agents-and-tools/agent-skills/best-practices) 与 [Equipping Agents with Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)：

- **conciseness is core**：context window 是公共资源；每个 token 必须证明自己值。SkillPack 主体不写 LLM 已知的常识。
- **imperative / infinitive form**：主体指令用祈使句 / 不定式（"To accomplish X, do Y"），不写 "If you need to..." 这种条件句。
- **second person for agent-facing prose**：persona / objectives / forbidden / facilitation 这些是写给 agent 的，用 "You..." 第二人称（与 Anthropic plugin-dev/agent-development 一致）。
- **consistent terminology**：SkillPack 中术语固化 —— "character entry"、"core character"、"draft" 通篇统一，不混用同义词。
- **degree of freedom matched to task**：character design 任务多解，用高自由度 prose 指引；不要伪装成精确脚本。
- **avoid time-sensitive info**：不写"在 X 月之前用旧 API"这类。

#### 与 Anthropic Skill 的机制差异（有意为之）

我们的 SkillPack 与 Anthropic Skill **内容质量原则一致**，但**装载机制不同**：

| 维度 | Anthropic Skill | 我们 SkillPack |
|---|---|---|
| 选定者 | Claude (LLM) 按 description 语义匹配 | 后端按 `wizard_stage` 字段查表 |
| 候选 metadata 是否常驻 | 是（所有 skill 的 name + description 始终在 system prompt） | 否（不暴露候选列表，前端已选好） |
| 分层加载（progressive disclosure） | 三层：metadata / body / refs | 一层：命中即整段渲染 |
| 一 turn 几个 | 多个 | 至多 1 个（与 wizard_stage 1:1） |

**为何选 deterministic-by-field**：UI 上用户已经显式选了 wizard 步骤，让 agent 再"猜一遍"是冗余且可能不一致。Pilot 选最简一层装载是合理起点；progressive disclosure（如未来 character preset 库膨胀）留作后续扩展。

#### 本任务专属设计原则

1. **不当裁判**：SkillPack **不**给 agent 自动判定 ready / commit 的硬阈值。Stage 推进与 commit 主动权在用户手里。
2. **引导优先**：SkillPack 提供 persona + 引导风格描述 + 澄清问句模板，让 agent **引导用户、追问盲区、发散思路**，不做"卡流程"的检查表。
3. **骨架推荐而非强制**：content 字段提建议而不强制 schema；题材敏感的字段走 `extras` 自由扩展槽。
4. **硬卸载**：stage 切换后旧 SkillPack 字符级不出现在新 system prompt 中。
5. **语言分层**：persona / objectives / forbidden / facilitation 用英文（LLM 系统级指令更稳）；clarification_templates 用中文（直接发给中文用户的话术）。
6. **替代 _stage_overlay 而非并存**：命中 SkillPack 时**跳过**现行 `_stage_overlay`，避免双套 stage prose 互冲；未命中时走原 `_stage_overlay` 保兼容。所有 7 个 wizard stage 全部落地 SkillPack 后，`_stage_overlay` 应整体弃用（后续任务）。
7. **persona swap 而非 You-are 互冲**：base prompt 开头由 "You are SetupAgent..." 调整为带 specialist-hat 槽位（详见下文 Base Prompt Refactor 章节）；SkillPack 不再写 "You are X"，而是作为 "Specialist hat" 段被引用，避免双重身份冲突。

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
    name: str                                     # e.g. "character-design.v1"
    wizard_stage: str                             # e.g. "characterDesign"
    description: str                              # internal docs only, not rendered to prompt; WHAT + WHEN
    persona: str                                  # EN persona prose, rendered as "Specialist hat:" (NOT "You are X")
    objectives: list[str]                         # EN, what this stage tries to converge
    forbidden: list[str]                          # EN, hard taboos in this stage
    facilitation_principles: list[str]            # EN, how the agent leads/asks/diverges
    content_skeleton: list[FieldHint]             # recommended (non-enforced) entry fields
    clarification_templates: list[ClarificationTemplate]
    # —— deferred slots (Pilot 不实装，但数据结构预留) ——
    personas: list[dict] | None = None            # multi-persona library, future
    selection_strategy: str | None = None         # "default"|"ask"|"auto"|"fusion", future
    preset_library: list[dict] | None = None      # tag-driven preset library, future
    evaluation_scenarios: list[dict] | None = None  # future eval cases (see Eval Integration section)
```

> **Drop**：原 `ready_criteria: list[str]` 字段从数据结构移除（按设计原则 1，不当裁判）。
> **Add**：`description`（内部文档，不渲染入 prompt）；`facilitation_principles`（agent 引导风格）；`content_skeleton`（推荐骨架）；`evaluation_scenarios` 槽位（Pilot 永远 None，预留 eval 接口）。
> **Change**：`persona` 字段语义由"You are X"独立人格改为"specialist hat"段落，避免与 base prompt 中的 SetupAgent 身份互冲。

### Loading / unloading 语义

- **装载**：当 turn 请求带 `wizard_stage = X` 且存在对应 SkillPack 时：
  - `SetupAgentPromptService.build_system_prompt(...)` **跳过现行 `_stage_overlay`**，在原 `_stage_overlay` 槽位插入 SkillPack 渲染段。
  - base prompt 开头的 SetupAgent 身份语句切换到 specialist-hat 模式（详见下文 Base Prompt Refactor）。
- **未匹配**：`wizard_stage` 为 None 或在 SkillPack 注册表中无对应条目时：
  - 走原 `_stage_overlay` 路径，行为与现行**字节级一致**（兼容性保证）。
  - base prompt 开头维持原 SetupAgent 身份语句。
- **硬卸载**：下一 turn 若 `wizard_stage` 变更或为 None，新 system prompt 不再包含旧 SkillPack 任何内容。无 "former skill summary" 软过渡（如有需要走 `prior_stage_handoffs`，那是已存在的 stage 级 handoff，不在本任务变更范围）。

### Base Prompt Refactor（persona swap 支持）

#### Why

现行 base prompt 开头是 "You are SetupAgent. You only work in prestory..."。SkillPack 若再写 "You are a senior dramatist" 会形成两个 "You are X" 互冲。Anthropic agent-development 规范也建议系统 prompt 用单一 persona 槽位 + stage-local specialist hat。

#### How

修改 `setup_agent_prompt_service.py::build_system_prompt`，将开头组装为：

```
You are SetupAgent, the prestory setup assistant.
[原 SetupAgent operating envelope: prestory only / no active prose / no Memory OS direct mutation / etc.]

{IF SkillPack present:}
For this turn, you operate in the {wizard_stage_label} stage.
While in this stage, take on the perspective of the Specialist hat described in the Stage Skill Pack section below.
Treat the Specialist hat as your guiding voice for this turn, but never break the SetupAgent operating envelope above.
{END IF}

Core rules:
1. ...
```

SkillPack 渲染段中 `persona` 字段以 "Specialist hat:" 标签出现，而非独立的 "You are X" 句：

```
[Stage Skill Pack: character-design.v1]
Specialist hat:
A senior dramatist and character writer. Your craft is shaping believable people: motivation arcs, internal contradictions, voice, relational tension, and how each character lives inside the story's world rules. While operating in this stage, you elicit, propose, and refine character entries; you do not write scenes, dialogue, or plot beats.

Objectives:
- ...
```

效果：
- 只有一个 "You are SetupAgent" 身份声明。
- SkillPack persona 是 stage-local 的"专业视角"，不与基础身份冲突。
- 切 stage 后，specialist-hat 段消失，恢复纯 SetupAgent 身份；`prior_stage_handoffs` 仍按原合同携带前 stage 真相。

### Render 形态（替换原 _stage_overlay 槽位的段落）

```
[Stage Skill Pack: character-design.v1]
Specialist hat:
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

### Persona (EN, rendered as "Specialist hat:" — NOT "You are X")

```
A senior dramatist and character writer. Your craft is shaping believable
people: motivation arcs, internal contradictions, voice, relational tension,
and how each character lives inside the story's world rules. While operating
in this stage, you elicit, propose, and refine character entries; you do not
write scenes, dialogue, or plot beats.
```

### Description (internal, not rendered to prompt)

```
WHAT: Drives the SetupAgent through the character-design wizard stage —
elicits the cast, deepens motivation/limits/voice, exposes relational
tension, and stays scoped to character entries within the foundation
SetupStepId.

WHEN: wizard_stage == "characterDesign". Loaded automatically by the
SetupAgentPromptService whenever the frontend reports the user is on the
"角色设定" wizard tab.
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
3. `SetupAgentPromptService.build_system_prompt(...)` 新增 `wizard_stage: str | None` 形参；命中 `STAGE_SKILL_PACKS[wizard_stage]` 时：
   - 跳过现行 `_stage_overlay`，在原 `_stage_overlay` 槽位插入 SkillPack 渲染段；
   - base prompt 开头插入 specialist-hat 引导句（详见 Base Prompt Refactor）；
   未命中时行为与现行**字节级一致**。
4. 新增 `backend/rp/services/setup_stage_skill_packs.py`：定义 `StageSkillPack` / `FieldHint` / `ClarificationTemplate` 数据结构、注册表 `STAGE_SKILL_PACKS`、`render_skill_pack(...)` 渲染函数。Pilot 只注册 `characterDesign`。

### Frontend

1. `lib/pages/prestory_setup_page.dart` 在调用 setup turn 入口处补传 `wizardStage = _selectedStage.name`（与 `_targetStepForStage` 同处）。
2. AI 客户端 / dio 调用层：`RpSetupAgentTurnRequest` 序列化新增 `wizard_stage` 字段。

### Eval Module Integration（接口预留，Pilot 不实装）

现有 eval 模块（`backend/rp/eval/`）已具备 case 化行为评测能力（runner / suite / replay / ragas），并有 setup scope 的多个 case family（cognitive / commit / guard / infra / repair）。SkillPack 行为评测**预留接口**但 Pilot 不交付：

- 数据结构层：`StageSkillPack.evaluation_scenarios: list[dict] | None = None` 槽位（Pilot 永远 None）。
- Case family 路径预定：未来在 `backend/rp/eval/cases/setup/skill_pack/<stage>/*.json` 下加 case，遵循现有 `EvalExpected` 合同（`expected_reason_codes` / `expected_outcome_chain` / `expected_recommended_next_action`）。
- Spec 层：在新 spec 文件 `rp-setup-agent-stage-skill-pack.md` 末尾标注"未来与 eval 模块的对接点"，但不在 `rp-eval-setup-case-contracts.md` 内引入新合同字段。

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
11. SkillPack 行为层 eval cases（数据结构 `evaluation_scenarios` 槽位预留 None，case JSON 与 ragas 评测拆后续任务）。
12. `_stage_overlay` 整体弃用（Pilot 仅在命中 SkillPack 时跳过；7 个 wizard stage 全部落地 SkillPack 后再做整体弃用）。

## Deliverables

1. 新增 spec：`.trellis/spec/backend/rp-setup-agent-stage-skill-pack.md`（运行时契约 + 与 eval 模块的对接预留）。
2. 后端代码：`backend/rp/services/setup_stage_skill_packs.py` + `SetupAgentPromptService` 改造（base prompt persona-swap + SkillPack 渲染替代 _stage_overlay 槽位）+ `SetupAgentTurnRequest` / `SetupAgentExecutionService` wizard_stage 透传。
3. 前端代码：`prestory_setup_page.dart` 与 setup turn 客户端层补传 `wizard_stage`。
4. 测试：
   - `backend/rp/tests/test_setup_agent_stage_skill_packs.py`（新文件）：
     - `STAGE_SKILL_PACKS["characterDesign"]` 存在；name / wizard_stage / description / persona / objectives / forbidden / facilitation_principles / content_skeleton / clarification_templates 全部非空且符合本 PRD 内容。
     - `render_skill_pack(pack)` 输出**不出现**字面量 "You are"（避免与 base prompt 互冲）；包含 "Specialist hat:" 标签；包含本 PRD 列出的 forbidden 第 4/5 条（不自动 commit / 不自动判 ready）；包含 `content.motivation.real`、`content.world_fit` 等关键路径；包含中文 clarification 模板原文。
     - `personas` / `selection_strategy` / `preset_library` / `evaluation_scenarios` 槽位为 None。
   - `backend/rp/tests/test_setup_agent_prompt_service.py`：
     - `wizard_stage="characterDesign"` 时 system prompt 中：
       - 出现 `[Stage Skill Pack: character-design.v1]` 标记段；
       - 出现 specialist-hat 引导句；
       - **不出现** foundation 的 `_stage_overlay` 原文（"Focus on stable world, character, and rule facts"）；
       - 仅出现一个 "You are SetupAgent" 身份声明。
     - `wizard_stage=None` 或未注册值时 system prompt 与现行**字节级一致**（无 `[Stage Skill Pack` 字串、无 specialist-hat 引导句、保留原 `_stage_overlay`）。
     - 同 prompt service 实例先后两次不同 wizard_stage 调用之间互不污染（无残留）。
   - `backend/rp/tests/test_setup_agent_execution_service_v2.py`：新字段 `wizard_stage` 从 `SetupAgentTurnRequest` 透传到 prompt service，渲染段落出现在最终 system prompt 中。
5. `.trellis/spec/backend/index.md` 索引追加新 spec 条目与 pre-development checkbox。

## Acceptance

1. 前端在 characterDesign stage 发起 turn 时，后端 system prompt 中出现 `[Stage Skill Pack: character-design.v1]` 渲染段，包含本 PRD 列出的 specialist hat / objectives / forbidden / facilitation / content skeleton / clarification 模板核心字段。
2. 命中 SkillPack 时**不**出现现行 foundation `_stage_overlay` 原文。
3. system prompt 中只出现一个 "You are SetupAgent" 身份声明；SkillPack 段不写 "You are X"。
4. 用户切到任一非 characterDesign wizard stage（或 wizard_stage 为 None）后，下一 turn 的 system prompt 中**完全不出现** `[Stage Skill Pack` 字符串、不出现 specialist-hat 引导句、不出现 character SkillPack 任何 persona / facilitation / clarification 内容（硬卸载）；同时**恢复**原 `_stage_overlay` 内容。
5. 未升级前端（不传 wizard_stage）的 turn 行为与现行**字节级**一致，无回归。
6. `characterDesign` SkillPack 的 description / persona / objectives / forbidden / facilitation_principles / content_skeleton / clarification_templates 与本 PRD 内容一致。
7. SkillPack 数据结构中 `personas` / `selection_strategy` / `preset_library` / `evaluation_scenarios` 槽位存在但 Pilot 全部为 None。
8. SkillPack 不引入任何让 agent 自动判 ready / 自动 commit / 自动声明阶段完成的语句。
9. 新增 spec 与 index 检查项就位，单元测试通过。
