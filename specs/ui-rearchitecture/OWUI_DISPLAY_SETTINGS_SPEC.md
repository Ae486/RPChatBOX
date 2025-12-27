# OWUI Display Settings（显示设置）规格
> 创建时间：2025-12-26  
> 状态：Draft（随实现迭代）  
> 目标：在 Settings 中新增「显示设置」入口与页面，用于承载 UI Scale / 字体 / 后续样式相关设置，并确保缩放后点击与布局稳定（不出现错位触发）。

---

## 1. 范围
本规格覆盖：
- Settings 增加「显示设置」入口
- 新增 Display Settings 页面（OWUI 风格）
- UI Scale（全局缩放：字体 + 控件 + 间距）
- 字体（全局字体 + 代码字体，分别可配置）

不覆盖（后续扩展）：
- Claude/Gemini 等主题配色预设（但需要为其预留结构）

---

## 2. 数据与持久化
使用 `SharedPreferences` 存储（与 `theme_mode` 同级）：
- `ui_scale`：`double`，默认 `1.0`
- `ui_font_family`：`String`，默认 `system`
- `ui_code_font_family`：`String`，默认 `system_mono`

字体值使用 **id**（而不是直接存 fontFamily），便于后续改名/迁移：
- 全局字体（示例）：
  - `system`（跟随系统默认）
  - `noto_sans`
  - `noto_serif`
- 代码字体（示例）：
  - `system_mono`
  - `jetbrains_mono`
  - `noto_sans_mono`

---

## 3. UI Scale 行为要求（关键）
### 3.1 目标
`uiScale` 需要统一影响：
- 所有字体（含代码字体）
- 按钮、输入框、AppBar、菜单等交互组件的尺寸/内边距
- OWUI spacing / radius / 常用尺寸 token

### 3.2 禁止方案
- 禁止使用 `Transform.scale`（包含 `transformHitTests` 变体）：会引入命中区域错位/不可点击等风险。

### 3.3 推荐落地方式
- `ThemeData.textTheme.apply(fontSizeFactor: uiScale)`：统一缩放文本
- `OwuiTokens.(light/dark)(uiScale: uiScale)`：统一缩放 spacing/radius（并按需扩展到 typography）
- 在 `ThemeData` 中补齐常见控件的 theme：
  - Button（padding / minimumSize）
  - InputDecoration（contentPadding / isDense 等）
  - IconTheme（icon size）
  - ListTileTheme（contentPadding / minLeadingWidth）
  - AppBarTheme（toolbarHeight 如需可跟随，但优先保持稳定）

并对关键尺寸做 clamp（例如最小高度不低于 40~44），避免缩放过小导致可点击区域不足。

建议初始范围：`0.85 ~ 1.25`，step `0.05`。

---

## 4. 字体要求
### 4.1 全局字体
- 影响全局 TextTheme（含所有权重）
- 默认 `system`

### 4.2 代码字体
- 影响 Markdown/代码块/错误详情等“等宽文本”场景
- 默认 `system_mono`
- 推荐通过 `OwuiTokens`（ThemeExtension）提供 `codeFontFamily + fallback`，由相关组件读取。

---

## 5. 页面与交互
### 5.1 Settings 入口
- 在 `SettingsPage` 新增卡片入口：`显示设置`
- 点击进入 `DisplaySettingsPage`

### 5.2 Display Settings 页面结构（参考 OpenWebUI）
- Section：`界面缩放`
  - Slider + 当前数值（例如 1.00）
  - 立即生效（onChanged 即时刷新主题）
- Section：`字体设置`（带 `New` 徽标）
  - Item：`全局字体`（点击弹出选择）
  - Item：`代码字体`（点击弹出选择）

---

## 6. 验收
- `dart analyze` 无 error
- UI scale 改变后：
  - 无明显溢出/错位
  - 点击区域与视觉一致（不出现“点 A 触发 B”）
  - 输入框、按钮可正常点击/聚焦
- light/dark 下页面风格保持 OWUI 统一
