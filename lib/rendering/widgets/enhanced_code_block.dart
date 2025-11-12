import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_highlight/flutter_highlight.dart';
import 'package:flutter_highlight/themes/github.dart';
import 'package:flutter_highlight/themes/monokai-sublime.dart';

/// 增强代码块组件
/// 功能：行号、折叠、优化的复制按钮
class EnhancedCodeBlock extends StatefulWidget {
  final String code;
  final String language;
  final bool isDark;
  final bool showLineNumbers;
  final bool collapsible;
  final int maxVisibleLines;

  const EnhancedCodeBlock({
    super.key,
    required this.code,
    required this.language,
    required this.isDark,
    this.showLineNumbers = true,
    this.collapsible = true,
    this.maxVisibleLines = 20,
  });

  @override
  State<EnhancedCodeBlock> createState() => _EnhancedCodeBlockState();
}

class _EnhancedCodeBlockState extends State<EnhancedCodeBlock> {
  bool _copied = false;
  bool _collapsed = false;
  late List<String> _lines;
  late bool _shouldCollapse;

  @override
  void initState() {
    super.initState();
    _lines = widget.code.split('\n');
    _shouldCollapse = widget.collapsible && _lines.length > widget.maxVisibleLines;
    // 默认展开（即使可折叠，仅显示折叠按钮）
    _collapsed = false;
  }

  void _copyToClipboard() async {
    await Clipboard.setData(ClipboardData(text: widget.code));
    if (!mounted) return;
    
    setState(() => _copied = true);
    
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('代码已复制到剪贴板'),
        duration: Duration(seconds: 2),
      ),
    );

    Future.delayed(const Duration(seconds: 2), () {
      if (mounted) setState(() => _copied = false);
    });
  }

  void _toggleCollapse() {
    setState(() => _collapsed = !_collapsed);
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      decoration: BoxDecoration(
        color: widget.isDark ? const Color(0xFF1E1E1E) : const Color(0xFFF6F8FA),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: widget.isDark ? const Color(0xFF353535) : const Color(0xFFD0D7DE),
          width: 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _buildHeader(),
          if (!_collapsed) _buildCodeContent(),
          if (_collapsed) _buildCollapsedPlaceholder(),
        ],
      ),
    );
  }

  Widget _buildHeader() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: widget.isDark ? const Color(0xFF2D2D2D) : const Color(0xFFEEF1F4),
        borderRadius: const BorderRadius.only(
          topLeft: Radius.circular(7),
          topRight: Radius.circular(7),
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.max,
        children: [
          // 语言标签
          if (widget.language != 'plaintext')
            Flexible(
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: widget.isDark ? Colors.blue.shade800 : Colors.blue.shade100,
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(
                  widget.language.toUpperCase(),
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                    color: widget.isDark ? Colors.blue.shade200 : Colors.blue.shade900,
                    letterSpacing: 0.5,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ),
          
          const Spacer(),
          
          // 折叠按钮
          if (_shouldCollapse)
            Material(
              color: Colors.transparent,
              child: InkWell(
                onTap: _toggleCollapse,
                borderRadius: BorderRadius.circular(4),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        _collapsed ? Icons.unfold_more : Icons.unfold_less,
                        size: 16,
                        color: widget.isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                      ),
                      const SizedBox(width: 4),
                      Text(
                        _collapsed 
                          ? '展开 (${_lines.length} 行)' 
                          : '折叠',
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w500,
                          color: widget.isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          
          // 🆕 复制按钮（固定在最右侧）
          Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: _copyToClipboard,
              borderRadius: BorderRadius.circular(4),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
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
        ],
      ),
    );
  }

  Widget _buildCodeContent() {
    return Container(
      padding: const EdgeInsets.all(16),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: !widget.showLineNumbers
            ? HighlightView(
                widget.code,
                language: widget.language,
                theme: widget.isDark ? monokaiSublimeTheme : githubTheme,
                padding: EdgeInsets.zero,
                textStyle: const TextStyle(
                  fontFamily: 'monospace',
                  fontSize: 13,
                ),
              )
            : IntrinsicHeight(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // 行号列
                    Container(
                      padding: const EdgeInsets.only(right: 16),
                      decoration: BoxDecoration(
                        border: Border(
                          right: BorderSide(
                            color: widget.isDark 
                              ? Colors.grey.shade700 
                              : Colors.grey.shade300,
                            width: 1,
                          ),
                        ),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: List.generate(
                          _lines.length,
                          (index) => Padding(
                            padding: const EdgeInsets.symmetric(vertical: 1),
                            child: Text(
                              '${index + 1}',
                              style: TextStyle(
                                fontFamily: 'monospace',
                                fontSize: 13,
                                color: widget.isDark 
                                  ? Colors.grey.shade600 
                                  : Colors.grey.shade500,
                                height: 1.5,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                    
                    const SizedBox(width: 16),
                    
                    // 代码内容
                    HighlightView(
                      widget.code,
                      language: widget.language,
                      theme: widget.isDark ? monokaiSublimeTheme : githubTheme,
                      padding: EdgeInsets.zero,
                      textStyle: const TextStyle(
                        fontFamily: 'monospace',
                        fontSize: 13,
                      ),
                    ),
                  ],
                ),
              ),
      ),
    );
  }

  Widget _buildCollapsedPlaceholder() {
    return Container(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          // 显示前几行代码预览
          ...List.generate(
            3.clamp(0, _lines.length),
            (index) => Text(
              _lines[index],
              style: TextStyle(
                fontFamily: 'monospace',
                fontSize: 13,
                color: widget.isDark ? Colors.grey.shade500 : Colors.grey.shade600,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            '... ${_lines.length - 3} 行已折叠',
            style: TextStyle(
              fontSize: 12,
              color: widget.isDark ? Colors.grey.shade600 : Colors.grey.shade500,
              fontStyle: FontStyle.italic,
            ),
          ),
        ],
      ),
    );
  }
}
