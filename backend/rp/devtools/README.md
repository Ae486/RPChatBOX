# RP Devtools

## legal longform session seed

这个工具直接向开发数据库写入一套“合法 longform runtime session”最小材料，不跑 setup agent，也不模拟完整 setup 流程。

### 做什么

- 创建 `StorySessionRecord` / `ChapterWorkspaceRecord`
- 确保 default branch 与 active runtime profile snapshot
- 写入 formal Core State activation seed 与 projection mirror
- 写入 accepted structured outline（带 beat）
- 写入至少一段 accepted story segment，并把 turn 标成 settled
- 写入 longform outline progress sidecar
- 写入 Recall accepted segment retrieval material
- 写入一份最小 Archival retrieval material

### 预期看到什么

- longform 页面可以直接用返回的 `session_id` 打开现有 session
- session 自带 active branch、active snapshot、accepted outline、accepted segments
- `memory/inspection` 至少能看到 Core / Projection / Runtime Workspace / Recall / Archival 的基础材料
- 这套 seed 可继续拿来做分支、回退、memory 检查的基础验证

### 命令

从 `backend/` 目录运行：

```powershell
python -m rp.devtools.seed_legal_longform_session `
  --template .\rp\devtools\fixtures\legal_longform_session_template.v1.json `
  --story-id story-dev-longform-seed-001 `
  --label longform-seed-main
```

覆盖同一个 seed：

```powershell
python -m rp.devtools.seed_legal_longform_session `
  --template .\rp\devtools\fixtures\legal_longform_session_template.v1.json `
  --story-id story-dev-longform-seed-001 `
  --label longform-seed-main `
  --replace
```

### 注意

- `--replace` 只会覆盖“同 story_id 且带同 seed marker/label”的旧种子。
- 如果同一个 `story_id` 下存在普通 dev session，工具会拒绝覆盖，避免误删数据。
- `source_workspace_id` 只作为 runtime source anchor 复用或创建 setup workspace 行，不代表真实 setup truth 已完整存在。
