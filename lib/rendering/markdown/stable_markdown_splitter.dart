typedef StableMarkdownSplitResult = ({String stable, String tail});

class StableMarkdownSplitter {
  static StableMarkdownSplitResult split(String source) {
    if (source.isEmpty) return (stable: '', tail: '');

    var inFence = false;
    String? fenceMarker;
    var inMathBlock = false;
    var safeEnd = 0;

    var cursor = 0;
    while (cursor < source.length) {
      final nl = source.indexOf('\n', cursor);
      final end = nl == -1 ? source.length : nl + 1;
      final line = source.substring(cursor, end);
      final trimmedRight = line.trimRight();
      final trimmed = trimmedRight.trimLeft();

      final isFenceLine = trimmed.startsWith('```') || trimmed.startsWith('~~~');
      if (isFenceLine) {
        final marker = trimmed.startsWith('```') ? '```' : '~~~';
        if (!inFence) {
          inFence = true;
          fenceMarker = marker;
        } else if (fenceMarker == marker) {
          inFence = false;
          fenceMarker = null;
        }
      }

      if (!inFence && trimmed == r'$$') {
        inMathBlock = !inMathBlock;
      }

      if (!inFence && !inMathBlock) {
        safeEnd = end;
      }

      cursor = end;
    }

    return (
      stable: source.substring(0, safeEnd),
      tail: source.substring(safeEnd),
    );
  }
}
