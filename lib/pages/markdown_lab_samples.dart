// markdown_lab_samples.dart —— lab 内置测试样本常量（part of markdown_lab_page）
part of 'markdown_lab_page.dart';

/// 默认测试样本：覆盖文章 + 表格 + 代码 + 行内/块级 LaTeX + think + mermaid
const String _kSample = r'''
# Smooth Markdown 试验场

普通段落，含 **加粗**、*斜体*、`行内代码`、删除线 ~~删除~~ 与链接 [Flutter](https://flutter.dev)。

## 表格（观察流式时是否泄漏 raw）

| 维度 | 现状 owui | smooth_markdown |
| --- | --- | --- |
| 表格流式 | 泄漏 `\|x\|x\|` | 待观察 |
| 代码行号 | 预测错位 | 待观察 |
| Mermaid | WebView | 原生 CustomPainter |

## 任务列表

- [x] 已完成项
- [ ] 未完成项

## 代码块（观察长行换行与行号对齐）

```dart
void main() {
  final List<String> items = <String>['alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta', 'eta', 'theta'];
  for (final item in items) {
    debugPrint('streaming code line that is intentionally long to force a soft wrap and test gutter alignment: $item');
  }
}
```

## LaTeX（行内与块级）

行内公式 $E = mc^2$ 与 $\alpha + \beta = \gamma$。

块级公式（观察是否过扁 / 是否横向溢出）：

$$
\int_{a}^{b} f(x)\,dx = F(b) - F(a) \qquad \sum_{i=1}^{n} i = \frac{n(n+1)}{2}
$$

## Think 块（注意：smooth_markdown 要求标签独占一行）

<think>
这是模型的推理过程。
上游 thinking_extractor 会把 reasoning 字段归一化为 <think> 标签。
</think>

## Mermaid（原生渲染，无 WebView）

```mermaid
graph TD
  A[开始] --> B{判断}
  B -->|是| C[执行]
  B -->|否| D[结束]
  C --> D
```

> 引用块：用于对照整体视觉风格是否统一。

## 提示/警告块（admonition：框架有 plugin，builder 自建）

::: note 说明
这是 note 提示块，正文经框架 blockRenderer 渲染（样式与正文统一）。
:::

::: tip 小技巧
tip 提示块。
:::

::: warning 注意
warning 警告块。
:::

::: danger 危险
danger 错误块。
:::

::: important 重要
important 重要块。
:::

## 折叠块（details：框架内核能力，开箱可用）

<details>
<summary>点击展开详情</summary>
这里是被折叠的内容，框架原生支持 details 块。
</details>

## 更多 Mermaid 子图（原生 CustomPainter，验证类型推断）

```mermaid
sequenceDiagram
  participant A as 客户端
  participant B as 服务端
  A->>B: 请求
  B-->>A: 响应
```

```mermaid
pie title 渲染耗时占比
  "解析" : 25
  "布局" : 35
  "绘制" : 40
```

## d2 / infographic（框架不支持）

框架无 d2/infographic 的 parser 与 painter，Flutter 生态亦无现成渲染器；
以下 d2 块会回退为普通代码块显示（语言标 D2）：

```d2
a -> b -> c
```
''';

/// 图表/块全集样本：展示框架支持的全部 mermaid 子图 + 网络图片。
/// 各图语法逐字取自包官方 example/lib/mermaid_demo.dart（保证可渲染）。
const String _kGallerySample = r'''
# 框架支持的图表全集（原生 CustomPainter，无 WebView）

## 流程图 Flowchart

```mermaid
graph TD
    A[开始] --> B{判断}
    B -->|是| C[处理]
    B -->|否| D[结束]
    C --> D
```

## 时序图 Sequence

```mermaid
sequenceDiagram
    participant U as 用户
    participant S as 服务器
    U->>S: 请求
    S-->>U: 响应
```

## 饼图 Pie

```mermaid
pie showData
    title 语言占比
    "Dart" : 55
    "Python" : 30
    "其他" : 15
```

## 甘特图 Gantt

```mermaid
gantt
    title 项目计划
    dateFormat YYYY-MM-DD
    section 开发
        设计 :done, des, 2024-01-01, 10d
        编码 :active, dev, after des, 20d
    section 测试
        联调 :test, after dev, 7d
```

## 时间线 Timeline

```mermaid
timeline
    title 发展历程
    2020 : 立项
    2022 : 上线
    2024 : 重构
```

## 看板 Kanban

```mermaid
kanban
  title 任务看板

  todo[待办]
    t1[需求分析]

  doing[进行中]
    t2[开发功能] @{ priority: "High" }

  done[完成]
    t3[环境搭建]
```

## 雷达图 Radar

```mermaid
radar-beta
    title 技能评估
    axis 编程, 设计, 沟通, 管理, 创新
    curve 张三{5, 3, 4, 2, 4}
    showLegend true
    max 5
    graticule polygon
    ticks 5
```

## XY 图 XY Chart

```mermaid
xychart-beta
    title "季度销售额"
    x-axis [Q1, Q2, Q3, Q4]
    y-axis "销售额(万)" 0 --> 100
    bar [23, 45, 67, 89]
    line [20, 40, 60, 85]
```

## 网络图片 Image（需联网，框架内核 builder：缓存 + 点击）

![随机图](https://picsum.photos/400/200)
''';

/// 图片来源测试样本：对照框架内核 ImageBuilder 对各来源的处理。
/// 预期：网络位图 / 网络 SVG 正常；本地文件 / data URI 碎图(走 Image.asset)。
const String _kImageSample = r'''
# 图片来源测试（框架默认 ImageBuilder）

> 观察框架内核 builder 对各来源的处理。预期：本地文件 / data URI 会碎图。

## 1. 网络位图 http/https —— 框架支持（CachedNetworkImage 带缓存）

![网络 PNG](https://picsum.photos/400/200)

## 2. 网络 SVG —— 框架支持（flutter_svg）

![网络 SVG](https://upload.wikimedia.org/wikipedia/commons/0/02/SVG_logo.svg)

## 3. 本地文件 —— 框架默认走 Image.asset，预期碎图

正斜杠绝对路径：

![本地-正斜杠](C:/Users/55473/Desktop/images/others/486.jpg)

反斜杠绝对路径：

![本地-反斜杠](C:\Users\55473\Desktop\images\others\486.jpg)

file URI：

![本地-fileURI](file:///C:/Users/55473/Desktop/images/others/486.jpg)

## 4. data URI base64 内联 —— 框架默认走 Image.asset，预期碎图

![内联1x1](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==)

## 5. 不存在的网络图 —— 错误占位

![坏链](https://example.invalid/nope.png)
''';
