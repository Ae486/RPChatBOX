part of '../flyer_chat_demo_page.dart';

/// 压力测试数据生成器
/// 
/// 用于测试流式渲染的各种边界情况和性能
class _StressTestData {
  /// 生成长文档测试 (1000+ 行)
  static String generateLongDocument({int paragraphs = 50}) {
    final buffer = StringBuffer();
    buffer.writeln('# 长文档压力测试\n');
    buffer.writeln('> 本文档包含 $paragraphs 个段落，用于测试长文档渲染性能\n');
    
    for (var i = 1; i <= paragraphs; i++) {
      buffer.writeln('## 第 $i 节\n');
      buffer.writeln('这是第 $i 段内容。包含**粗体**、*斜体*、`行内代码`和[链接](https://example.com/$i)。');
      buffer.writeln('Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.\n');
      
      if (i % 5 == 0) {
        buffer.writeln('```dart\n// 代码块 $i\nvoid function$i() {\n  print("Section $i");\n}\n```\n');
      }
      if (i % 7 == 0) {
        buffer.writeln('| 列A | 列B | 列C |\n|-----|-----|-----|\n| $i-1 | $i-2 | $i-3 |\n| $i-4 | $i-5 | $i-6 |\n');
      }
      if (i % 10 == 0) {
        buffer.writeln('\$\$\\sum_{k=1}^{$i} k = \\frac{$i \\cdot ${i + 1}}{2}\$\$\n');
      }
    }
    return buffer.toString();
  }

  /// 生成多语言代码块测试
  static String generateMultiLanguageCodeBlocks() {
    return '''
# 多语言代码块测试

## Python
```python
import numpy as np
import pandas as pd

class DataProcessor:
    def __init__(self, data: list[dict]):
        self.df = pd.DataFrame(data)
    
    def process(self) -> pd.DataFrame:
        return self.df.groupby('category').agg({
            'value': ['mean', 'std', 'count']
        })

processor = DataProcessor([
    {'category': 'A', 'value': 10},
    {'category': 'B', 'value': 20},
    {'category': 'A', 'value': 15},
])
print(processor.process())
```

## JavaScript/TypeScript
```typescript
interface User {
  id: number;
  name: string;
  email: string;
  roles: string[];
}

async function fetchUsers(): Promise<User[]> {
  const response = await fetch('/api/users');
  if (!response.ok) {
    throw new Error(`HTTP error! status: \${response.status}`);
  }
  return response.json();
}

const users = await fetchUsers();
console.log(users.filter(u => u.roles.includes('admin')));
```

## Rust
```rust
use std::collections::HashMap;

#[derive(Debug, Clone)]
struct Config {
    name: String,
    values: HashMap<String, i32>,
}

impl Config {
    fn new(name: &str) -> Self {
        Self {
            name: name.to_string(),
            values: HashMap::new(),
        }
    }

    fn set(&mut self, key: &str, value: i32) {
        self.values.insert(key.to_string(), value);
    }
}

fn main() {
    let mut config = Config::new("production");
    config.set("max_connections", 100);
    config.set("timeout_ms", 5000);
    println!("{:?}", config);
}
```

## Go
```go
package main

import (
    "encoding/json"
    "fmt"
    "net/http"
)

type Response struct {
    Status  string `json:"status"`
    Message string `json:"message"`
    Data    any    `json:"data,omitempty"`
}

func handler(w http.ResponseWriter, r *http.Request) {
    resp := Response{
        Status:  "success",
        Message: "Hello, World!",
    }
    json.NewEncoder(w).Encode(resp)
}

func main() {
    http.HandleFunc("/", handler)
    fmt.Println("Server starting on :8080")
    http.ListenAndServe(":8080", nil)
}
```

## SQL
```sql
WITH monthly_sales AS (
    SELECT 
        DATE_TRUNC('month', order_date) AS month,
        product_id,
        SUM(quantity * unit_price) AS revenue,
        COUNT(DISTINCT customer_id) AS unique_customers
    FROM orders o
    JOIN order_items oi ON o.id = oi.order_id
    WHERE order_date >= '2024-01-01'
    GROUP BY 1, 2
)
SELECT 
    month,
    product_id,
    revenue,
    unique_customers,
    LAG(revenue) OVER (PARTITION BY product_id ORDER BY month) AS prev_month_revenue,
    revenue - LAG(revenue) OVER (PARTITION BY product_id ORDER BY month) AS revenue_change
FROM monthly_sales
ORDER BY month DESC, revenue DESC;
```

## Shell
```bash
#!/bin/bash
set -euo pipefail

echo "Starting deployment..."

# Build
npm run build

# Deploy
rsync -avz --delete dist/ server:/var/www/app/

# Restart
ssh server 'sudo systemctl restart app'

echo "Deployment complete!"
```
''';
  }

