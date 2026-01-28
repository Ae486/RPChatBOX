/// Validation Context
///
/// Provides context for validators including story/branch info,
/// output text to validate, and memory reader access.
/// POS: Services / Roleplay / Consistency Gate

import '../context_compiler/rp_memory_reader.dart';
import '../context_compiler/rp_fragment.dart';

/// Context provided to validators
class RpValidationContext {
  /// Story ID
  final String storyId;

  /// Branch ID
  final String branchId;

  /// The output text to validate
  final String outputText;

  /// Memory reader for accessing entries
  final RpMemoryReader memory;

  /// Already compiled context (optional)
  final RpPackedContext? packedContext;

  /// Prompt utilization ratio (0.0 ~ 1.0)
  final double promptUtilization;

  /// Remaining token headroom
  final int headroomTokens;

  /// When the output was generated
  final DateTime generatedAt;

  /// Additional hints for validators
  final Map<String, dynamic> hints;

  const RpValidationContext({
    required this.storyId,
    required this.branchId,
    required this.outputText,
    required this.memory,
    this.packedContext,
    required this.promptUtilization,
    required this.headroomTokens,
    DateTime? generatedAt,
    this.hints = const {},
  }) : generatedAt = generatedAt ?? const _DefaultDateTime();

  /// Get a typed hint value
  T? getHint<T>(String key) {
    final value = hints[key];
    return value is T ? value : null;
  }

  /// Check if heavy validation should be triggered
  bool get shouldTriggerHeavyValidation {
    return promptUtilization >= 0.85 || headroomTokens < 800;
  }

  /// Get output text for validation (with optional sampling for long text)
  String getTextForValidation({int maxLength = 5000}) {
    final length = outputText.length;
    if (length <= maxLength) {
      return outputText;
    }

    // Sample head + tail for long text, with safe bounds
    final halfMax = maxLength ~/ 2;
    final headLength = halfMax.clamp(0, length);
    final tailLength = (maxLength - headLength).clamp(0, length - headLength);

    final head = outputText.substring(0, headLength);
    final tail = tailLength > 0
        ? outputText.substring(length - tailLength)
        : '';
    return '$head\n...[content truncated for validation]...\n$tail';
  }

  @override
  String toString() {
    return 'RpValidationContext(storyId: $storyId, branchId: $branchId, '
        'outputLength: ${outputText.length}, utilization: $promptUtilization)';
  }
}

/// Helper class for default DateTime
class _DefaultDateTime implements DateTime {
  const _DefaultDateTime();

  DateTime get _now => DateTime.now();

  @override
  int get year => _now.year;
  @override
  int get month => _now.month;
  @override
  int get day => _now.day;
  @override
  int get hour => _now.hour;
  @override
  int get minute => _now.minute;
  @override
  int get second => _now.second;
  @override
  int get millisecond => _now.millisecond;
  @override
  int get microsecond => _now.microsecond;
  @override
  int get weekday => _now.weekday;
  @override
  bool get isUtc => _now.isUtc;
  @override
  int get millisecondsSinceEpoch => _now.millisecondsSinceEpoch;
  @override
  int get microsecondsSinceEpoch => _now.microsecondsSinceEpoch;
  @override
  String get timeZoneName => _now.timeZoneName;
  @override
  Duration get timeZoneOffset => _now.timeZoneOffset;

  @override
  DateTime add(Duration duration) => _now.add(duration);
  @override
  DateTime subtract(Duration duration) => _now.subtract(duration);
  @override
  Duration difference(DateTime other) => _now.difference(other);
  @override
  int compareTo(DateTime other) => _now.compareTo(other);
  @override
  bool isBefore(DateTime other) => _now.isBefore(other);
  @override
  bool isAfter(DateTime other) => _now.isAfter(other);
  @override
  bool isAtSameMomentAs(DateTime other) => _now.isAtSameMomentAs(other);
  @override
  DateTime toLocal() => _now.toLocal();
  @override
  DateTime toUtc() => _now.toUtc();
  @override
  String toIso8601String() => _now.toIso8601String();
  @override
  String toString() => _now.toString();
}

/// Validation timing options
enum ValidationTiming {
  /// Validate after stream ends (recommended for v0)
  onStreamEnd,

  /// Validate on each chunk flush (for future v1)
  onChunkFlush,
}
