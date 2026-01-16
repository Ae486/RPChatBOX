/// INPUT: Mermaid 代码 + 平台能力（WebView/外部预览）+ 主题/高度
/// OUTPUT: MermaidRenderer - Mermaid 图表渲染（内嵌 WebView 或外部预览）
/// POS: UI 层 / Widgets - Mermaid 渲染底层（供 OwuiMermaidBlock/Demo 使用）

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_windows/webview_windows.dart' as windows_webview;

import '../chat_ui/owui/owui_icons.dart';
import '../design_system/design_tokens.dart';

/// Mermaid 图表渲染器
/// 使用 WebView + Mermaid.js 渲染流程图、时序图等
class MermaidRenderer extends StatefulWidget {
  final String mermaidCode;
  final bool isDark;
  final double? height;
  final bool includeOuterContainer;
  final EdgeInsets? margin;

  const MermaidRenderer({
    super.key,
    required this.mermaidCode,
    this.isDark = false,
    this.height,
    this.includeOuterContainer = true,
    this.margin,
  });

  @override
  State<MermaidRenderer> createState() => _MermaidRendererState();
}

class _MermaidRendererState extends State<MermaidRenderer> {
  WebViewController? _controller;
  windows_webview.WebviewController? _windowsController;
  double _webViewHeight = 300; // 默认高度
  bool _isLoading = true;
  String? _error;
  Uri? _previewUri;
  bool _isWindowsWebViewReady = false;

  @override
  void initState() {
    super.initState();
    _initializeWebView();
  }