  /// 生成复杂嵌套测试
  static String generateComplexNesting() {
    return '''
# 复杂嵌套结构测试

## 多层列表

1. 第一层项目 1
   - 第二层项目 A
     - 第三层项目 i
       - 第四层项目 α
         - 第五层项目 ①
     - 第三层项目 ii
   - 第二层项目 B
     1. 有序子列表 1
     2. 有序子列表 2
        - 混合嵌套
        - 更多内容
2. 第一层项目 2
   > 引用块嵌套在列表中
   > - 引用中的列表
   > - 继续
   
   ```dart
   // 代码块嵌套在列表中
   void nestedCode() {
     print("Hello from nested code!");
   }
   ```

## 表格中的复杂内容

| 功能 | 代码示例 | 说明 |
|------|---------|------|
| 粗体 | `**text**` | **粗体效果** |
| 斜体 | `*text*` | *斜体效果* |
| 行内代码 | \\`code\\` | `代码效果` |
| 链接 | `[text](url)` | [链接效果](https://example.com) |
| 公式 | `\$formula\$` | \$E=mc^2\$ |

## 引用块嵌套

> 第一层引用
> > 第二层引用
> > > 第三层引用
> > > > 第四层引用 - 包含 **格式化** 和 `代码`
> > > 
> > > 返回第三层
> > 
> > 返回第二层，包含列表：
> > - 项目 1
> > - 项目 2
> 
> 返回第一层

## 混合内容块

这是一个包含多种元素的段落：**粗体**、*斜体*、~~删除线~~、`行内代码`、[链接](https://example.com)、以及公式 \$\\alpha + \\beta = \\gamma\$。

接下来是代码块和表格的交替：

```json
{
  "name": "test",
  "version": "1.0.0",
  "dependencies": {
    "lodash": "^4.17.21"
  }
}
```

| Key | Value | Type |
|-----|-------|------|
| name | test | string |
| version | 1.0.0 | string |

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
data:
  DATABASE_URL: postgres://localhost:5432/db
  REDIS_URL: redis://localhost:6379
```
''';
  }

  /// 生成大量公式测试
  static String generateMathHeavy() {
    return '''
# 数学公式压力测试

## 基础公式

行内公式：\$a^2 + b^2 = c^2\$, \$\\sin^2\\theta + \\cos^2\\theta = 1\$, \$e^{i\\pi} + 1 = 0\$

## 块级公式

\$\$
\\frac{d}{dx}\\left[\\int_a^x f(t)dt\\right] = f(x)
\$\$

\$\$
\\nabla \\times \\mathbf{E} = -\\frac{\\partial \\mathbf{B}}{\\partial t}
\$\$

\$\$
\\begin{pmatrix}
a & b \\\\
c & d
\\end{pmatrix}
\\begin{pmatrix}
x \\\\
y
\\end{pmatrix}
=
\\begin{pmatrix}
ax + by \\\\
cx + dy
\\end{pmatrix}
\$\$

## 连续公式

\$\$\\lim_{n\\to\\infty}\\left(1+\\frac{1}{n}\\right)^n = e\$\$

\$\$\\sum_{n=0}^{\\infty}\\frac{x^n}{n!} = e^x\$\$

\$\$\\int_{-\\infty}^{\\infty}e^{-x^2}dx = \\sqrt{\\pi}\$\$

\$\$\\prod_{p\\text{ prime}}\\frac{1}{1-p^{-s}} = \\sum_{n=1}^{\\infty}\\frac{1}{n^s}\$\$

## 复杂公式

\$\$
\\mathcal{L}\\{f(t)\\} = \\int_0^{\\infty} e^{-st} f(t) dt = F(s)
\$\$

\$\$
\\hat{f}(\\xi) = \\int_{-\\infty}^{\\infty} f(x) e^{-2\\pi i x \\xi} dx
\$\$

\$\$
\\frac{\\partial^2 u}{\\partial t^2} = c^2 \\nabla^2 u
\$\$
''';
  }

