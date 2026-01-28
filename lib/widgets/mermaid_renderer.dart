/// INPUT: Mermaid 代码 + 平台能力（WebView/外部预览）+ 主题/高度
/// OUTPUT: MermaidRenderer - Mermaid 图表渲染（优先 SVG 缓存，降级 WebView）
/// POS: UI 层 / Widgets - Mermaid 渲染底层（供 OwuiMermaidBlock/Demo 使用）

import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_windows/webview_windows.dart' as windows_webview;

import '../chat_ui/owui/owui_icons.dart';
import '../design_system/design_tokens.dart';
import '../services/mermaid_svg_cache.dart';
import 'mermaid_svg_widget.dart';

/// 全局高度缓存，避免重建时高度跳变
/// 使用 LRU 策略，限制最大条目数
final Map<int, double> _mermaidHeightCache = {};
const int _maxCacheSize = 50;

/// 生成 Mermaid 代码的缓存 key
int _cacheKey(String code) => code.hashCode;

/// 添加缓存条目，超出限制时移除最早的条目
void _addToCache(int key, double height) {
  if (_mermaidHeightCache.length >= _maxCacheSize) {
    _mermaidHeightCache.remove(_mermaidHeightCache.keys.first);
  }
  _mermaidHeightCache[key] = height;
}

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
  late double _webViewHeight;
  bool _isLoading = true;
  String? _error;
  Uri? _previewUri;
  bool _isWindowsWebViewReady = false;

  /// 缓存的 SVG 数据（优先使用，避免 WebView 重建）
  MermaidSvgData? _cachedSvgData;

  int get _cacheKeyValue => _cacheKey(widget.mermaidCode);

  @override
  void initState() {
    super.initState();
    // 暂时禁用 SVG 缓存渲染（flutter_svg 兼容性问题待调试）
    // TODO: 调试 flutter_svg 渲染 Mermaid SVG 的兼容性
    // _cachedSvgData = MermaidSvgCache.instance.get(
    //   widget.mermaidCode,
    //   isDark: widget.isDark,
    // );

    // 使用高度缓存或默认值，然后初始化 WebView
    _webViewHeight = _mermaidHeightCache[_cacheKeyValue] ?? 360;
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
        ..addJavaScriptChannel(
          'FlutterChannel',
          onMessageReceived: (message) {
            _handleHeightMessage(message.message);
          },
        )
        ..setNavigationDelegate(
          NavigationDelegate(
            onPageFinished: (String url) {
              setState(() {
                _isLoading = false;
              });
              // 降级方案：始终延迟探测高度，确保 WebView 内容可见
              // 即使有缓存高度也要探测，以防缓存失效
              Future.delayed(const Duration(milliseconds: 800), () {
                if (mounted) {
                  _getWebViewHeight();
                }
              });
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
        // Windows 平台：延迟轮询获取高度（暂不支持 JS channel）
        Future.delayed(const Duration(milliseconds: 800), _getWindowsWebViewHeight);
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

  /// 处理 JS channel 回传的消息（高度 + SVG）
  void _handleHeightMessage(String message) {
    try {
      final data = jsonDecode(message) as Map<String, dynamic>;
      final type = data['type'] as String?;

      if (type == 'rendered') {
        final height = (data['height'] as num?)?.toDouble();
        // 暂时禁用 SVG 缓存（flutter_svg 兼容性问题待调试）
        // final width = (data['width'] as num?)?.toDouble();
        // final svgString = data['svg'] as String?;

        if (height != null && height > 0 && mounted) {
          setState(() {
            _webViewHeight = height;
            _addToCache(_cacheKeyValue, height);
          });

          // TODO: 调试 flutter_svg 渲染 Mermaid SVG 的兼容性后启用
          // if (svgString != null && svgString.isNotEmpty) {
          //   final svgData = MermaidSvgData(
          //     svgString: svgString,
          //     width: width ?? 400,
          //     height: height,
          //     createdAt: DateTime.now(),
          //   );
          //   MermaidSvgCache.instance.put(
          //     widget.mermaidCode,
          //     svgData,
          //     isDark: widget.isDark,
          //   );
          //   setState(() {
          //     _cachedSvgData = svgData;
          //   });
          // }
        }
      } else {
        // 兼容旧格式（仅高度）
        final height = (data['height'] as num?)?.toDouble();
        if (height != null && height > 0 && mounted) {
          setState(() {
            _webViewHeight = height;
            _addToCache(_cacheKeyValue, height);
          });
        }
      }
    } catch (e) {
      debugPrint('Failed to parse message: $e');
    }
  }

  /// 获取 WebView 实际高度（降级方案）
  Future<void> _getWebViewHeight() async {
    if (_controller == null) return;
    try {
      final heightStr = await _controller!.runJavaScriptReturningResult(
        'document.getElementById("diagram").scrollHeight'
      );

      final height = double.tryParse(heightStr.toString()) ?? 360;

      if (mounted && height > 0) {
        final finalHeight = height + 32;
        setState(() {
          _webViewHeight = finalHeight;
          _addToCache(_cacheKeyValue, finalHeight);
        });
      }
    } catch (e) {
      debugPrint('Failed to get WebView height: $e');
    }
  }

  /// Windows 平台获取 WebView 高度
  Future<void> _getWindowsWebViewHeight() async {
    if (_windowsController == null) return;
    try {
      final result = await _windowsController!.executeScript(
        'document.getElementById("diagram").scrollHeight'
      );

      final height = double.tryParse(result.toString()) ?? 360;

      if (mounted && height > 0) {
        final finalHeight = height + 32;
        setState(() {
          _webViewHeight = finalHeight;
          _addToCache(_cacheKeyValue, finalHeight);
        });
      }
    } catch (e) {
      debugPrint('Failed to get Windows WebView height: $e');
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

    // 暂时禁用 SVG 缓存渲染（flutter_svg 兼容性问题待调试）
    // if (_cachedSvgData != null) {
    //   return MermaidSvgWidget(
    //     svgData: _cachedSvgData!,
    //     isDark: widget.isDark,
    //     includeOuterContainer: widget.includeOuterContainer,
    //     margin: widget.margin,
    //   );
    // }

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
            // 禁止 WebView 捕获触摸事件，让父级 ListView 正常滚动
            child: IgnorePointer(
              child: WebViewWidget(controller: _controller!),
            ),
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
        // 禁止 WebView 捕获触摸事件，让父级 ListView 正常滚动
        child: IgnorePointer(
          child: windows_webview.Webview(_windowsController!),
        ),
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

