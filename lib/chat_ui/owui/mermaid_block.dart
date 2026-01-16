/// INPUT: Mermaid 代码 + 主题/缩放 + 本地文件/剪贴板能力
/// OUTPUT: OwuiMermaidBlock - Mermaid 预览/源码切换 + 全屏预览
/// POS: UI 层 / Markdown / Owui - Mermaid 区块渲染（供 OwuiMarkdown 使用）

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../widgets/mermaid_renderer.dart';
import 'owui_icons.dart';
import 'owui_tokens_ext.dart';

enum OwuiMermaidTab { preview, source }

/// OpenWebUI-inspired enhanced Mermaid block.
///
/// Ported from Demo: `lib/pages/flyer_chat_demo/mermaid_block.dart`.
class OwuiMermaidBlock extends StatefulWidget {
  final String mermaidCode;
  final bool isDark;
  final bool isStreaming;

  /// P0-4: 流式阶段启用固定高度占位，避免 WebView 抖动/跳变。
  ///
  /// MUST default to false so existing behavior is unaffected.
  final bool enableStablePlaceholder;

  /// P0-4: 固定占位高度（单位 dp），默认 360。
  static const double stablePlaceholderHeight = 360.0;

  const OwuiMermaidBlock({
    super.key,
    required this.mermaidCode,
    required this.isDark,
    required this.isStreaming,
    this.enableStablePlaceholder = false,
  });

  @override
  State<OwuiMermaidBlock> createState() => _OwuiMermaidBlockState();
}

class _OwuiMermaidBlockState extends State<OwuiMermaidBlock> {
  OwuiMermaidTab _tab = OwuiMermaidTab.preview;
  bool _isCollapsed = false;
  bool _isFullscreen = false;

  double _zoom = 1.0;
  Offset _offset = Offset.zero;
  Offset? _dragStart;
  Offset? _lastOffset;

  static const double _minZoom = 0.25;
  static const double _maxZoom = 3.0;
  static const double _zoomStep = 0.1;

  bool get _isDesktop => Platform.isWindows || Platform.isLinux || Platform.isMacOS;

  void _zoomIn() => setState(() => _zoom = (_zoom + _zoomStep).clamp(_minZoom, _maxZoom));
  void _zoomOut() => setState(() => _zoom = (_zoom - _zoomStep).clamp(_minZoom, _maxZoom));

  void _resetZoom() => setState(() {
        _zoom = 1.0;
        _offset = Offset.zero;
      });

  void _onPanStart(DragStartDetails details) {
    _dragStart = details.localPosition;
    _lastOffset = _offset;
  }

  void _onPanUpdate(DragUpdateDetails details) {
    if (_dragStart == null || _lastOffset == null) return;
    setState(() => _offset = _lastOffset! + (details.localPosition - _dragStart!));
  }

  void _onPanEnd(DragEndDetails details) {
    _dragStart = null;
    _lastOffset = null;
  }

  Future<void> _copySource() async {
    await Clipboard.setData(ClipboardData(text: widget.mermaidCode));
    if (!mounted) return;
    final messenger = ScaffoldMessenger.maybeOf(context);
    messenger?.hideCurrentSnackBar();
    messenger?.showSnackBar(
      const SnackBar(content: Text('已复制'), duration: Duration(milliseconds: 900)),
    );
  }

  void _toggleFullscreen() {
    setState(() {
      _isFullscreen = !_isFullscreen;
      if (_isFullscreen) {
        _zoom = 1.0;
        _offset = Offset.zero;
      }
    });
  }

  String _escapeMermaidCode(String code) {
    return code.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
  }

