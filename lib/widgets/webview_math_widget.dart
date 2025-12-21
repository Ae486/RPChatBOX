import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:flutter_spinkit/flutter_spinkit.dart';
import '../rendering/widgets/latex_error_widget.dart';

/// WebView LaTeX 渲染器
/// 用于渲染复杂 LaTeX 公式（矩阵、多行、特殊符号等）
class WebViewMathWidget extends StatefulWidget {
  final String latex;
  final bool isBlockMath;
  final TextStyle? textStyle;
  final bool isDark;

  const WebViewMathWidget({
    super.key,
    required this.latex,
    this.isBlockMath = false,
    this.textStyle,
    this.isDark = false,
  });

  @override
  State<WebViewMathWidget> createState() => _WebViewMathWidgetState();
}

class _WebViewMathWidgetState extends State<WebViewMathWidget> {
  late WebViewController _controller;
  double _webViewHeight = 60; // 默认高度
  bool _isLoading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _initializeWebView();
  }

  Future<void> _initializeWebView() async {
    try {
      // 桌面平台暂不支持 WebView，直接返回错误让系统降级到原生渲染
      if (Platform.isWindows || Platform.isLinux || Platform.isMacOS) {
        setState(() {
          _error = 'Desktop platform: fallback to native rendering';
          _isLoading = false;
        });
        return;
      }
      
      // 加载 HTML 模板
      final template = await rootBundle.loadString('assets/web/katex_template.html');
      
      // 计算字体大小
      final fontSize = widget.textStyle?.fontSize ?? (widget.isBlockMath ? 16.0 : 15.0);
      
      // 替换模板变量
      final html = template
          .replaceAll('{{LATEX_CODE}}', _escapeLatex(widget.latex))
          .replaceAll('{{FONT_SIZE}}', fontSize.toString())
          .replaceAll('{{DISPLAY_MODE}}', widget.isBlockMath.toString())
          .replaceAll('{{THEME}}', widget.isDark ? 'dark' : '');
      
      // 创建 WebView 控制器
      _controller = WebViewController()
        ..setJavaScriptMode(JavaScriptMode.unrestricted)
        ..setBackgroundColor(Colors.transparent)
        ..setNavigationDelegate(
          NavigationDelegate(
            onPageFinished: (String url) {
              setState(() {
                _isLoading = false;
              });
              _getWebViewHeight();
            },
            onWebResourceError: (WebResourceError error) {
              debugPrint('LaTeX WebView error: ${error.description}');
              setState(() {
                _error = error.description;
                _isLoading = false;
              });
            },
          ),
        )
        ..loadHtmlString(html);
    } catch (e) {
      debugPrint('LaTeX WebView initialization error: $e');
      setState(() {
        _error = e.toString();
        _isLoading = false;
      });
    }
  }

  /// 获取 WebView 实际高度
  Future<void> _getWebViewHeight() async {
    try {
      final heightStr = await _controller.runJavaScriptReturningResult(
        'document.getElementById("math").scrollHeight + 24'
      );
      
      final height = double.tryParse(heightStr.toString()) ?? 60;
      
      setState(() {
        _webViewHeight = height;
      });
    } catch (e) {
      debugPrint('Failed to get LaTeX height: $e');
    }
  }

  /// 转义 LaTeX 代码中的特殊字符（用于 JavaScript 字符串）
  String _escapeLatex(String latex) {
    return latex
        .replaceAll(r'\', r'\\')     // 反斜杠必须先转义
        .replaceAll('`', r'\`')       // 反引号
        .replaceAll('\$', r'\$')      // 美元符号
        .replaceAll('\n', r'\n')      // 换行符
        .replaceAll('\r', r'\r')      // 回车符
        .replaceAll('"', r'\"')       // 双引号
        .replaceAll("'", r"\'");      // 单引号
  }

  @override
  Widget build(BuildContext context) {
    if (_error != null) {
      return _buildErrorWidget();
    }

    if (widget.isBlockMath) {
      // 块级公式
      return Container(
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 8),
        margin: const EdgeInsets.symmetric(vertical: 8),
        child: SizedBox(
          height: _webViewHeight,
          child: Stack(
            children: [
              WebViewWidget(controller: _controller),
              if (_isLoading)
                Center(
                  child: SpinKitThreeBounce(
                    color: Colors.grey,
                    size: 16.0,
                  ),
                ),
            ],
          ),
        ),
      );
    } else {
      // 内联公式
      return SizedBox(
        height: _webViewHeight,
        child: Stack(
          children: [
            WebViewWidget(controller: _controller),
            if (_isLoading)
              Center(
                child: SpinKitThreeBounce(
                  color: Colors.grey,
                  size: 12.0,
                ),
              ),
          ],
        ),
      );
    }
  }

  Widget _buildErrorWidget() {
    // 🔥 使用统一的LaTeX错误组件，而不是橙色警告框
    if (widget.isBlockMath) {
      return LaTeXErrorWidget(
        latex: widget.latex,
        errorMessage: _error ?? 'WebView rendering not supported on desktop platform',
        isBlockMath: true,
        isDark: widget.isDark,
      );
    } else {
      return InlineLaTeXErrorWidget(
        latex: widget.latex,
        isDark: widget.isDark,
      );
    }
  }
}

