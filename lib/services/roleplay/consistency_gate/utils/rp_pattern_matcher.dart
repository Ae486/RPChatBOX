/// Pattern Matcher Utility
///
/// Provides bilingual (Chinese/English) pattern matching for
/// appearance, state, and presence detection in text.
/// POS: Services / Roleplay / Consistency Gate / Utils

/// Match result from pattern matching
class PatternMatch {
  /// The matched text
  final String matchedText;

  /// Start position in source text
  final int start;

  /// End position in source text
  final int end;

  /// The pattern category that matched
  final String category;

  /// The specific key within the category
  final String key;

  /// Confidence of this match (0.0 ~ 1.0)
  final double confidence;

  const PatternMatch({
    required this.matchedText,
    required this.start,
    required this.end,
    required this.category,
    required this.key,
    required this.confidence,
  });

  @override
  String toString() =>
      'PatternMatch($category.$key: "$matchedText" [$start:$end] conf=$confidence)';
}

/// Bilingual pattern matcher for roleplay consistency checking
class RpPatternMatcher {
  RpPatternMatcher._();

  // ============================================================
  // Appearance Patterns
  // ============================================================

  /// Hair-related patterns (bilingual)
  static const hairPatterns = [
    r'头发',
    r'发色',
    r'秀发',
    r'长发',
    r'短发',
    r'卷发',
    r'直发',
    r'发丝',
    r'hair',
    r'hairstyle',
    r'locks',
    r'tresses',
  ];

  /// Eye-related patterns (bilingual)
  static const eyePatterns = [
    r'眼睛',
    r'瞳色',
    r'双眸',
    r'眼眸',
    r'瞳孔',
    r'眼瞳',
    r'eyes?',
    r'gaze',
    r'pupils?',
    r'iris',
  ];

  /// Height-related patterns (bilingual)
  static const heightPatterns = [
    r'身高',
    r'个子',
    r'高大',
    r'矮小',
    r'height',
    r'tall',
    r'short',
    r'stature',
  ];

  /// Gender/pronoun patterns (bilingual)
  static const genderPatterns = [
    r'他(?!们)',
    r'她(?!们)',
    r'男(?:人|性|孩|子)?',
    r'女(?:人|性|孩|子)?',
    r'\bhe\b',
    r'\bshe\b',
    r'\bhim\b',
    r'\bher\b',
    r'\bhis\b',
    r'\bmale\b',
    r'\bfemale\b',
    r'\bman\b',
    r'\bwoman\b',
  ];

  // ============================================================
  // Color Synonyms
  // ============================================================

  /// Color term mappings (Chinese and English synonyms)
  static const colorSynonyms = <String, List<String>>{
    'black': [
      '黑色',
      '乌黑',
      '漆黑',
      '墨色',
      'black',
      'dark',
      'ebony',
      'jet',
      'raven'
    ],
    'white': ['白色', '雪白', '银白', 'white', 'silver', 'ivory', 'platinum'],
    'gold': [
      '金色',
      '金黄',
      '金灿灿',
      '淡金',
      'golden',
      'blonde',
      'blond',
      'gold'
    ],
    'red': ['红色', '赤红', '火红', '绯红', 'red', 'crimson', 'scarlet', 'ruby'],
    'blue': [
      '蓝色',
      '湛蓝',
      '深蓝',
      '碧蓝',
      'blue',
      'azure',
      'sapphire',
      'cerulean'
    ],
    'green': ['绿色', '翠绿', '碧绿', 'green', 'emerald', 'jade', 'verdant'],
    'brown': ['棕色', '褐色', '茶色', 'brown', 'chestnut', 'auburn', 'hazel'],
    'purple': ['紫色', '紫罗兰', '靛紫', 'purple', 'violet', 'lavender', 'amethyst'],
    'pink': ['粉色', '粉红', '桃粉', 'pink', 'rose', 'coral'],
    'gray': ['灰色', '灰白', '银灰', 'gray', 'grey', 'silver', 'ash'],
    'orange': ['橙色', '橘色', '橘黄', 'orange', 'amber', 'copper'],
  };

  // ============================================================
  // State Patterns
  // ============================================================

  /// Injury-related patterns
  static const injuryPatterns = [
    r'伤',
    r'痛',
    r'受伤',
    r'流血',
    r'断(?:臂|腿|手|脚)',
    r'骨折',
    r'injured',
    r'wound(?:ed)?',
    r'hurt',
    r'bleeding',
    r'broken',
  ];

