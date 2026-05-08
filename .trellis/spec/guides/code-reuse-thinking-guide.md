# Code Reuse Thinking Guide

> **Purpose**: Stop and think before creating new code - does it already exist?

---

## The Problem

**Duplicated code is the #1 source of inconsistency bugs.**

When you copy-paste or rewrite existing logic:
- Bug fixes don't propagate
- Behavior diverges over time
- Codebase becomes harder to understand

---

## Before Writing New Code

### Step 1: Search First

```powershell
# Search for similar function names
rg -n "functionName" .

# Search for similar logic
rg -n "keyword" .
```

### Step 2: Ask These Questions

| Question | If Yes... |
|----------|-----------|
| Does a similar function exist? | Use or extend it |
| Is this pattern used elsewhere? | Follow the existing pattern |
| Could this be a shared utility? | Create it in the right place |
| Am I copying code from another file? | **STOP** - extract to shared |

---

## Common Duplication Patterns

### Pattern 1: Copy-Paste Functions

**Bad**: Copying a validation function to another file

**Good**: Extract to shared utilities, import where needed

### Pattern 2: Similar Components

**Bad**: Creating a new component that's 80% similar to existing

**Good**: Extend existing component with props/variants

### Pattern 3: Repeated Constants

**Bad**: Defining the same constant in multiple files

**Good**: Single source of truth, import everywhere

---

## When to Abstract

**Abstract when**:
- Same code appears 3+ times
- Logic is complex enough to have bugs
- Multiple people might need this

**Don't abstract when**:
- Only used once
- Trivial one-liner
- Abstraction would be more complex than duplication

---

## After Batch Modifications

When you've made similar changes to multiple files:

1. **Review**: Did you catch all instances?
2. **Search**: Run `rg` to find any missed
3. **Consider**: Should this be abstracted?

---

## Gotcha: Asymmetric Mechanisms Producing Same Output

**Problem**: When two different mechanisms must produce the same file set (e.g., recursive directory copy for init vs. manual `files.set()` for update), structural changes (renaming, moving, adding subdirectories) only propagate through the automatic mechanism. The manual one silently drifts.

**Symptom**: Init works perfectly, but update creates files at wrong paths or misses files entirely.

**Prevention checklist**:
- [ ] When migrating directory structures, search for ALL code paths that reference the old structure
- [ ] If one path is auto-derived (glob/copy) and another is manually listed, the manual one needs updating
- [ ] Add a regression test that compares outputs from both mechanisms

---

## Reuse Existing Conventions Before Adding Library Dependencies

**Problem**: Reaching for a new third-party library when the codebase has already converged on a lightweight in-house pattern that solves the same need. Each redundant dependency adds install footprint, security surface, and version-coupling risk.

**Examples of conventions worth checking before adding a dep**:

| Need | Reflexive choice | Project convention to check first |
|---|---|---|
| Parse YAML frontmatter from markdown files | `pyyaml` | Project may have a regex-based split (`---\n...---\n`) for simple flat frontmatter; `pyyaml` is opt-in only where deeply nested structure is required |
| HTTP client | new `httpx` / `requests` import | Existing service-layer wrapper that injects timeouts / retries / langfuse trace |
| Date parsing | `dateutil` | `datetime.fromisoformat` + project-local helpers |
| ID generation | new `uuid` / `secrets` import | Project may have a centralized id factory enforcing prefix conventions |

**Decision rule**:

1. Search the codebase for the same problem (`rg "frontmatter\|yaml.safe_load\|---\n"`).
2. If a convention exists, follow it; do not introduce a parallel mechanism.
3. If no convention exists but the in-house solution would stay under ~30 lines and have a single clear use site, prefer the in-house solution over a new dependency.
4. Only add a dependency when the problem genuinely exceeds what a small focused helper can do (e.g., full YAML schema validation, complex date arithmetic, OAuth flows).

**Symptom of skipping this rule**: `requirements.txt` accretes near-duplicate libraries (`pyyaml` + `ruamel.yaml`, `requests` + `httpx`); each new contributor reaches for whichever library they know first; codebase loses parsing/IO consistency.

**Real example from this repo**: SkillPack registry parses `SKILL.md` frontmatter via a small regex (`backend/rp/agent_runtime/skill_packs/registry.py`) instead of pulling in `pyyaml` as a hard dependency. The frontmatter shape is intentionally flat (3 string keys); the regex is ~10 lines and fail-soft. Adding `pyyaml` for this would have created divergent YAML parsing paths in the project (existing `case_loader.py` uses `pyyaml` only as an opt-in import).

---

## Checklist Before Commit

- [ ] Searched for existing similar code
- [ ] No copy-pasted logic that should be shared
- [ ] Constants defined in one place
- [ ] Similar patterns follow same structure
- [ ] No new third-party dependency added without checking for an in-house convention
