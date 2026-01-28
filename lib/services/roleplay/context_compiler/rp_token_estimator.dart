/// Token Estimator
///
/// Estimates token count for text content.
/// POS: Services / Roleplay / Context Compiler

/// Token estimation utility
class RpTokenEstimator {
  /// Average characters per token (conservative estimate for CJK + English mixed)
  static const double _defaultCharsPerToken = 3.5;

  final double _charsPerToken;

  const RpTokenEstimator({double charsPerToken = _defaultCharsPerToken})
      : _charsPerToken = charsPerToken;

  /// Estimate token count for given text
  int estimate(String text) {
    if (text.isEmpty) return 0;
    return (text.length / _charsPerToken).ceil();
  }

  /// Estimate token count for multiple texts
  int estimateAll(Iterable<String> texts) {
    return texts.fold(0, (sum, text) => sum + estimate(text));
  }

  /// Check if text fits within budget
  bool fitsInBudget(String text, int budgetTokens) {
    return estimate(text) <= budgetTokens;
  }

  /// Truncate text to fit budget (best-effort, may exceed slightly)
  String truncateToFit(String text, int budgetTokens) {
    if (budgetTokens <= 0) return '';

    final estimated = estimate(text);
    if (estimated <= budgetTokens) return text;

    // Estimate max characters
    final maxChars = (budgetTokens * _charsPerToken).floor();
    if (maxChars >= text.length) return text;

    // Find a safe truncation point (avoid breaking mid-word/char)
    var cutPoint = maxChars;

    // Try to break at whitespace
    for (var i = maxChars; i > maxChars - 50 && i > 0; i--) {
      if (text[i] == ' ' || text[i] == '\n') {
        cutPoint = i;
        break;
      }
    }

    return '${text.substring(0, cutPoint)}...';
  }
}
