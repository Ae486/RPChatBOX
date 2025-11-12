import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';

/// Markdown样式辅助类
/// 提供统一的、增强的Markdown样式配置
class MarkdownStyleHelper {
  /// 获取优化的样式表
  static MarkdownStyleSheet getStyleSheet({
    required bool isDark,
    TextStyle? baseTextStyle,
  }) {
    final base = baseTextStyle ?? const TextStyle(fontSize: 15);
    
    return MarkdownStyleSheet(
      // 段落样式
      p: base.copyWith(
        height: 1.6,
        letterSpacing: 0.2,
      ),
      
      // 标题样式
      h1: base.copyWith(
        fontSize: 28,
        fontWeight: FontWeight.bold,
        height: 1.4,
        color: isDark ? Colors.white : Colors.black87,
      ),
      h2: base.copyWith(
        fontSize: 24,
        fontWeight: FontWeight.bold,
        height: 1.4,
        color: isDark ? Colors.white : Colors.black87,
      ),
      h3: base.copyWith(
        fontSize: 20,
        fontWeight: FontWeight.w600,
        height: 1.4,
        color: isDark ? Colors.white : Colors.black87,
      ),
      h4: base.copyWith(
        fontSize: 18,
        fontWeight: FontWeight.w600,
        height: 1.4,
      ),
      h5: base.copyWith(
        fontSize: 16,
        fontWeight: FontWeight.w600,
        height: 1.4,
      ),
      h6: base.copyWith(
        fontSize: 15,
        fontWeight: FontWeight.w600,
        height: 1.4,
      ),
      
      // 内联代码
      code: TextStyle(
        backgroundColor: isDark 
          ? Colors.grey.shade800.withValues(alpha: 0.5)
          : Colors.grey.shade300.withValues(alpha: 0.5),
        fontFamily: 'monospace',
        fontSize: 13,
        color: isDark ? Colors.blue.shade300 : Colors.blue.shade700,
        letterSpacing: 0,
      ),
      
      // 代码块
      codeblockPadding: const EdgeInsets.all(12),
      codeblockDecoration: BoxDecoration(
        color: isDark ? const Color(0xFF1E1E1E) : const Color(0xFFF6F8FA),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: isDark ? const Color(0xFF353535) : const Color(0xFFD0D7DE),
          width: 1,
        ),
      ),
      
      // 引用块
      blockquote: base.copyWith(
        color: isDark ? Colors.grey.shade400 : Colors.grey.shade700,
        fontStyle: FontStyle.italic,
        height: 1.6,
      ),
      blockquotePadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      blockquoteDecoration: BoxDecoration(
        border: Border(
          left: BorderSide(
            color: isDark ? Colors.blue.shade700 : Colors.blue.shade300,
            width: 4,
          ),
        ),
        color: isDark 
          ? Colors.blue.shade900.withValues(alpha: 0.1)
          : Colors.blue.shade50.withValues(alpha: 0.3),
        borderRadius: const BorderRadius.only(
          topRight: Radius.circular(4),
          bottomRight: Radius.circular(4),
        ),
      ),
      
      // 列表
      listBullet: base.copyWith(
        color: isDark ? Colors.grey.shade400 : Colors.grey.shade700,
      ),
      listBulletPadding: const EdgeInsets.only(right: 8),
      listIndent: 24,
      
      // 链接
      a: base.copyWith(
        color: isDark ? Colors.blue.shade300 : Colors.blue.shade700,
        decoration: TextDecoration.underline,
      ),
      
      // 强调
      em: base.copyWith(fontStyle: FontStyle.italic),
      strong: base.copyWith(fontWeight: FontWeight.bold),
      del: base.copyWith(
        decoration: TextDecoration.lineThrough,
        color: isDark ? Colors.grey.shade500 : Colors.grey.shade600,
      ),
      
      // 表格
      tableBorder: TableBorder.all(
        color: isDark ? Colors.grey.shade700 : Colors.grey.shade800,
        width: 1,
      ),
      tableHead: base.copyWith(
        fontWeight: FontWeight.bold,
        backgroundColor: isDark ? Colors.grey.shade800 : Colors.grey.shade100,
      ),
      tableBody: base,
      tableCellsPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      tableColumnWidth: const FlexColumnWidth(),
      
      // 水平线
      horizontalRuleDecoration: BoxDecoration(
        border: Border(
          top: BorderSide(
            color: isDark ? Colors.grey.shade700 : Colors.grey.shade300,
            width: 1,
          ),
        ),
      ),
      
      // 图片
      img: base,
      
      // 复选框（任务列表）
      checkbox: base.copyWith(
        color: isDark ? Colors.blue.shade300 : Colors.blue.shade700,
      ),
      
      // 段落间距
      h1Padding: const EdgeInsets.only(top: 24, bottom: 16),
      h2Padding: const EdgeInsets.only(top: 20, bottom: 12),
      h3Padding: const EdgeInsets.only(top: 16, bottom: 8),
      h4Padding: const EdgeInsets.only(top: 12, bottom: 4),
      h5Padding: const EdgeInsets.only(top: 8, bottom: 4),
      h6Padding: const EdgeInsets.only(top: 8, bottom: 4),
      pPadding: const EdgeInsets.only(bottom: 12),
    );
  }
  
  /// 获取紧凑的样式表（用于对话气泡）
  static MarkdownStyleSheet getCompactStyleSheet({
    required bool isDark,
    TextStyle? baseTextStyle,
  }) {
    final standard = getStyleSheet(isDark: isDark, baseTextStyle: baseTextStyle);
    
    return standard.copyWith(
      // 减少标题间距
      h1Padding: const EdgeInsets.only(top: 16, bottom: 8),
      h2Padding: const EdgeInsets.only(top: 12, bottom: 6),
      h3Padding: const EdgeInsets.only(top: 8, bottom: 4),
      h4Padding: const EdgeInsets.only(top: 6, bottom: 2),
      h5Padding: const EdgeInsets.only(top: 4, bottom: 2),
      h6Padding: const EdgeInsets.only(top: 4, bottom: 2),
      
      // 减少段落间距
      pPadding: const EdgeInsets.only(bottom: 8),
      
      // 减少引用块间距
      blockquotePadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      
      // 减少列表缩进
      listIndent: 20,
    );
  }
}
