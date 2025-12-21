part of '../flyer_chat_demo_page.dart';

class _StreamingCodeBlockPreview extends StatefulWidget {
  final String code;
  final String language;
  final bool isDark;

  final bool isLoading;

  final bool includeOuterContainer;
  final bool showHeader;

  const _StreamingCodeBlockPreview({
    required this.code,
    required this.language,
    required this.isDark,
    this.isLoading = false,
    this.includeOuterContainer = true,
    this.showHeader = true,
  });

  @override
  State<_StreamingCodeBlockPreview> createState() => _StreamingCodeBlockPreviewState();
}

class _StreamingCodeBlockPreviewState extends State<_StreamingCodeBlockPreview> {
  static const int _collapseLineThreshold = 16;
  static const double _collapsedMaxHeight = 220;
  static const double _expandedMaxHeight = 360;

  late bool _expanded;

  int? _cachedLineCount;
  String _cachedLineLabels = '';

  ({int lineCount, int visibleLines})? _cachedCollapsedKey;
  String _cachedCollapsedLineLabels = '';

  int _countLines(String value) {
    if (value.isEmpty) return 1;
    var count = 1;
    for (var i = 0; i < value.length; i++) {
      if (value.codeUnitAt(i) == 10) count++;
    }
    return count;
  }

  String _fullLineLabels(int lineCount) {
    if (_cachedLineCount == lineCount) return _cachedLineLabels;
    _cachedLineCount = lineCount;
    _cachedLineLabels = List.generate(lineCount, (i) => '${i + 1}').join('\n');
    return _cachedLineLabels;
  }

  String _collapsedLineLabels({required int lineCount, required int visibleLines}) {
    final key = (lineCount: lineCount, visibleLines: visibleLines);
    if (_cachedCollapsedKey == key) return _cachedCollapsedLineLabels;
    _cachedCollapsedKey = key;

    final showLines = visibleLines.clamp(1, lineCount);
    final labels = <String>[...List.generate(showLines, (i) => '${i + 1}')];
    if (lineCount > showLines) labels.add('…');
    _cachedCollapsedLineLabels = labels.join('\n');
    return _cachedCollapsedLineLabels;
  }

  @override
  void initState() {
    super.initState();
    final lineCount = _countLines(widget.code);
    _expanded = lineCount <= _collapseLineThreshold;
  }

  @override
  void didUpdateWidget(covariant _StreamingCodeBlockPreview oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.code == oldWidget.code) return;

    final oldLines = _countLines(oldWidget.code);
    final newLines = _countLines(widget.code);

    final oldLong = oldLines > _collapseLineThreshold;
    final newLong = newLines > _collapseLineThreshold;

    if (!newLong) {
      _expanded = true;
      return;
    }

