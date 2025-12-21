part of '../flyer_chat_demo_page.dart';

enum _MermaidTab { preview, source }

/// 增强版 Mermaid 图表组件
/// 
/// 参考 markstream-vue: src/components/MermaidBlockNode/MermaidBlockNode.vue
/// 功能：放大/缩小、复制、Preview/Source、全屏、拖动
class _EnhancedMermaidBlock extends StatefulWidget {
  final String mermaidCode;
  final bool isDark;
  final bool isStreaming;

  const _EnhancedMermaidBlock({
    required this.mermaidCode,
    required this.isDark,
    required this.isStreaming,
  });

  @override
  State<_EnhancedMermaidBlock> createState() => _EnhancedMermaidBlockState();
}

class _EnhancedMermaidBlockState extends State<_EnhancedMermaidBlock> {
  _MermaidTab _tab = _MermaidTab.preview;
  bool _isCollapsed = false;
  bool _isFullscreen = false;
  
  // 缩放和拖动状态
  double _zoom = 1.0;
  Offset _offset = Offset.zero;
  Offset? _dragStart;
  Offset? _lastOffset;
  
  static const double _minZoom = 0.25;
  static const double _maxZoom = 3.0;
  static const double _zoomStep = 0.1;

  bool get _isDesktop => Platform.isWindows || Platform.isLinux || Platform.isMacOS;

  void _zoomIn() {
    setState(() {
      _zoom = (_zoom + _zoomStep).clamp(_minZoom, _maxZoom);
    });
  }

  void _zoomOut() {
    setState(() {
      _zoom = (_zoom - _zoomStep).clamp(_minZoom, _maxZoom);
    });
  }

  void _resetZoom() {
    setState(() {
      _zoom = 1.0;
      _offset = Offset.zero;
    });
  }

  void _onPanStart(DragStartDetails details) {
    _dragStart = details.localPosition;
    _lastOffset = _offset;
  }

  void _onPanUpdate(DragUpdateDetails details) {
    if (_dragStart == null || _lastOffset == null) return;
    setState(() {
      _offset = _lastOffset! + (details.localPosition - _dragStart!);
    });
  }

  void _onPanEnd(DragEndDetails details) {
    _dragStart = null;
    _lastOffset = null;
  }

