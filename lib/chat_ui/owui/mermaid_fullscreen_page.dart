/// INPUT: Mermaid 代码 + 主题
/// OUTPUT: MermaidFullscreenPage - 全屏预览（独立路由，解决 z-index 问题）
/// POS: UI 层 / Pages - Mermaid 全屏预览

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../widgets/mermaid_renderer.dart';
import 'owui_icons.dart';
import 'owui_tokens_ext.dart';

/// Mermaid 全屏预览页面
///
/// 使用 Navigator.push 独立路由，解决 z-index 层级问题。
/// 内部创建新的 MermaidRenderer 实例，避免复用内联视图的尺寸限制。
class MermaidFullscreenPage extends StatefulWidget {
  final String mermaidCode;
  final bool isDark;

  const MermaidFullscreenPage({
    super.key,
    required this.mermaidCode,
    required this.isDark,
  });

  @override
  State<MermaidFullscreenPage> createState() => _MermaidFullscreenPageState();
}

class _MermaidFullscreenPageState extends State<MermaidFullscreenPage> {
  final TransformationController _transformController =
      TransformationController();
  double _currentScale = 1.0;

  @override
  void dispose() {
    _transformController.dispose();
    super.dispose();
  }

  void _zoomIn() {
    _setScaleKeepingTranslation(_currentScale * 1.25);
  }

  void _zoomOut() {
    _setScaleKeepingTranslation(_currentScale / 1.25);
  }

  void _resetZoom() {
    setState(() {
      _currentScale = 1.0;
      _transformController.value = Matrix4.identity();
    });
  }

  /// 设置缩放但保留当前平移位置
  void _setScaleKeepingTranslation(double scale) {
    final clamped = scale.clamp(0.5, 4.0);
    final currentMatrix = _transformController.value;
    final translation = currentMatrix.getTranslation();
    setState(() {
      _currentScale = clamped;
      _transformController.value = Matrix4.identity()
        ..translate(translation.x, translation.y)
        ..scale(clamped, clamped, 1.0);
    });
  }

  Future<void> _copySource() async {
    await Clipboard.setData(ClipboardData(text: widget.mermaidCode));
    if (!mounted) return;
    final messenger = ScaffoldMessenger.maybeOf(context);
    messenger?.hideCurrentSnackBar();
    messenger?.showSnackBar(
      const SnackBar(
          content: Text('已复制'), duration: Duration(milliseconds: 900)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final uiScale = context.owui.uiScale;
    final bgColor = widget.isDark ? const Color(0xFF0D0D0D) : Colors.white;
    final iconColor =
        widget.isDark ? Colors.grey.shade300 : Colors.grey.shade700;

    return Scaffold(
      backgroundColor: bgColor,
      body: CallbackShortcuts(
        bindings: {
          const SingleActivator(LogicalKeyboardKey.escape): () =>
              Navigator.pop(context),
          // Ctrl + (Windows/Linux)
          const SingleActivator(LogicalKeyboardKey.equal, control: true):
              _zoomIn,
          const SingleActivator(LogicalKeyboardKey.minus, control: true):
              _zoomOut,
          const SingleActivator(LogicalKeyboardKey.digit0, control: true):
              _resetZoom,
          // Cmd + (macOS)
          const SingleActivator(LogicalKeyboardKey.equal, meta: true):
              _zoomIn,
          const SingleActivator(LogicalKeyboardKey.minus, meta: true):
              _zoomOut,
          const SingleActivator(LogicalKeyboardKey.digit0, meta: true):
              _resetZoom,
        },
        child: Focus(
          autofocus: true,
          child: Stack(
            children: [
              // 内容层：InteractiveViewer + MermaidRenderer
              InteractiveViewer(
                transformationController: _transformController,
                minScale: 0.5,
                maxScale: 4.0,
                boundaryMargin: const EdgeInsets.all(200),
                onInteractionEnd: (details) {
                  setState(() {
                    _currentScale =
                        _transformController.value.getMaxScaleOnAxis();
                  });
                },
                child: Center(
                  child: MermaidRenderer(
                    mermaidCode: widget.mermaidCode,
                    isDark: widget.isDark,
                    includeOuterContainer: false,
                  ),
                ),
              ),

              // 工具栏层
              Positioned(
                top: 0,
                left: 0,
                right: 0,
                child: SafeArea(
                  child: _buildToolbar(context, uiScale, iconColor),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildToolbar(
      BuildContext context, double uiScale, Color iconColor) {
    final bgColor = widget.isDark
        ? const Color(0xFF0D0D0D).withValues(alpha: 0.9)
        : Colors.white.withValues(alpha: 0.9);

    return Container(
      padding:
          EdgeInsets.symmetric(horizontal: 16 * uiScale, vertical: 12 * uiScale),
      decoration: BoxDecoration(
        color: bgColor,
        border: Border(
          bottom: BorderSide(
            color:
                widget.isDark ? const Color(0x26FFFFFF) : const Color(0x1A000000),
          ),
        ),
      ),
      child: Row(
        children: [
          Icon(OwuiIcons.accountTree,
              size: 20 * uiScale, color: Colors.purple.shade400),
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
            icon: OwuiIcons.zoomOut,
            tooltip: '缩小 (Ctrl -)',
            onPressed: _zoomOut,
            iconColor: iconColor,
            uiScale: uiScale,
          ),
          Padding(
            padding: EdgeInsets.symmetric(horizontal: 8 * uiScale),
            child: GestureDetector(
              onTap: _resetZoom,
              child: Container(
                padding: EdgeInsets.symmetric(
                    horizontal: 8 * uiScale, vertical: 4 * uiScale),
                decoration: BoxDecoration(
                  color: widget.isDark
                      ? const Color(0xFF1A1D23)
                      : const Color(0xFFF3F4F6),
                  borderRadius: BorderRadius.circular(4 * uiScale),
                ),
                child: Text(
                  '${(_currentScale * 100).round()}%',
                  style: TextStyle(
                    fontSize: 13 * uiScale,
                    fontWeight: FontWeight.w500,
                    color: widget.isDark
                        ? Colors.grey.shade400
                        : Colors.grey.shade600,
                  ),
                ),
              ),
            ),
          ),
          _buildIconBtn(
            icon: OwuiIcons.zoomIn,
            tooltip: '放大 (Ctrl +)',
            onPressed: _zoomIn,
            iconColor: iconColor,
            uiScale: uiScale,
          ),
          SizedBox(width: 12 * uiScale),
          _buildIconBtn(
            icon: OwuiIcons.copy,
            tooltip: '复制源码',
            onPressed: _copySource,
            iconColor: iconColor,
            uiScale: uiScale,
          ),
          SizedBox(width: 12 * uiScale),
          _buildIconBtn(
            icon: OwuiIcons.close,
            tooltip: '关闭 (ESC)',
            onPressed: () => Navigator.pop(context),
            iconColor: iconColor,
            uiScale: uiScale,
            iconSize: 22,
          ),
        ],
      ),
    );
  }

  Widget _buildIconBtn({
    required IconData icon,
    required String tooltip,
    required VoidCallback onPressed,
    required Color iconColor,
    required double uiScale,
    double iconSize = 20,
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
}