    if (!oldLong && newLong) {
      _expanded = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    final textStyle = TextStyle(
      fontFamily: 'monospace',
      fontFamilyFallback: const [
        'Consolas',
        'Menlo',
        'Monaco',
        'RobotoMono',
        'Courier New',
        'monospace',
      ],
      fontSize: 13,
      height: 1.55,
      letterSpacing: 0.2,
      color: widget.isDark ? const Color(0xFFE5E7EB) : const Color(0xFF111827),
    );

    final lineCount = _countLines(widget.code);
    final isLong = lineCount > _collapseLineThreshold;

    final lineHeight = (textStyle.fontSize ?? 13) * (textStyle.height ?? 1.55);
    final collapsedVisibleLines = ((_collapsedMaxHeight - 24) / lineHeight).floor().clamp(1, lineCount);
    final lineLabels = (isLong && !_expanded)
        ? _collapsedLineLabels(lineCount: lineCount, visibleLines: collapsedVisibleLines)
        : _fullLineLabels(lineCount);

    final maxHeight = isLong
        ? (_expanded ? _expandedMaxHeight : _collapsedMaxHeight)
        : _expandedMaxHeight;

    final header = Container(
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(
            color: widget.isDark ? const Color(0x1AFFFFFF) : const Color(0x14000000),
          ),
        ),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
            decoration: BoxDecoration(
              color: widget.isDark ? const Color(0x263B82F6) : const Color(0x1A1A73E8),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(
              widget.language.toUpperCase(),
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w600,
                color: widget.isDark ? const Color(0xFF93C5FD) : const Color(0xFF1A73E8),
                letterSpacing: 0.5,
              ),
            ),
          ),
          if (widget.isLoading) ...[
            const SizedBox(width: 10),
            SizedBox(
              width: 14,
              height: 14,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                valueColor: AlwaysStoppedAnimation<Color>(
                  widget.isDark ? const Color(0xFF93C5FD) : const Color(0xFF1A73E8),
                ),
              ),
            ),
            const SizedBox(width: 8),
            Text(
              'Streaming…',
              style: TextStyle(
                fontSize: 12,
                color: widget.isDark ? const Color(0xFF9CA3AF) : const Color(0xFF6B7280),
              ),
            ),
          ],
          const Spacer(),
          if (isLong)
            IconButton(
              onPressed: () {
                setState(() {
                  _expanded = !_expanded;
                });
              },
              icon: Icon(
                _expanded ? Icons.unfold_less_rounded : Icons.unfold_more_rounded,
                size: 18,
                color: widget.isDark ? Colors.grey.shade500 : Colors.grey.shade600,
              ),
              padding: EdgeInsets.zero,
              visualDensity: VisualDensity.compact,
              constraints: const BoxConstraints.tightFor(width: 32, height: 32),
            ),
          IconButton(
            onPressed: () {
              Clipboard.setData(ClipboardData(text: widget.code));
              final messenger = ScaffoldMessenger.maybeOf(context);
              messenger?.hideCurrentSnackBar();
              messenger?.showSnackBar(
                const SnackBar(
                  content: Text('已复制'),
                  duration: Duration(milliseconds: 900),
                ),
              );
            },
            icon: Icon(
              Icons.content_copy_rounded,
              size: 18,
              color: widget.isDark ? Colors.grey.shade500 : Colors.grey.shade600,
            ),
            padding: EdgeInsets.zero,
            visualDensity: VisualDensity.compact,
            constraints: const BoxConstraints.tightFor(width: 32, height: 32),
          ),
        ],
      ),
    );

    final codeScrollable = ScrollConfiguration(
      behavior: ScrollConfiguration.of(context).copyWith(scrollbars: false),
      child: ClipRect(
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeInOut,
          constraints: BoxConstraints(maxHeight: maxHeight),
          child: SingleChildScrollView(
            scrollDirection: Axis.vertical,
            physics: (isLong && !_expanded) ? const NeverScrollableScrollPhysics() : const ClampingScrollPhysics(),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(
                  width: 40,
                  child: Container(
                    padding: const EdgeInsets.fromLTRB(12, 12, 8, 12),
                    decoration: BoxDecoration(
                      color: widget.isDark ? const Color(0xFF171A20) : const Color(0xFFF1F3F5),
                      borderRadius: const BorderRadius.only(
                        bottomLeft: Radius.circular(11),
                      ),
                      border: Border(
                        right: BorderSide(
                          color: widget.isDark ? const Color(0x1AFFFFFF) : const Color(0x14000000),
                        ),
                      ),
                    ),
                    child: Text(
                      lineLabels,
                      textAlign: TextAlign.right,
                      style: textStyle.copyWith(
                        color: widget.isDark ? const Color(0xFF9CA3AF) : const Color(0xFF6B7280),
                      ),
                    ),
                  ),
                ),
                Expanded(
                  child: SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    physics: const ClampingScrollPhysics(),
                    padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
                    child: Text(
                      widget.code,
                      style: textStyle,
                      softWrap: false,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );

    if (!widget.includeOuterContainer) {
      return codeScrollable;
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
          if (widget.showHeader) header,
          codeScrollable,
        ],
      ),
    );
  }
}