  Future<void> _copySource() async {
    await Clipboard.setData(ClipboardData(text: widget.mermaidCode));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('已复制'), duration: Duration(milliseconds: 800)),
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
    return code
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;');
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
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('外部预览打开失败')),
      );
    }
  }

  Widget _buildHeader() {
    final iconColor = widget.isDark ? Colors.grey.shade400 : Colors.grey.shade600;
    final iconSize = 16.0;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: widget.isDark ? const Color(0xFF1A1D23) : const Color(0xFFEEF1F5),
        border: Border(
          bottom: BorderSide(
            color: widget.isDark ? const Color(0x26FFFFFF) : const Color(0x1A000000),
          ),
        ),
      ),
      child: Row(
        children: [
          // Mermaid 图标和标签
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
          // Preview/Source 切换
          Container(
            padding: const EdgeInsets.all(2),
            decoration: BoxDecoration(
              color: widget.isDark ? const Color(0xFF0D0F12) : const Color(0xFFE5E8EC),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                _buildTabBtn('Preview', _tab == _MermaidTab.preview, () {
                  setState(() => _tab = _MermaidTab.preview);
                }),
                _buildTabBtn('Source', _tab == _MermaidTab.source, () {
                  setState(() => _tab = _MermaidTab.source);
                }),
              ],
            ),
          ),
          const SizedBox(width: 8),
          // 收起/展开
          _buildIconBtn(
            icon: _isCollapsed ? Icons.chevron_right : Icons.expand_more,
            tooltip: _isCollapsed ? '展开' : '收起',
            onPressed: () => setState(() => _isCollapsed = !_isCollapsed),
            iconColor: iconColor,
            iconSize: iconSize,
          ),
          // 复制
          _buildIconBtn(
            icon: Icons.content_copy_rounded,
            tooltip: '复制',
            onPressed: _copySource,
            iconColor: iconColor,
            iconSize: iconSize,
          ),
          // 全屏
          _buildIconBtn(
            icon: _isFullscreen ? Icons.fullscreen_exit : Icons.fullscreen,
            tooltip: _isFullscreen ? '退出全屏' : '全屏',
            onPressed: _toggleFullscreen,
            iconColor: iconColor,
            iconSize: iconSize,
          ),
        ],
      ),
    );
  }

  Widget _buildTabBtn(String label, bool selected, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: selected
              ? (widget.isDark ? const Color(0xFF2D3139) : Colors.white)
              : Colors.transparent,
          borderRadius: BorderRadius.circular(4),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 12,
            fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
            color: selected
                ? (widget.isDark ? Colors.white : Colors.grey.shade800)
                : (widget.isDark ? Colors.grey.shade500 : Colors.grey.shade600),
          ),
        ),
      ),
    );
  }

  Widget _buildIconBtn({
    required IconData icon,
    required String tooltip,
    required VoidCallback onPressed,
    required Color iconColor,
    required double iconSize,
  }) {
    return Tooltip(
      message: tooltip,
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(4),
        child: Padding(
          padding: const EdgeInsets.all(6),
          child: Icon(icon, size: iconSize, color: iconColor),
        ),
      ),
    );
  }

  Widget _buildZoomControls() {
    final btnStyle = BoxDecoration(
      color: widget.isDark ? const Color(0xFF2D3139) : Colors.white,
      borderRadius: BorderRadius.circular(6),
      boxShadow: [
        BoxShadow(
          color: Colors.black.withValues(alpha: 0.1),
          blurRadius: 4,
          offset: const Offset(0, 2),
        ),
      ],
    );

    return Positioned(
      top: 8,
      right: 8,
      child: Container(
        decoration: btnStyle,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            _buildIconBtn(
              icon: Icons.zoom_in,
              tooltip: '放大',
              onPressed: _zoomIn,
              iconColor: widget.isDark ? Colors.grey.shade300 : Colors.grey.shade700,
              iconSize: 18,
            ),
            _buildIconBtn(
              icon: Icons.zoom_out,
              tooltip: '缩小',
              onPressed: _zoomOut,
              iconColor: widget.isDark ? Colors.grey.shade300 : Colors.grey.shade700,
              iconSize: 18,
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8),
              child: GestureDetector(
                onTap: _resetZoom,
                child: Text(
                  '${(_zoom * 100).round()}%',
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w500,
                    color: widget.isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildPreviewContent() {
    if (widget.isStreaming) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: 24,
              height: 24,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: widget.isDark ? Colors.purple.shade300 : Colors.purple.shade600,
              ),
            ),
            const SizedBox(height: 12),
            Text(
              '等待 Mermaid 代码闭合...',
              style: TextStyle(
                fontSize: 13,
                color: widget.isDark ? Colors.grey.shade400 : Colors.grey.shade600,
              ),
            ),
          ],
        ),
      );
    }

    // 可拖动和缩放的预览区域
    return GestureDetector(
      onPanStart: _onPanStart,
      onPanUpdate: _onPanUpdate,
      onPanEnd: _onPanEnd,
      child: MouseRegion(
        cursor: SystemMouseCursors.grab,
        child: ClipRect(
          child: Stack(
            children: [
              Center(
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
              _buildZoomControls(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSourceContent() {
    return _StreamingCodeBlockPreview(
      code: widget.mermaidCode,
      language: 'mermaid',
      isDark: widget.isDark,
      includeOuterContainer: false,
      showHeader: false,
    );
  }

  Widget _buildContent() {
    if (_isCollapsed) {
      return const SizedBox.shrink();
    }

    final content = _tab == _MermaidTab.preview ? _buildPreviewContent() : _buildSourceContent();

    return AnimatedContainer(
      duration: const Duration(milliseconds: 200),
      height: _tab == _MermaidTab.preview ? 360 : null,
      constraints: _tab == _MermaidTab.source 
          ? const BoxConstraints(maxHeight: 400)
          : null,
      child: content,
    );
  }

  Widget _buildFullscreenOverlay() {
    return Material(
      color: widget.isDark ? const Color(0xFF0D0F12) : Colors.white,
      child: SafeArea(
        child: Column(
          children: [
            // 全屏顶部栏
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
                  // 缩放控制
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
            // 全屏内容区域
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
    if (_isFullscreen) {
      return _buildFullscreenOverlay();
    }

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
