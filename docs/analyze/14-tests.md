# test/ 代码质量分析

> 检查时间: 2026-02-01
> 检查人: Claude (Haiku)
> 复核人: Codex (SESSION_ID: 待记录)
> 状态: 进行中

---

## 1. 概览

### 测试结构

| 项目 | 类型 | 文件数 | 行数 | 风险 |
|------|------|--------|------|------|
| 单元测试 | unit_test | ~10 | ~1500 | ⏳ |
| Widget 测试 | widget_test | ~8 | ~2000 | ⏳ |
| 集成测试 | golden + helpers | ~10 | ~2720 | ⏳ |

**总结构**:
- test/unit/ - 单元测试
- test/widget/ - Widget 测试
- test/helpers/ - 测试辅助（Mock、Fixture）
- test/mocks/ - Mock 对象
- test/golden/ - Golden 文件测试

**总行数**: ~6220 行

---

## 2. 检查清单（12 维度 + 测试特定）

### 1. 测试架构
- [ ] 1.1 测试结构：unit/integration/widget 是否分离
- [ ] 1.2 测试命名：测试文件命名是否清晰
- [ ] 1.3 Mock 管理：Mock 对象是否集中管理
- [ ] 1.4 Fixture 设计：测试数据是否易于维护

### 2. 代码质量
- [ ] 2.1 测试行数：单个测试是否超过 50 行
- [ ] 2.2 函数长度：setup/teardown 是否过长
- [ ] 2.3 嵌套深度：describe 嵌套是否过深
- [ ] 2.4 圈复杂度：测试逻辑是否过复杂

### 3. 测试覆盖
- [ ] 3.1 关键路径：核心功能是否有测试
- [ ] 3.2 错误路径：异常处理是否有测试
- [ ] 3.3 边界条件：边界值是否测试
- [ ] 3.4 覆盖率：整体覆盖率水平

### 4. 错误处理
- [ ] 4.1 异常测试：try/catch 是否有测试
- [ ] 4.2 expect 完整性：断言是否充分
- [ ] 4.3 失败诊断：测试失败信息是否清晰

### 5. 类型安全
- [ ] 5.1 mock 类型：Mock 对象类型是否安全
- [ ] 5.2 as 转换：强制转换是否必需
- [ ] 5.3 null 处理：可选值测试是否正确

### 6. 隔离性
- [ ] 6.1 测试独立：测试间是否有依赖
- [ ] 6.2 状态清理：setUp/tearDown 是否完整
- [ ] 6.3 全局污染：是否有全局状态污染

### 7. 重复性
- [ ] 7.1 重复代码：测试是否有重复 setup
- [ ] 7.2 辅助函数：公共逻辑是否提取
- [ ] 7.3 数据生成：Fixture 是否复用

### 8. 文档与注释
- [ ] 8.1 测试说明：测试意图是否清晰
- [ ] 8.2 Mock 说明：Mock 行为是否有文档
- [ ] 8.3 边界说明：特殊用例是否有说明

### 9. 技术债务
- [ ] 9.1 skip/pending：跳过的测试是否标记
- [ ] 9.2 临时 mock：硬编码 mock 是否临时
- [ ] 9.3 废弃测试：过时测试是否清理

### 10. 性能
- [ ] 10.1 执行时间：单个测试是否过慢
- [ ] 10.2 总耗时：整个测试套件是否快速
- [ ] 10.3 资源占用：内存/CPU 是否占用过多

### 11. 可维护性
- [ ] 11.1 命名清晰：测试函数名是否说明用途
- [ ] 11.2 组织逻辑：测试文件组织是否清晰
- [ ] 11.3 改动成本：添加新测试成本是否低

### 12. CI/CD 集成
- [ ] 12.1 自动化：测试是否自动运行
- [ ] 12.2 失败处理：测试失败是否阻止发布
- [ ] 12.3 覆盖率报告：是否收集覆盖率

---

## 4. Codex 复核意见

> **SESSION_ID**: 019c159c-57dc-7e13-bb74-43e506e4209e
> **Review Scope**: Test coverage gaps, Mock strategy consistency, critical path verification

### A. CRITICAL TEST COVERAGE GAPS

#### [IMPORTANT] 无 StablePrefixParser.split() 单元测试
**Issue**: `lib/rendering/markdown_stream/stable_prefix_parser.dart:26` - 核心流式 Markdown 解析器
- 4 个 critical state machine bugs 已在 Codex 审查中发现（10-rendering.md）
- **完全无单元测试验证**

**影响**: 任何 StablePrefixParser 的改动都无法通过测试防止回归

**所需测试**:
```dart
test('split() handles 4+ backtick fences', () { ... });
test('split() exits table mode when separator missing', () { ... });
test('split() HTML stack tracking', () { ... });
test('split() fence not gated by HTML block', () { ... });
```

---

#### [IMPORTANT] 无 inferCodeLanguage() / Diff 检测测试
**Issue**: `lib/rendering/markdown_stream/language_utils.dart:150, 165` - 语言识别无测试

**所需测试**:
```dart
test('inferCodeLanguage() recognizes common patterns', () { ... });
test('looksLikeUnifiedDiff() detects diffs correctly', () { ... });
test('Pandoc info strings like {.js} are normalized', () { ... });
```