  Future<void> _openExternalPreview() async {
    try {
      final template = await rootBundle.loadString('assets/web/mermaid_template.html');
      final html = template
          .replaceAll('{{MERMAID_CODE}}', _escapeMermaidCode(widget.mermaidCode))
          .replaceAll('{{THEME}}', widget.isDark ? 'dark' : 'default');

      final dir = await getTemporaryDirectory();
      final file = File(
        '${dir.path}${Platform.pathSeparator}mermaid_${DateTime.now().millisecondsSinceEpoch}.html',
      );
      await file.writeAsString(html);
      await launchUrl(Uri.file(file.path), mode: LaunchMode.externalApplication);
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('外部预览打开失败')));
    }
  }

  Widget _buildIconBtn({
    required IconData icon,
    required String tooltip,
    required VoidCallback onPressed,
    required Color iconColor,
    required double uiScale,
    double iconSize = 16,
  }) {
    return Tooltip(
      message: tooltip,
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(6 * uiScale),
        child: Padding(
          padding: EdgeInsets.all(6 * uiScale),
          child: Icon(icon, size: iconSize * uiScale, color: iconColor),
        ),
      ),
    );
  }

  Widget _tabBtn(OwuiMermaidTab tab, {required String label, required double uiScale}) {
    final selected = _tab == tab;
    return InkWell(
      onTap: () => setState(() => _tab = tab),
      borderRadius: BorderRadius.circular(4 * uiScale),
      child: Container(
        padding: EdgeInsets.symmetric(horizontal: 10 * uiScale, vertical: 6 * uiScale),
        decoration: BoxDecoration(
          color: selected ? (widget.isDark ? const Color(0xFF14161A) : Colors.white) : Colors.transparent,
          borderRadius: BorderRadius.circular(4 * uiScale),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 12 * uiScale,
            fontWeight: FontWeight.w600,
            color: selected
                ? (widget.isDark ? Colors.white : const Color(0xFF111827))
                : (widget.isDark ? const Color(0xFF9CA3AF) : const Color(0xFF6B7280)),
          ),
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    final uiScale = context.owui.uiScale;
    final iconColor = widget.isDark ? Colors.grey.shade400 : Colors.grey.shade600;
    final bg = widget.isDark ? const Color(0xFF1A1D23) : const Color(0xFFEEF1F5);

    return Container(
      padding: EdgeInsets.symmetric(horizontal: 12 * uiScale, vertical: 8 * uiScale),
      decoration: BoxDecoration(
        color: bg,
        border: Border(
          bottom: BorderSide(
            color: widget.isDark ? const Color(0x26FFFFFF) : const Color(0x1A000000),
          ),
        ),
      ),
      child: Row(
        children: [
          Icon(OwuiIcons.accountTree, size: 16 * uiScale, color: Colors.purple.shade400),
          SizedBox(width: 6 * uiScale),
          Text(
            'Mermaid',
            style: TextStyle(
              fontSize: 13 * uiScale,
              fontWeight: FontWeight.w500,
              color: widget.isDark ? Colors.grey.shade300 : Colors.grey.shade700,
            ),
          ),
          const Spacer(),
          Container(
            padding: EdgeInsets.all(2 * uiScale),
            decoration: BoxDecoration(
              color: widget.isDark ? const Color(0xFF0D0F12) : const Color(0xFFE5E8EC),
              borderRadius: BorderRadius.circular(6 * uiScale),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                _tabBtn(OwuiMermaidTab.preview, label: 'Preview', uiScale: uiScale),
                _tabBtn(OwuiMermaidTab.source, label: 'Source', uiScale: uiScale),
              ],
            ),
          ),
          SizedBox(width: 6 * uiScale),
          if (_isDesktop)
            _buildIconBtn(
              icon: OwuiIcons.openInNew,
              tooltip: '外部预览',
              onPressed: _openExternalPreview,
              iconColor: iconColor,
              uiScale: uiScale,
            ),
          _buildIconBtn(
            icon: OwuiIcons.copy,
            tooltip: '复制',
            onPressed: _copySource,
            iconColor: iconColor,
            uiScale: uiScale,
          ),
          _buildIconBtn(
            icon: _isCollapsed ? OwuiIcons.unfoldMore : OwuiIcons.unfoldLess,
            tooltip: _isCollapsed ? '展开' : '收起',
            onPressed: () => setState(() => _isCollapsed = !_isCollapsed),
            iconColor: iconColor,
            uiScale: uiScale,
          ),
          _buildIconBtn(
            icon: OwuiIcons.fullscreen,
            tooltip: '全屏',
            onPressed: _toggleFullscreen,
            iconColor: iconColor,
            uiScale: uiScale,
          ),
        ],
      ),
    );
  }

  Widget _buildContent(BuildContext context) {
    final uiScale = context.owui.uiScale;
    if (_isCollapsed) return const SizedBox.shrink();

    if (_tab == OwuiMermaidTab.source) {
      return Container(
        padding: EdgeInsets.all(12 * uiScale),
        child: SelectableText(
          widget.mermaidCode,
          style: TextStyle(
            fontFamily: 'monospace',
            fontFamilyFallback: const ['Consolas', 'Menlo', 'Monaco', 'monospace'],
            fontSize: 13 * uiScale,
            height: 1.5,
            color: widget.isDark ? const Color(0xFFE5E7EB) : const Color(0xFF111827),
          ),
        ),
      );
    }

    if (widget.isStreaming) {
      // P0-4: 启用固定高度占位时，使用 AnimatedContainer 平滑过渡
      final placeholderContent = Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(
            width: 14 * uiScale,
            height: 14 * uiScale,
            child: CircularProgressIndicator(
              strokeWidth: 2 * uiScale,
              valueColor: AlwaysStoppedAnimation(
                widget.isDark ? const Color(0xFF9CA3AF) : const Color(0xFF6B7280),
              ),
            ),
          ),
          SizedBox(width: 10 * uiScale),
          Text(
            'Rendering…',
            style: TextStyle(
              fontSize: 13 * uiScale,
              color: widget.isDark ? const Color(0xFF9CA3AF) : const Color(0xFF6B7280),
            ),
          ),
        ],
      );

      if (widget.enableStablePlaceholder) {
        return AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
          height: OwuiMermaidBlock.stablePlaceholderHeight * uiScale,
          padding: EdgeInsets.all(16 * uiScale),
          alignment: Alignment.center,
          child: placeholderContent,
        );
      }

      return Container(
        padding: EdgeInsets.all(16 * uiScale),
        child: placeholderContent,
      );
    }

    return Padding(
      padding: EdgeInsets.all(12 * uiScale),
      child: MermaidRenderer(
        mermaidCode: widget.mermaidCode,
        isDark: widget.isDark,
        includeOuterContainer: false,
        margin: EdgeInsets.zero,
      ),
    );
  }

  Widget _buildFullscreenOverlay(BuildContext context) {
    final uiScale = context.owui.uiScale;
    return Material(
      color: widget.isDark ? const Color(0xFF0D0D0D) : Colors.white,
      child: SafeArea(
        child: Column(
          children: [
            Container(
              padding: EdgeInsets.symmetric(horizontal: 16 * uiScale, vertical: 12 * uiScale),
              decoration: BoxDecoration(
                border: Border(
                  bottom: BorderSide(
                    color: widget.isDark ? const Color(0x26FFFFFF) : const Color(0x1A000000),
                  ),
                ),
              ),
              child: Row(
                children: [
                  Icon(OwuiIcons.accountTree, size: 20 * uiScale, color: Colors.purple.shade400),
                  SizedBox(width: 8 * uiScale),
                  Text(
                    'Mermaid 全屏预览',
                    style: TextStyle(
                      fontSize: 16 * uiScale,
                      fontWeight: FontWeight.w600,
                      color: widget.isDark ? Colors.white : Colors.grey.shade800,
                    ),
                  ),
                  const Spacer(),
                  _buildIconBtn(
                    icon: OwuiIcons.zoomIn,
                    tooltip: '放大',
                    onPressed: _zoomIn,
                    iconColor: widget.isDark ? Colors.grey.shade300 : Colors.grey.shade700,
                    uiScale: uiScale,
                    iconSize: 20,
                  ),
                  _buildIconBtn(
                    icon: OwuiIcons.zoomOut,
                    tooltip: '缩小',
                    onPressed: _zoomOut,
                    iconColor: widget.isDark ? Colors.grey.shade300 : Colors.grey.shade700,
                    uiScale: uiScale,
                    iconSize: 20,
                  ),
                  Padding(
                    padding: EdgeInsets.symmetric(horizontal: 8 * uiScale),
                    child: GestureDetector(
                      onTap: _resetZoom,
                      child: Text(
                        '${(_zoom * 100).round()}%',
                        style: TextStyle(
                          fontSize: 13 * uiScale,
                          fontWeight: FontWeight.w500,
                          color: widget.isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                        ),
                      ),
                    ),
                  ),
                  SizedBox(width: 16 * uiScale),
                  _buildIconBtn(
                    icon: OwuiIcons.close,
                    tooltip: '关闭',
                    onPressed: _toggleFullscreen,
                    iconColor: widget.isDark ? Colors.grey.shade300 : Colors.grey.shade700,
                    uiScale: uiScale,
                    iconSize: 22,
                  ),
                ],
              ),
            ),
            Expanded(
              child: GestureDetector(
                onPanStart: _onPanStart,
                onPanUpdate: _onPanUpdate,
                onPanEnd: _onPanEnd,
                child: MouseRegion(
                  cursor: SystemMouseCursors.grab,
                  child: Center(
                    child: Transform.translate(
                      offset: _offset,
                      child: Transform.scale(
                        scale: _zoom,
                        child: MermaidRenderer(
                          mermaidCode: widget.mermaidCode,
                          isDark: widget.isDark,
                          includeOuterContainer: false,
                          margin: EdgeInsets.zero,
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final uiScale = context.owui.uiScale;
    if (_isFullscreen) return _buildFullscreenOverlay(context);

    return Container(
      margin: EdgeInsets.symmetric(vertical: 8 * uiScale),
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: widget.isDark ? const Color(0xFF14161A) : const Color(0xFFF6F8FA),
        borderRadius: BorderRadius.circular(12 * uiScale),
        border: Border.all(
          color: widget.isDark ? const Color(0x26FFFFFF) : const Color(0x1A000000),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          _buildHeader(context),
          AnimatedSize(
            duration: const Duration(milliseconds: 200),
            curve: Curves.easeOut,
            child: _buildContent(context),
          ),
        ],
      ),
    );
  }
}
