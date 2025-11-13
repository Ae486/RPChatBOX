import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_highlight/flutter_highlight.dart';
import 'package:flutter_highlight/themes/github.dart';
import 'package:flutter_highlight/themes/monokai-sublime.dart';
import '/utils/global_toast.dart';

/// 增强代码块组件
/// 功能：简洁的 Header (语言标签 + 复制按钮) + 代码内容
class EnhancedCodeBlock extends StatefulWidget {
  final String code;
  final String language;
  final bool isDark;

  const EnhancedCodeBlock({
    super.key,
    required this.code,
    required this.language,
    required this.isDark,
  });

  @override
  State<EnhancedCodeBlock> createState() => _EnhancedCodeBlockState();
}

class _EnhancedCodeBlockState extends State<EnhancedCodeBlock> {
  bool _copied = false;
  final ScrollController _scrollController = ScrollController();

  @override
  void initState() {
    super.initState();
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  void _copyToClipboard() async {
    await Clipboard.setData(ClipboardData(text: widget.code));
    if (!mounted) return;
    
    setState(() => _copied = true);
    
    GlobalToast.showSuccess(
      context,
      '代码已复制到剪贴板',
    );
    

    Future.delayed(const Duration(seconds: 2), () {
      if (mounted) setState(() => _copied = false);
    });
  }

  @override
  Widget build(BuildContext context) {
    // 🔍 调试：验证此组件是否被调用
    debugPrint('🔵 EnhancedCodeBlock.build() - language: ${widget.language}, code length: ${widget.code.length}');
    
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      decoration: BoxDecoration(
        color: widget.isDark ? const Color(0xFF1E1E1E) : const Color(0xFFECECEC),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          _buildHeader(),
          _buildCodeContent(),
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
            Container(
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
          
          const Spacer(),
          
          // 复制按钮
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
    // 🔍 调试：验证滚动组件是否被构建
    debugPrint('🟢 EnhancedCodeBlock._buildCodeContent() - 使用Scrollbar + SingleChildScrollView');
    
    return Scrollbar(
      controller: _scrollController,
      thumbVisibility: false,
      thickness: 6,
      radius: const Radius.circular(3),
      child: SingleChildScrollView(
        controller: _scrollController,
        scrollDirection: Axis.horizontal,
        physics: const ClampingScrollPhysics(),
        padding: const EdgeInsets.all(16),
        child: HighlightView(
          widget.code,
          language: widget.language,
          theme: widget.isDark ? monokaiSublimeTheme : githubTheme,
          padding: EdgeInsets.zero,
          textStyle: const TextStyle(
            fontFamily: 'monospace',
            fontSize: 13,
            height: 1.5,
            letterSpacing: 0.3,
          ),
        ),
      ),
    );
  }
}
