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
    
    // 检测复杂 LaTeX 特征
    final complexPatterns = [
      r'\begin{',      // 环境（矩阵、多行公式等）
      r'\mathbb{',     // 黑板粗体
      r'\mathcal{',    // 花体
      r'\mathfrak{',   // 哥特体
      r'\cases',       // 分段函数
      r'\array',       // 数组
      r'\align',       // 对齐
      r'\\\\',         // 多行（双反斜杠）
    ];
    
    for (var pattern in complexPatterns) {
      if (content.contains(pattern)) {
        return true;
      }
    }
    
    return false;
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