  Future<void> _initializeWebView() async {
    try {
      // Windows 平台使用 webview_windows
      if (Platform.isWindows) {
        await _initializeWindowsWebView();
        return;
      }
      
      // Linux 平台仍使用外部预览
      if (Platform.isLinux) {
        setState(() {
          _error = '当前平台不支持内嵌 Mermaid 渲染，可使用“外部预览”。';
          _isLoading = false;
        });
        await _prepareExternalPreview();
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

  Future<void> _initializeWindowsWebView() async {
    try {
      _windowsController = windows_webview.WebviewController();
      await _windowsController!.initialize();
      
      // 加载 HTML 模板
      final template = await rootBundle.loadString('assets/web/mermaid_template.html');
      final html = template
          .replaceAll('{{MERMAID_CODE}}', _escapeMermaidCode(widget.mermaidCode))
          .replaceAll('{{THEME}}', widget.isDark ? 'dark' : 'default');
      
      // 写入临时文件并加载
      final dir = await getTemporaryDirectory();
      final file = File('${dir.path}${Platform.pathSeparator}mermaid_${DateTime.now().millisecondsSinceEpoch}.html');
      await file.writeAsString(html);
      
      await _windowsController!.setBackgroundColor(Colors.transparent);
      await _windowsController!.loadUrl(Uri.file(file.path).toString());
      
      if (mounted) {
        setState(() {
          _isWindowsWebViewReady = true;
          _isLoading = false;
        });
      }
    } catch (e) {
      debugPrint('Windows WebView initialization error: $e');
      // 降级到外部预览
      setState(() {
        _error = 'Windows WebView 初始化失败，使用外部预览';
        _isLoading = false;
      });
      await _prepareExternalPreview();
    }
  }

  Future<void> _prepareExternalPreview() async {
    try {
      final template = await rootBundle.loadString('assets/web/mermaid_template.html');
      final html = template
          .replaceAll('{{MERMAID_CODE}}', _escapeMermaidCode(widget.mermaidCode))
          .replaceAll('{{THEME}}', widget.isDark ? 'dark' : 'default');

      final dir = await getTemporaryDirectory();
      final file = File('${dir.path}${Platform.pathSeparator}mermaid_preview_${DateTime.now().millisecondsSinceEpoch}.html');
      await file.writeAsString(html);
      setState(() {
        _previewUri = Uri.file(file.path);
      });
    } catch (e) {
      debugPrint('Mermaid external preview prepare error: $e');
    }
  }

  Future<void> _openExternalPreview() async {
    final uri = _previewUri;
    if (uri == null) {
      await _prepareExternalPreview();
    }
    final finalUri = _previewUri;
    if (finalUri == null) return;

    await launchUrl(
      finalUri,
      mode: LaunchMode.externalApplication,
    );
  }

  Future<void> _copyMermaidCode() async {
    await Clipboard.setData(ClipboardData(text: widget.mermaidCode));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Mermaid 代码已复制到剪贴板')),
    );
  }

  /// 获取 WebView 实际高度
  Future<void> _getWebViewHeight() async {
    if (_controller == null) return;
    try {
      // 执行 JavaScript 获取内容高度
      final heightStr = await _controller!.runJavaScriptReturningResult(
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
  void dispose() {
    _windowsController?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_error != null) {
      return _buildErrorWidget();
    }

    // Windows 平台使用 webview_windows
    if (Platform.isWindows && _isWindowsWebViewReady && _windowsController != null) {
      return _buildWindowsWebView();
    }

    // 其他平台使用 webview_flutter
    if (_controller == null) {
      return _buildLoadingWidget();
    }

    final inner = ClipRRect(
      borderRadius: BorderRadius.circular(ChatBoxTokens.radius.small),
      child: Stack(
        children: [
          SizedBox(
            height: widget.height ?? _webViewHeight,
            child: WebViewWidget(controller: _controller!),
          ),
          if (_isLoading) _buildLoadingOverlay(),
        ],
      ),
    );

    if (!widget.includeOuterContainer) {
      return inner;
    }

    return Container(
      margin: widget.margin ?? EdgeInsets.symmetric(vertical: ChatBoxTokens.spacing.sm),
      decoration: BoxDecoration(
        color: widget.isDark ? Colors.grey.shade900 : Colors.grey.shade50,
        borderRadius: BorderRadius.circular(ChatBoxTokens.radius.small),
        border: Border.all(
          color: widget.isDark ? Colors.grey.shade700 : Colors.grey.shade300,
        ),
      ),
      child: inner,
    );
  }

  Widget _buildWindowsWebView() {
    final inner = ClipRRect(
      borderRadius: BorderRadius.circular(ChatBoxTokens.radius.small),
      child: SizedBox(
        height: widget.height ?? _webViewHeight,
        child: windows_webview.Webview(_windowsController!),
      ),
    );

    if (!widget.includeOuterContainer) {
      return inner;
    }

    return Container(
      margin: widget.margin ?? EdgeInsets.symmetric(vertical: ChatBoxTokens.spacing.sm),
      decoration: BoxDecoration(
        color: widget.isDark ? Colors.grey.shade900 : Colors.grey.shade50,
        borderRadius: BorderRadius.circular(ChatBoxTokens.radius.small),
        border: Border.all(
          color: widget.isDark ? Colors.grey.shade700 : Colors.grey.shade300,
        ),
      ),
      child: inner,
    );
  }

  Widget _buildLoadingWidget() {
    return Container(
      height: widget.height ?? _webViewHeight,
      margin: widget.margin ?? EdgeInsets.symmetric(vertical: ChatBoxTokens.spacing.sm),
      decoration: BoxDecoration(
        color: widget.isDark ? Colors.grey.shade900 : Colors.grey.shade50,
        borderRadius: BorderRadius.circular(ChatBoxTokens.radius.small),
      ),
      child: const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(),
            SizedBox(height: 8),
            Text('正在加载 WebView...'),
          ],
        ),
      ),
    );
  }

  Widget _buildLoadingOverlay() {
    return Positioned.fill(
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
    );
  }

  Widget _buildErrorWidget() {
    // 桌面平台：显示为代码块
    if (Platform.isWindows || Platform.isLinux) {
      return Container(
        margin: EdgeInsets.symmetric(vertical: ChatBoxTokens.spacing.sm),
        padding: EdgeInsets.all(ChatBoxTokens.spacing.lg),
        decoration: BoxDecoration(
          color: widget.isDark ? Colors.grey.shade900 : Colors.grey.shade100,
          borderRadius: BorderRadius.circular(ChatBoxTokens.radius.small),
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
                  OwuiIcons.info,
                  color: Colors.blue.shade700,
                  size: 16,
                ),
                SizedBox(width: ChatBoxTokens.spacing.sm),
                Text(
                  'Mermaid（桌面平台：源码 + 外部预览）',
                  style: TextStyle(
                    color: widget.isDark ? Colors.grey.shade400 : Colors.grey.shade700,
                    fontSize: 12,
                  ),
                ),
                const Spacer(),
                IconButton(
                  tooltip: '复制源码',
                  onPressed: _copyMermaidCode,
                  icon: Icon(
                    OwuiIcons.copy,
                    size: 16,
                    color: widget.isDark ? Colors.grey.shade300 : Colors.grey.shade700,
                  ),
                ),
                TextButton(
                  onPressed: _previewUri == null ? null : _openExternalPreview,
                  child: const Text('外部预览'),
                ),
              ],
            ),
            SizedBox(height: ChatBoxTokens.spacing.md),
            Container(
              padding: EdgeInsets.all(ChatBoxTokens.spacing.md),
              decoration: BoxDecoration(
                color: widget.isDark ? Colors.black : Colors.white,
                borderRadius: BorderRadius.circular(ChatBoxTokens.radius.xs),
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
      margin: EdgeInsets.symmetric(vertical: ChatBoxTokens.spacing.sm),
      padding: EdgeInsets.all(ChatBoxTokens.spacing.lg),
      decoration: BoxDecoration(
        color: Colors.red.shade50,
        borderRadius: BorderRadius.circular(ChatBoxTokens.radius.small),
        border: Border.all(color: Colors.red.shade300),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Icon(OwuiIcons.error, color: Colors.red.shade700),
              SizedBox(width: ChatBoxTokens.spacing.sm),
              Text(
                'Mermaid 渲染失败',
                style: TextStyle(
                  color: Colors.red.shade700,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          SizedBox(height: ChatBoxTokens.spacing.sm),
          Text(
            _error ?? '未知错误',
            style: TextStyle(
              color: Colors.red.shade900,
              fontSize: 12,
              fontFamily: 'monospace',
            ),
          ),
          SizedBox(height: ChatBoxTokens.spacing.sm),
          ExpansionTile(
            title: const Text('查看原始代码'),
            children: [
              Container(
                padding: EdgeInsets.all(ChatBoxTokens.spacing.sm),
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

