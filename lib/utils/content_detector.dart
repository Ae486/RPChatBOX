import 'dart:core';

/// 内容类型检测器
/// 用于判断消息内容包含哪些特殊格式
class ContentDetector {
  /// 检测是否包含 Mermaid 图表
  static bool containsMermaid(String content) {
    return content.contains('```mermaid') || 
           content.contains('~~~mermaid');
  }

  /// 检测是否包含复杂 LaTeX（需要 WebView 渲染）
  static bool containsComplexLatex(String content) {
    if (!content.contains('\$')) return false;

    // 检测复杂 LaTeX 特征（WebView渲染）
    final webviewPatterns = [
      r'\begin{equation}',        // 方程环境
      r'\begin{align}',           // 对齐环境
      r'\begin{gather}',          // 聚集环境
      r'\begin{multline}',        // 多行环境
      r'\begin{split}',           // 分割环境
      r'\begin{cases}',           // 分段函数
      r'\begin{array}',           // 数组环境
      r'\begin{matrix}',          // 矩阵环境
      r'\begin{pmatrix}',         // 括号矩阵
      r'\begin{bmatrix}',         // 方括号矩阵
      r'\begin{vmatrix}',         // 竖线矩阵
      r'\begin{Vmatrix}',         // 双竖线矩阵
      r'\begin{bmatrix}',         // 方括号矩阵
      r'\begin{tikzpicture}',     // TikZ图形
      r'\begin{table}',           // 表格环境
      r'\begin{tabular}',         // 表格
      r'\includegraphics',        // 插入图片
      r'\href{',                  // 超链接
      r'\url{',                   // URL
      r'\cite{',                  // 引用
      r'\ref{',                   // 引用
      r'\label{',                 // 标签
      r'\bibliography',           // 参考文献
      r'\bibitem{',               // 参考文献条目
      r'\newcommand',             // 新命令
      r'\renewcommand',           // 重定义命令
      r'\def',                    // 定义命令
      r'\let',                    // 赋值命令
    ];

    for (var pattern in webviewPatterns) {
      if (content.contains(pattern)) {
        return true;
      }
    }

    return false;
  }

  /// 检测是否包含标准 LaTeX（latext支持）
  static bool containsStandardLatex(String content) {
    if (!content.contains('\$')) return false;

    // 标准LaTeX模式（latext原生支持）
    final standardPatterns = [
      r'\frac{',                  // 分数
      r'\sqrt{',                  // 根号
      r'\sqrt[',                  // 带指数根号
      r'\sum_{',                  // 求和
      r'\sum^',                   // 求和上限
      r'\int_{',                  // 积分
      r'\int^',                   // 积分上限
      r'\lim_{',                  // 极限
      r'\lim_{',                  // 极限
      r'\prod_{',                 // 乘积
      r'\prod^',                  // 乘积上限
      r'\bigcup_{',               // 大并集
      r'\bigcap_{',               // 大交集
      r'\bigcup^',                // 大并集上限
      r'\bigcap^',                // 大交集上限
      r'\cup',                    // 并集
      r'\cap',                    // 交集
      r'\subset',                 // 子集
      r'\subseteq',               // 子集或等于
      r'\supset',                 // 超集
      r'\supseteq',               // 超集或等于
      r'\in',                     // 属于
      r'\notin',                  // 不属于
      r'\forall',                 // 对所有
      r'\exists',                 // 存在
      r'\nexists',                // 不存在
      r'\nabla',                  // 哈密顿算子
      r'\partial',                // 偏导数
      r'\infty',                  // 无穷
      r'\alpha',                  // 希腊字母
      r'\beta',
      r'\gamma',
      r'\delta',
      r'\epsilon',
      r'\zeta',
      r'\eta',
      r'\theta',
      r'\iota',
      r'\kappa',
      r'\lambda',
      r'\mu',
      r'\nu',
      r'\xi',
      r'\pi',
      r'\rho',
      r'\sigma',
      r'\tau',
      r'\upsilon',
      r'\phi',
      r'\chi',
      r'\psi',
      r'\omega',
      r'\Gamma',                  // 大写希腊字母
      r'\Delta',
      r'\Theta',
      r'\Lambda',
      r'\Xi',
      r'\Pi',
      r'\Sigma',
      r'\Upsilon',
      r'\Phi',
      r'\Psi',
      r'\Omega',
      r'\sin',                    // 三角函数
      r'\cos',
      r'\tan',
      r'\cot',
      r'\sec',
      r'\csc',
      r'\arcsin',
      r'\arccos',
      r'\arctan',
      r'\ln',                     // 对数
      r'\log',
      r'\exp',
      r'\sinh',                   // 双曲函数
      r'\cosh',
      r'\tanh',
      r'\left(',                  // 自动调整大小的括号
      r'\right)',
      r'\left[',
      r'\right]',
      r'\left\{',
      r'\right\}',
      r'\left|',
      r'\right|',
      r'\overline{',              // 上划线
      r'\underline{',             // 下划线
      r'\bar{',                   // 上划线
      r'\vec{',                   // 向量
      r'\hat{',                   // 尖帽
      r'\dot{',                   // 点
      r'\ddot{',                  // 双点
      r'\mathbb{',                // 黑板粗体
      r'\mathcal{',               // 花体
      r'\mathfrak{',              // 哥特体
      r'\mathscr{',               // 手写体
      r'\mathrm{',                // 罗马体
      r'\mathbf{',                // 粗体
      r'\mathit{',                // 斜体
      r'\mathsf{',                // 无衬线体
      r'\mathtt{',                // 打字机体
    ];

    return standardPatterns.any((pattern) => content.contains(pattern));
  }

  /// 提取所有 Mermaid 代码块
  static List<String> extractMermaidBlocks(String content) {
    final blocks = <String>[];
    final regex = RegExp(
      r'```mermaid\s*([\s\S]*?)```',
      multiLine: true,
    );
    
    final matches = regex.allMatches(content);
    for (var match in matches) {
      final code = match.group(1)?.trim();
      if (code != null && code.isNotEmpty) {
        blocks.add(code);
      }
    }
    
    return blocks;
  }

  /// 检测 Mermaid 图表类型
  static String detectMermaidType(String mermaidCode) {
    final firstLine = mermaidCode.trim().split('\n').first.toLowerCase();
    
    if (firstLine.startsWith('graph')) return 'flowchart';
    if (firstLine.startsWith('sequencediagram')) return 'sequence';
    if (firstLine.startsWith('classDiagram')) return 'class';
    if (firstLine.startsWith('stateDiagram')) return 'state';
    if (firstLine.startsWith('erDiagram')) return 'er';
    if (firstLine.startsWith('gantt')) return 'gantt';
    if (firstLine.startsWith('pie')) return 'pie';
    if (firstLine.startsWith('gitGraph')) return 'git';
    
    return 'unknown';
  }

  /// 移除内容中的 Mermaid 代码块（用于混合渲染）
  static String removeMermaidBlocks(String content) {
    return content.replaceAll(
      RegExp(r'```mermaid\s*[\s\S]*?```', multiLine: true),
      '',
    ).trim();
  }
}