  /// 生成 Mermaid 图表测试
  static String generateMermaidCharts() {
    return '''
# Mermaid 图表测试

## 流程图

```mermaid
graph TD
    A[开始] --> B{条件判断}
    B -->|是| C[执行操作A]
    B -->|否| D[执行操作B]
    C --> E[处理结果]
    D --> E
    E --> F{继续?}
    F -->|是| B
    F -->|否| G[结束]
```

## 时序图

```mermaid
sequenceDiagram
    participant U as 用户
    participant C as 客户端
    participant S as 服务器
    participant D as 数据库
    
    U->>C: 输入查询
    C->>S: 发送请求
    S->>D: 查询数据
    D-->>S: 返回结果
    S-->>C: 响应数据
    C-->>U: 显示结果
```

## 类图

```mermaid
classDiagram
    class Animal {
        +String name
        +int age
        +makeSound() void
    }
    class Dog {
        +String breed
        +bark() void
    }
    class Cat {
        +String color
        +meow() void
    }
    Animal <|-- Dog
    Animal <|-- Cat
```

## 状态图

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> Loading: 开始加载
    Loading --> Success: 加载成功
    Loading --> Error: 加载失败
    Success --> Idle: 重置
    Error --> Loading: 重试
    Error --> Idle: 取消
```
''';
  }
}

