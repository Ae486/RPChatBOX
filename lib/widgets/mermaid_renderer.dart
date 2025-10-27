import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:webview_flutter/webview_flutter.dart';

/// Mermaid 图表渲染器
/// 使用 WebView + Mermaid.js 渲染流程图、时序图等
class MermaidRenderer extends StatefulWidget {
  final String mermaidCode;
  final bool isDark;
  final double? height;

  const MermaidRenderer({
    super.key,
    required this.mermaidCode,
    this.isDark = false,
    this.height,
  });

  @override
  State<MermaidRenderer> createState() => _MermaidRendererState();
}

class _MermaidRendererState extends State<MermaidRenderer> {
  late WebViewController _controller;
  double _webViewHeight = 300; // 默认高度
  bool _isLoading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _initializeWebView();
  }

  Future<void> _initializeWebView() async {
    try {
      // Windows 平台暂不支持 WebView
      if (Platform.isWindows || Platform.isLinux || Platform.isMacOS) {
        setState(() {
          _error = '桌面平台暂不支持 Mermaid 渲染，请使用 Android/iOS 版本';
          _isLoading = false;
        });
        return;
      }
      
      // 加载 HTML 模板
      final template = await rootBundle.loadString('assets/web/mermaid_template.html');
      
      // 替换模板变量
      final html = template
          .replaceAll('{{MERMAID_CODE}}', _escapeMermaidCode(widget.mermaidCode))
          .replaceAll('{{THEME}}', widget.isDark ? 'dark' : 'default');
      
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
              debugPrint('Mermaid WebView error: ${error.description}');
              setState(() {
                _error = error.description;
                _isLoading = false;
              });
            },
          ),
        )
        ..loadHtmlString(html);
    } catch (e) {
      debugPrint('Mermaid initialization error: $e');
      setState(() {
        _error = e.toString();
        _isLoading = false;
      });
    }
  }

  /// 获取 WebView 实际高度
  Future<void> _getWebViewHeight() async {
    try {
      // 执行 JavaScript 获取内容高度
      final heightStr = await _controller.runJavaScriptReturningResult(
        'document.getElementById("diagram").scrollHeight'
      );
      
      final height = double.tryParse(heightStr.toString()) ?? 300;
      
      setState(() {
        _webViewHeight = height + 32; // 加上 padding
      });
    } catch (e) {
      debugPrint('Failed to get WebView height: $e');
    }
  }

  /// 转义 Mermaid 代码中的特殊 HTML 字符
  String _escapeMermaidCode(String code) {
    // 注意：不要过度转义，Mermaid 需要保留原始语法
    return code
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;');
  }

  @override
  Widget build(BuildContext context) {
    if (_error != null) {
      return _buildErrorWidget();
    }

    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      decoration: BoxDecoration(
        color: widget.isDark ? Colors.grey.shade900 : Colors.grey.shade50,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: widget.isDark ? Colors.grey.shade700 : Colors.grey.shade300,
        ),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: Stack(
          children: [
            SizedBox(
              height: widget.height ?? _webViewHeight,
              child: WebViewWidget(controller: _controller),
            ),
            if (_isLoading)
              Positioned.fill(
                child: Container(
                  color: widget.isDark ? Colors.grey.shade900 : Colors.grey.shade50,
                  child: const Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        CircularProgressIndicator(),
                        SizedBox(height: 8),
                        Text('正在渲染图表...'),
                      ],
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildErrorWidget() {
    // 桌面平台：显示为代码块
    if (_error != null && _error!.contains('桌面平台')) {
      return Container(
        margin: const EdgeInsets.symmetric(vertical: 8),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: widget.isDark ? Colors.grey.shade900 : Colors.grey.shade100,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: widget.isDark ? Colors.grey.shade700 : Colors.grey.shade300,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                Icon(
                  Icons.info_outline,
                  color: Colors.blue.shade700,
                  size: 16,
                ),
                const SizedBox(width: 8),
                Text(
                  'Mermaid 代码（桌面平台仅显示源码）',
                  style: TextStyle(
                    color: widget.isDark ? Colors.grey.shade400 : Colors.grey.shade700,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: widget.isDark ? Colors.black : Colors.white,
                borderRadius: BorderRadius.circular(6),
              ),
              child: SelectableText(
                widget.mermaidCode,
                style: const TextStyle(
                  fontFamily: 'Consolas, Monaco, monospace',
                  fontSize: 13,
                  height: 1.5,
                ),
              ),
            ),
          ],
        ),
      );
    }
    
    // 其他错误：显示错误信息
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.red.shade50,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.red.shade300),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Icon(Icons.error_outline, color: Colors.red.shade700),
              const SizedBox(width: 8),
              Text(
                'Mermaid 渲染失败',
                style: TextStyle(
                  color: Colors.red.shade700,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            _error ?? '未知错误',
            style: TextStyle(
              color: Colors.red.shade900,
              fontSize: 12,
              fontFamily: 'monospace',
            ),
          ),
          const SizedBox(height: 8),
          ExpansionTile(
            title: const Text('查看原始代码'),
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                color: Colors.grey.shade200,
                child: SelectableText(
                  widget.mermaidCode,
                  style: const TextStyle(
                    fontFamily: 'monospace',
                    fontSize: 12,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

