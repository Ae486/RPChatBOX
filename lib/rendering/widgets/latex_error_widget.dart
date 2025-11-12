import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// LaTeX渲染错误提示组件
/// 提供友好的错误显示和调试信息
class LaTeXErrorWidget extends StatefulWidget {
  final String latex;
  final String errorMessage;
  final bool isBlockMath;
  final bool isDark;

  const LaTeXErrorWidget({
    super.key,
    required this.latex,
    required this.errorMessage,
    this.isBlockMath = false,
    this.isDark = false,
  });

  @override
  State<LaTeXErrorWidget> createState() => _LaTeXErrorWidgetState();
}

class _LaTeXErrorWidgetState extends State<LaTeXErrorWidget> {
  bool _showDetails = false;
  bool _copied = false;

  void _copyToClipboard() async {
    await Clipboard.setData(ClipboardData(text: widget.latex));
    if (!mounted) return;
    
    setState(() => _copied = true);
    
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('LaTeX代码已复制到剪贴板'),
        duration: Duration(seconds: 2),
      ),
    );

    Future.delayed(const Duration(seconds: 2), () {
      if (mounted) setState(() => _copied = false);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: widget.isBlockMath 
        ? const EdgeInsets.symmetric(vertical: 8)
        : const EdgeInsets.symmetric(horizontal: 2, vertical: 2),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: widget.isDark 
          ? Colors.red.shade900.withValues(alpha: 0.2)
          : Colors.red.shade50,
        border: Border.all(
          color: widget.isDark ? Colors.red.shade700 : Colors.red.shade300,
          width: 1,
        ),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // 错误标题
          Row(
            children: [
              Icon(
                Icons.error_outline,
                color: widget.isDark ? Colors.red.shade300 : Colors.red.shade700,
                size: 20,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'LaTeX渲染失败',
                  style: TextStyle(
                    fontWeight: FontWeight.w600,
                    fontSize: 14,
                    color: widget.isDark ? Colors.red.shade300 : Colors.red.shade700,
                  ),
                ),
              ),
              // 复制按钮
              Material(
                color: Colors.transparent,
                child: InkWell(
                  onTap: _copyToClipboard,
                  borderRadius: BorderRadius.circular(4),
                  child: Padding(
                    padding: const EdgeInsets.all(4),
                    child: Icon(
                      _copied ? Icons.check : Icons.content_copy,
                      size: 16,
                      color: _copied 
                        ? Colors.green
                        : (widget.isDark ? Colors.grey.shade400 : Colors.grey.shade600),
                    ),
                  ),
                ),
              ),
              // 展开/收起按钮
              Material(
                color: Colors.transparent,
                child: InkWell(
                  onTap: () => setState(() => _showDetails = !_showDetails),
                  borderRadius: BorderRadius.circular(4),
                  child: Padding(
                    padding: const EdgeInsets.all(4),
                    child: Icon(
                      _showDetails ? Icons.expand_less : Icons.expand_more,
                      size: 16,
                      color: widget.isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                    ),
                  ),
                ),
              ),
            ],
          ),
          
          const SizedBox(height: 8),
          
          // 简短说明
          Text(
            '无法渲染此数学公式，可能包含不支持的LaTeX语法',
            style: TextStyle(
              fontSize: 13,
              color: widget.isDark ? Colors.grey.shade400 : Colors.grey.shade700,
            ),
          ),
          
          // 原始LaTeX代码（总是显示）
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: widget.isDark 
                ? Colors.grey.shade900.withValues(alpha: 0.5)
                : Colors.grey.shade100,
              borderRadius: BorderRadius.circular(4),
            ),
            child: SelectableText(
              widget.isBlockMath 
                ? '\$\$${widget.latex}\$\$'
                : '\$${widget.latex}\$',
              style: const TextStyle(
                fontFamily: 'monospace',
                fontSize: 13,
              ),
            ),
          ),
          
          // 详细错误信息（可展开）
          if (_showDetails) ...[
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: widget.isDark 
                  ? Colors.grey.shade800.withValues(alpha: 0.5)
                  : Colors.grey.shade200,
                borderRadius: BorderRadius.circular(4),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '错误详情：',
                    style: TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 12,
                      color: widget.isDark ? Colors.grey.shade300 : Colors.grey.shade800,
                    ),
                  ),
                  const SizedBox(height: 4),
                  SelectableText(
                    widget.errorMessage,
                    style: TextStyle(
                      fontFamily: 'monospace',
                      fontSize: 11,
                      color: widget.isDark ? Colors.grey.shade400 : Colors.grey.shade700,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '💡 建议：',
                    style: TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 12,
                      color: widget.isDark ? Colors.grey.shade300 : Colors.grey.shade800,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '• 检查LaTeX语法是否正确\n'
                    '• 某些高级命令可能不被支持\n'
                    '• 尝试简化公式或使用基础语法',
                    style: TextStyle(
                      fontSize: 11,
                      color: widget.isDark ? Colors.grey.shade400 : Colors.grey.shade700,
                      height: 1.4,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// 简化的LaTeX错误组件（内联使用）
class InlineLaTeXErrorWidget extends StatelessWidget {
  final String latex;
  final bool isDark;

  const InlineLaTeXErrorWidget({
    super.key,
    required this.latex,
    this.isDark = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: isDark 
          ? Colors.red.shade900.withValues(alpha: 0.3)
          : Colors.red.shade100.withValues(alpha: 0.7),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(
          color: isDark ? Colors.red.shade700 : Colors.red.shade400,
          width: 1,
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.warning_amber_rounded,
            size: 14,
            color: isDark ? Colors.red.shade300 : Colors.red.shade700,
          ),
          const SizedBox(width: 4),
          Flexible(
            child: Text(
              '\$$latex\$',
              style: TextStyle(
                fontFamily: 'monospace',
                fontSize: 13,
                color: isDark ? Colors.red.shade200 : Colors.red.shade900,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}