---

#### [IMPORTANT] ModelCapabilityPresets 映射规则无测试
**Issue**: `lib/data/model_capability_presets.dart:52` - 模型能力预设映射
- 匹配规则（精确 → 前缀 → 包含）无测试
- 从 Codex 11-data 审查发现，模型覆盖过时（GPT-4.1, Claude ID, Gemini 预设）

**所需测试**:
```dart
test('getCapabilities() exact matches', () { ... });
test('getCapabilities() prefix matching', () { ... });
test('getCapabilities() fallback to text-only', () { ... });
test('Model coverage - GPT-4.1, Claude new IDs, Gemini', () { ... });
```

---

#### [IMPORTANT] ChatSessionProvider 异步初始化无测试
**Issue**: `lib/providers/chat_session_provider.dart:32` - Provider 初始化时序 bug（P0 from Phase 2）
- 构造器调用异步 _init()，但未等待
- 无测试覆盖此场景

**所需测试**:
```dart
test('ChatSessionProvider initializes Hive before notifying listeners', () { ... });
test('Early access to ChatSessionProvider.messages before init completes', () { ... });
```

---

#### [IMPORTANT] setState-After-Dispose 场景无覆盖
**Issue**: `lib/pages/` 中多个页面（4+ 处，Phase 2 发现）
- 快速返回导致 setState 在 dispose 后执行 → 黄屏错误
- 仅有一个基础 widget smoke test，无边界覆盖

**所需测试**:
```dart
test('ChatPage dispose clears all StreamSubscriptions', () { ... });
test('Provider detail page rapid navigation cancels pending ops', () { ... });
test('Golden test with Timer cleanup (currently skipped)', () { ... });
```

---

### B. MOCK STRATEGY INCONSISTENCY

#### [RISK] Mock 策略不一致
**Issue** (test/mocks, test/helpers):
- **Mockito**: 代码生成器生成了 mocks，但在实际测试中**几乎未使用**
- **手写 Fakes**: SharedPreferences.setMockInitialValues 主导
- **覆盖率**: 仅 15-25%，UI 层 <10%

**问题**:
- 交互验证困难（无 Mock.verify(x.calls)）
- 集成测试与单元测试边界模糊
- 新贡献者难以理解 mock 策略

**建议**:
1. **选择一致的 Mock 策略**:
   - 要么全用 Mockito （推荐）
   - 要么全用手写 Fakes

2. **统一测试组织**:
   ```
   test/unit/
   ├── models/      # 数据模型测试
   ├── services/    # 服务逻辑测试
   ├── providers/   # Provider 状态测试
   └── utils/       # 工具函数测试

   test/widget/     # Widget 构建测试

   test/integration/ # 多组件集成测试
   ```

3. **文档化 Mock 约定**:
   ```dart
   // test/README.md
   - Unit tests use Mockito for verification
   - SharedPreferences.setMockInitialValues for state
   - Use .mock suffix for MockitoMocks
   ```

---

### C. COVERAGE SUMMARY

| 组件 | 覆盖 | 状态 |
|------|------|------|
| StablePrefixParser | 0% | 🔴 NOT TESTED |
| inferCodeLanguage | 0% | 🔴 NOT TESTED |
| ModelCapabilityPresets | ~30% | 🟡 PARTIAL (only ModelConfig) |
| ChatSessionProvider | ~20% | 🟡 MINIMAL |
| Pages (UI) | <10% | 🔴 CRITICAL GAP |
| Widgets (UI) | ~15% | 🟡 SMOKE ONLY |
| Services | ~40% | 🟡 MODERATE |
| Models | ~50% | 🟡 REASONABLE |

**整体估计**: **15-25% 代码覆盖率，关键路径 <10%**

---

## 5. 总结与建议

### 测试质量评估

| 维度 | 评级 | 说明 |
|------|------|------|
| **覆盖率** | 🔴 CRITICAL | 15-25% 过低，UI <10% |
| **Mock 策略** | 🟠 HIGH | 不一致，难以维护 |
| **关键路径** | 🔴 GAPS | StablePrefixParser, Provider init 无测试 |
| **集成测试** | 🟡 LIMITED | Golden 测试被跳过 |
| **可维护性** | 🟠 HIGH | 需要组织和文档 |

### 修复优先级（预计工作量）

**Phase 1 - 关键路径（3-4 周）**:
1. 添加 StablePrefixParser 单元测试（20 小时）
2. 添加 ChatSessionProvider 初始化测试（8 小时）
3. 添加 setState-after-dispose 边界测试（8 小时）
4. 添加 inferCodeLanguage + Diff 检测测试（4 小时）

**Phase 2 - 基础设施（2 周）**:
5. 统一 Mock 策略（Mockito 优先）（12 小时）
6. 组织 test/ 目录结构（4 小时）
7. 编写测试指南文档（4 小时）

**Phase 3 - 完整覆盖（4+ 周）**:
8. UI 层测试补充（pages, widgets）（40+ 小时）
9. 集成测试编写（20+ 小时）
10. 覆盖率目标 50%+

---

**状态**: 🔴 CRITICAL - 关键组件无测试，建议立即添加（StablePrefixParser, Provider init)

---

## 5. 总结与建议

（待更新）