  /// Item possession patterns
  static const itemPatterns = [
    r'拿着',
    r'持有',
    r'手中',
    r'携带',
    r'握着',
    r'提着',
    r'背着',
    r'挎着',
    r'holding',
    r'carrying',
    r'wielding',
    r'gripping',
  ];

  /// Action patterns
  static const actionPatterns = [
    r'拔出',
    r'挥舞',
    r'使用',
    r'施展',
    r'发动',
    r'drew',
    r'used',
    r'wielded',
    r'cast',
    r'activated',
  ];

  // ============================================================
  // Presence Patterns
  // ============================================================

  /// Dialogue/speech patterns
  static const dialoguePatterns = [
    r'说道?',
    r'道：',
    r'问道?',
    r'回答',
    r'喊道?',
    r'叫道?',
    r'"[^"]*"',
    r'「[^」]*」',
    r'said',
    r'asked',
    r'replied',
    r'shouted',
    r'whispered',
  ];

  /// Character action patterns (for presence check)
  static const characterActionPatterns = [
    r'走(?:了|过来|进|出|向)',
    r'站(?:起|着|在)',
    r'坐(?:着|下)',
    r'看(?:着|向)',
    r'转身',
    r'点头',
    r'摇头',
    r'walked',
    r'stood',
    r'sat',
    r'looked',
    r'turned',
    r'nodded',
  ];

  // ============================================================
  // Matching Methods
  // ============================================================

  /// Find all matches for a pattern list in text
  static List<PatternMatch> findMatches(
    String text,
    List<String> patterns, {
    required String category,
    required String key,
    bool caseSensitive = false,
  }) {
    final matches = <PatternMatch>[];
    final flags = caseSensitive ? '' : 'i';

    for (final pattern in patterns) {
      final regex = RegExp(pattern, caseSensitive: caseSensitive);
      for (final match in regex.allMatches(text)) {
        matches.add(PatternMatch(
          matchedText: match.group(0)!,
          start: match.start,
          end: match.end,
          category: category,
          key: key,
          confidence: _calculateConfidence(match.group(0)!, pattern),
        ));
      }
    }

    return matches;
  }

  /// Find color mentions in text and return normalized color names
  static Map<String, List<PatternMatch>> findColorMentions(String text) {
    final results = <String, List<PatternMatch>>{};

    for (final entry in colorSynonyms.entries) {
      final colorName = entry.key;
      final synonyms = entry.value;
      final matches = findMatches(
        text,
        synonyms,
        category: 'color',
        key: colorName,
      );

      if (matches.isNotEmpty) {
        results[colorName] = matches;
      }
    }

    return results;
  }

  /// Check if two color terms refer to the same color
  static bool areColorsEquivalent(String color1, String color2) {
    final normalized1 = _normalizeColor(color1);
    final normalized2 = _normalizeColor(color2);
    return normalized1 == normalized2;
  }

  /// Normalize a color term to its canonical form
  static String? _normalizeColor(String colorTerm) {
    final lower = colorTerm.toLowerCase();
    for (final entry in colorSynonyms.entries) {
      for (final synonym in entry.value) {
        if (RegExp(synonym, caseSensitive: false).hasMatch(lower)) {
          return entry.key;
        }
      }
    }
    return null;
  }

  /// Calculate confidence based on match quality
  static double _calculateConfidence(String matched, String pattern) {
    // Exact matches get higher confidence
    if (matched.toLowerCase() == pattern.toLowerCase()) {
      return 1.0;
    }
    // Longer matches generally more reliable
    if (matched.length >= 4) {
      return 0.9;
    }
    if (matched.length >= 2) {
      return 0.7;
    }
    return 0.5;
  }

  /// Extract character names mentioned in text
  static List<String> extractCharacterNames(
    String text,
    List<String> knownCharacters,
  ) {
    final found = <String>[];

    for (final name in knownCharacters) {
      if (text.contains(name)) {
        found.add(name);
      }
    }

    return found;
  }

  /// Check if text mentions a specific appearance attribute
  static bool mentionsAppearance(String text, String attribute) {
    List<String> patterns;
    switch (attribute.toLowerCase()) {
      case 'hair':
        patterns = hairPatterns;
        break;
      case 'eye':
      case 'eyes':
        patterns = eyePatterns;
        break;
      case 'height':
        patterns = heightPatterns;
        break;
      case 'gender':
        patterns = genderPatterns;
        break;
      default:
        return false;
    }

    for (final pattern in patterns) {
      if (RegExp(pattern, caseSensitive: false).hasMatch(text)) {
        return true;
      }
    }
    return false;
  }
}