String _buildMarkdownResponse(String prompt) {
  final raw = prompt.trim();
  if (raw.startsWith('/stress')) {
    final args = raw.split(RegExp(r'\s+')).where((e) => e.isNotEmpty).toList();
    final kind = args.length >= 2 ? args[1].toLowerCase() : 'all';
    final paragraphs = args.length >= 3 ? int.tryParse(args[2]) : null;

    String body;
    switch (kind) {
      case 'long':
        body = _StressTestData.generateLongDocument(paragraphs: paragraphs ?? 120);
        break;
      case 'code':
        body = _StressTestData.generateMultiLanguageCodeBlocks();
        break;
      case 'nest':
      case 'nested':
        body = _StressTestData.generateComplexNesting();
        break;
      case 'math':
        body = _StressTestData.generateMathHeavy();
        break;
      case 'mermaid':
        body = _StressTestData.generateMermaidCharts();
        break;
      case 'all':
      default:
        body = [
          _StressTestData.generateLongDocument(paragraphs: paragraphs ?? 80),
          _StressTestData.generateMultiLanguageCodeBlocks(),
          _StressTestData.generateComplexNesting(),
          _StressTestData.generateMathHeavy(),
          _StressTestData.generateMermaidCharts(),
        ].join('\n\n---\n\n');
        break;
    }

    return '''# 压力测试模式

> 输入命令：`$raw`

---

$body
''';
  }

  return '''下面是对你消息的模拟流式回复（内容更长、更复杂，方便观察"边输出边渲染"）：

## 你的输入

> $prompt

---

## 代码块

```dart
flutter run -d windows

flutter run -d android
```

```dart
class VeryLongDemo {
  VeryLongDemo();

  String build() {
    final buffer = StringBuffer();
    for (var i = 0; i < 40; i++) {
      buffer.writeln('Line: \$i');
    }
    return buffer.toString();
  }

  int sum(List<int> xs) {
    var s = 0;
    for (final x in xs) {
      s += x;
    }
    return s;
  }

  Map<String, dynamic> toJson() {
    return {
      'name': 'VeryLongDemo',
      'ok': true,
      'items': List.generate(10, (i) => i),
    };
  }
}
```

## 表格

| 功能 | 说明 |
| --- | --- |
| 流式 | 先纯文本展示 |
| 完成 | 切换完整渲染 |

| 模块 | 细节 | 备注 |
| --- | --- | --- |
| code | header + copy + highlight | 对标 CodeBlockNode |
| table | padding + border + zebra | 需要更精致样式 |
| link | underline + onTap | 可加 tooltip（桌面） |
| math | inline + block | 错误态要好看 |

## LaTeX

行内：\$\\frac{1}{2}\$

再来一个行内：\$E = mc^2\$

块级：

\$\$
\\int_0^1 x^2 \\; dx = \\frac{1}{3}
\$\$

\$\$
\\sum_{i=1}^{n} i = \\frac{n(n+1)}{2}
\$\$

## 链接

- Flutter: https://flutter.dev
- Flyer Chat: https://github.com/flyerhq/flutter_chat_ui
- markstream-vue: https://github.com/Simon-He95/markstream-vue

## Mermaid（如果你启用了渲染）

```mermaid
graph TD
  A[User] --> B[Stream]
  B --> C[Final Markdown]
  C --> D{Closed Blocks?}
  D -->|Yes| E[Upgrade]
  D -->|No| F[Plain Tail]
```

## Mid-state 压力测试

~~~js
console.log('tilde fence works')
~~~

a|b
---|---
1|2
3|4

好的，这是一段随机生成的长文本，希望能满足你的测试需求：

在浩瀚的宇宙深处，一颗名为“艾瑞斯”的蓝色星球正静静地悬浮在星系的边缘。这颗星球拥有着极其独特的地质构造和生态系统，其地表被广阔的海洋和连绵起伏的山脉所覆盖。海洋中生活着形态各异、色彩斑斓的生物，它们在深邃的海底世界中繁衍生息，构成了复杂而迷人的海洋食物链。而山脉之中，则隐藏着古老的森林和神秘的洞穴，那里栖息着一些鲜为人知的物种，它们的生存方式与外界截然不同。

艾瑞斯星球上的智慧生命，自称为“赛尔人”，他们拥有高度发达的文明。赛尔人的科技水平远超我们所知的任何文明，他们能够操控能量，穿梭于星际之间，并对宇宙的奥秘有着深刻的理解。然而，尽管科技发达，赛尔人却始终保持着对自然的敬畏。他们深知，宇宙中的每一个生命体都扮演着重要的角色，任何一个微小的改变都可能引发连锁反应，影响整个生态系统的平衡。因此，他们的发展始终以可持续性为核心，力求在科技进步与环境保护之间找到最佳的平衡点。

最近，艾瑞斯星球的科学家们发现了一个令人担忧的现象：一颗巨大的、带有未知能量的陨石正朝着他们的星球飞来。这颗陨石的轨迹难以预测，其潜在的破坏力足以威胁到整个星球的生存。消息一出，整个赛尔人社会都陷入了紧张之中。长老会立即召开了紧急会议，商讨对策。

一位名叫“艾莉亚”的年轻科学家提出了一个大胆的计划。她认为，与其试图摧毁陨石，不如尝试与其能量场进行共振，从而改变其飞行轨迹，将其引向宇宙的某个安全区域。这个计划风险极高，需要精确的计算和强大的能量输出，但这是他们唯一的希望。

在全星球的关注下，艾莉亚和她的团队开始了这项史无前例的尝试。他们调动了星球上最先进的能量聚合装置，将庞大的能量汇聚起来，对准了正在逼近的陨石。随着能量的释放，一道耀眼的光束划破天际，直射陨石。整个星球都感受到了巨大的能量波动，空气中弥漫着紧张而又充满希望的气息。

经过漫长而紧张的等待，科学家的监测数据显示，陨石的轨迹开始发生微小的偏离。每一次偏离都伴随着巨大的能量消耗和精确的调整。最终，在陨石距离艾瑞斯星球仅有几千公里的地方，它的飞行方向发生了决定性的改变，朝着宇宙深处的一个寂静区域飞去，最终消失在茫茫星海之中。

艾瑞斯星球得救了。整个星球都沉浸在巨大的喜悦和庆幸之中。这次事件不仅展现了赛尔人高超的智慧和勇气，更让他们对宇宙的敬畏之心油然而生。他们明白，即使拥有最先进的科技，也无法完全掌控宇宙的规律，而与自然和谐共处，才是生存之道。从此，赛尔人更加珍视自己的家园，并致力于探索宇宙的奥秘，同时守护着这颗美丽的蓝色星球。


下面这段在流式过程中会出现 `- *` / `-` / `>` 这类“危险尾巴”，要求不断流、不卡死、最终渲染正确：

- item 1
- item 2
- *

> quote start
> - list in quote

<think>
this is a think block that may arrive in chunks
</think>

下面是一个 **未声明语言** 的 diff，用来测试自动识别（应显示为 diff，并在最终渲染中高亮）：

```
diff --git a/lib/a.dart b/lib/a.dart
index 1111111..2222222 100644
--- a/lib/a.dart
+++ b/lib/a.dart
@@ -1,3 +1,4 @@
 class A {
-  final int x = 1;
+  final int x = 2;
+  final int y = 3;
 }
```
''';
}
