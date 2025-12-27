import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../widgets/mermaid_renderer.dart';

enum OwuiMermaidTab { preview, source }

/// OpenWebUI-inspired enhanced Mermaid block.
///
/// Ported from Demo: `lib/pages/flyer_chat_demo/mermaid_block.dart`.
class OwuiMermaidBlock extends StatefulWidget {
  final String mermaidCode;
  final bool isDark;
  final bool isStreaming;

  const OwuiMermaidBlock({
    super.key,
    required this.mermaidCode,
    required this.isDark,
    required this.isStreaming,
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
    double iconSize = 16,
  }) {
    return Tooltip(
      message: tooltip,
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(6),
        child: Padding(
          padding: const EdgeInsets.all(6),
          child: Icon(icon, size: iconSize, color: iconColor),
        ),
      ),
    );
  }

  Widget _tabBtn(OwuiMermaidTab tab, {required String label}) {
    final selected = _tab == tab;
    return InkWell(
      onTap: () => setState(() => _tab = tab),
      borderRadius: BorderRadius.circular(4),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: selected ? (widget.isDark ? const Color(0xFF14161A) : Colors.white) : Colors.transparent,
          borderRadius: BorderRadius.circular(4),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w600,
            color: selected
                ? (widget.isDark ? Colors.white : const Color(0xFF111827))
                : (widget.isDark ? const Color(0xFF9CA3AF) : const Color(0xFF6B7280)),
          ),
        ),
      ),
    );
  }

  Widget _buildHeader() {
    final iconColor = widget.isDark ? Colors.grey.shade400 : Colors.grey.shade600;
    final bg = widget.isDark ? const Color(0xFF1A1D23) : const Color(0xFFEEF1F5);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
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
          Icon(Icons.account_tree_rounded, size: 16, color: Colors.purple.shade400),
          const SizedBox(width: 6),
          Text(
            'Mermaid',
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w500,
              color: widget.isDark ? Colors.grey.shade300 : Colors.grey.shade700,
            ),
          ),
          const Spacer(),
          Container(
            padding: const EdgeInsets.all(2),
            decoration: BoxDecoration(
              color: widget.isDark ? const Color(0xFF0D0F12) : const Color(0xFFE5E8EC),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                _tabBtn(OwuiMermaidTab.preview, label: 'Preview'),
                _tabBtn(OwuiMermaidTab.source, label: 'Source'),
              ],
            ),
          ),
          const SizedBox(width: 6),
          if (_isDesktop)
            _buildIconBtn(
              icon: Icons.open_in_new_rounded,
              tooltip: '外部预览',
              onPressed: _openExternalPreview,
              iconColor: iconColor,
            ),
          _buildIconBtn(
            icon: Icons.content_copy_rounded,
            tooltip: '复制',
            onPressed: _copySource,
            iconColor: iconColor,
          ),
          _buildIconBtn(
            icon: _isCollapsed ? Icons.unfold_more_rounded : Icons.unfold_less_rounded,
            tooltip: _isCollapsed ? '展开' : '收起',
            onPressed: () => setState(() => _isCollapsed = !_isCollapsed),
            iconColor: iconColor,
          ),
          _buildIconBtn(
            icon: Icons.fullscreen_rounded,
            tooltip: '全屏',
            onPressed: _toggleFullscreen,
            iconColor: iconColor,
          ),
        ],
      ),
    );
  }

  Widget _buildContent() {
    if (_isCollapsed) return const SizedBox.shrink();

    if (_tab == OwuiMermaidTab.source) {
      return Container(
        padding: const EdgeInsets.all(12),
        child: SelectableText(
          widget.mermaidCode,
          style: TextStyle(
            fontFamily: 'monospace',
            fontFamilyFallback: const ['Consolas', 'Menlo', 'Monaco', 'monospace'],
            fontSize: 13,
            height: 1.5,
            color: widget.isDark ? const Color(0xFFE5E7EB) : const Color(0xFF111827),
          ),
        ),
      );
    }

    if (widget.isStreaming) {
      return Container(
        padding: const EdgeInsets.all(16),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: 14,
              height: 14,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                valueColor: AlwaysStoppedAnimation(
                  widget.isDark ? const Color(0xFF9CA3AF) : const Color(0xFF6B7280),
                ),
              ),
            ),
            const SizedBox(width: 10),
            Text(
              'Rendering…',
              style: TextStyle(
                fontSize: 13,
                color: widget.isDark ? const Color(0xFF9CA3AF) : const Color(0xFF6B7280),
              ),
            ),
          ],
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.all(12),
      child: MermaidRenderer(
        mermaidCode: widget.mermaidCode,
        isDark: widget.isDark,
        includeOuterContainer: false,
        margin: EdgeInsets.zero,
      ),
    );
  }

  Widget _buildFullscreenOverlay() {
    return Material(
      color: widget.isDark ? const Color(0xFF0D0D0D) : Colors.white,
      child: SafeArea(
        child: Column(
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: BoxDecoration(
                border: Border(
                  bottom: BorderSide(
                    color: widget.isDark ? const Color(0x26FFFFFF) : const Color(0x1A000000),
                  ),
                ),
              ),
              child: Row(
                children: [
                  Icon(Icons.account_tree_rounded, size: 20, color: Colors.purple.shade400),
                  const SizedBox(width: 8),
                  Text(
                    'Mermaid 全屏预览',
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                      color: widget.isDark ? Colors.white : Colors.grey.shade800,
                    ),
                  ),
                  const Spacer(),
                  _buildIconBtn(
                    icon: Icons.zoom_in,
                    tooltip: '放大',
                    onPressed: _zoomIn,
                    iconColor: widget.isDark ? Colors.grey.shade300 : Colors.grey.shade700,
                    iconSize: 20,
                  ),
                  _buildIconBtn(
                    icon: Icons.zoom_out,
                    tooltip: '缩小',
                    onPressed: _zoomOut,
                    iconColor: widget.isDark ? Colors.grey.shade300 : Colors.grey.shade700,
                    iconSize: 20,
                  ),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 8),
                    child: GestureDetector(
                      onTap: _resetZoom,
                      child: Text(
                        '${(_zoom * 100).round()}%',
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w500,
                          color: widget.isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 16),
                  _buildIconBtn(
                    icon: Icons.close,
                    tooltip: '关闭',
                    onPressed: _toggleFullscreen,
                    iconColor: widget.isDark ? Colors.grey.shade300 : Colors.grey.shade700,
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
    if (_isFullscreen) return _buildFullscreenOverlay();

    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: widget.isDark ? const Color(0xFF14161A) : const Color(0xFFF6F8FA),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: widget.isDark ? const Color(0x26FFFFFF) : const Color(0x1A000000),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          _buildHeader(),
          AnimatedSize(
            duration: const Duration(milliseconds: 200),
            curve: Curves.easeOut,
            child: _buildContent(),
          ),
        ],
      ),
    );
  }
}

