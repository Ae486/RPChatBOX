# UI Rearchitecture Documentation

> **项目目标**: 以 `flutter_chat_ui` 为视觉标准，对 ChatBox 项目进行全局 UI 统合重构

## 文档结构

| 文档                                       | 说明                                     |
| ------------------------------------------ | ---------------------------------------- |
| `01-PRODUCTION_FUNCTIONALITY_ANALYSIS.md`  | 生产项目功能完整分析                     |
| `02-INTEGRATION_FEASIBILITY_ASSESSMENT.md` | 集成可行性评估                           |
| `03-MIGRATION_PLAN.md`                     | 分步迁移计划                             |
| `04-FLUTTER_CHAT_UI_MAPPING.md`            | flutter_chat_ui 功能映射                 |
| `05-DESIGN_TOKENS_ARCHITECTURE.md`         | 设计令牌架构设计                         |
| `06-BUBBLE_FREE_LLM_OUTPUT_DESIGN.md`      | **⭐ 无气泡 LLM 输出设计**               |
| `09-PAGE_SWITCH_TEXT_JITTER.md`            | 页面切换时文字抖动（根因/验证/解决方案） |

## 核心开发哲学

> **"Copy before writing, connect before creating, reuse before inventing."**
>
> 复制优于编写，连接优于创造，复用优于发明。

原生产项目存在过度自定义实现的问题，导致维护性差。本次重构的核心原则：

1. **优先复用** - 优先使用 `flutter_chat_ui` 已有功能
2. **最小定制** - 仅在必要时进行定制扩展
3. **渐进迁移** - 分阶段逐步替换，确保稳定性
4. **功能保留** - 100% 保留现有功能，不丢失任何用户体验

## Flyer Chat Demo 的双重角色

`lib/pages/flyer_chat_demo_page.dart` 承担两个关键职责：

### 1. UI 框架集成试验场

- 验证 `flutter_chat_ui` 与项目的兼容性
- 测试自定义 Builder 实现
- 探索主题系统集成方案

### 2. Markdown 渲染策略优先级

- 包含优先的 Markdown 流式渲染策略
- `StablePrefixParser` 稳定前缀解析
- 需要迁移到生产项目的核心渲染逻辑

## 关键依赖

```yaml
# 已在 pubspec.yaml 中
flutter_chat_ui: ^2.0.0
flutter_chat_core: ^2.0.0
flyer_chat_text_message: ^2.0.0
flyer_chat_text_stream_message: ^2.0.0
```

## 当前状态

- [x] 依赖审计完成
- [x] 生产代码分析完成
- [x] Demo 代码分析完成 (详见 `../markstream-flutter/FLYER_CHAT_DEMO_ANALYSIS.md`)
- [x] 功能映射文档
- [x] 迁移计划制定
- [x] **无气泡 LLM 输出设计规范**
- [ ] 第一阶段实施

## 相关文档

- `docs/markstream-flutter/` - MarkStream 集成指南
- `docs/CONVERSATIONVIEW_CODE_ANALYSIS.md` - 历史代码分析

---

## 核心 UI 设计决策

### 无气泡 LLM 输出

用户明确要求：**大模型输出内容不使用气泡包裹，直接流淌在背景上**

| 消息类型 | 样式                                 |
| -------- | ------------------------------------ |
| 用户消息 | 气泡包裹 (保持现有设计)              |
| LLM 输出 | **无气泡**，全宽度内容，流淌在背景上 |
| 思考气泡 | 轻量容器 (半透明蓝色背景)            |
| 代码块   | 自带容器 (保持现有设计)              |

详见 [`06-BUBBLE_FREE_LLM_OUTPUT_DESIGN.md`](./06-BUBBLE_FREE_LLM_OUTPUT_DESIGN.md)

---

_创建时间: 2024-12-21_
_最后更新: 2024-12-21_
