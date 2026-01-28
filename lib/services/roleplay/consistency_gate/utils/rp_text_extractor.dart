/// Text Extractor Utility
///
/// Extracts relevant information from output text for validation.
/// POS: Services / Roleplay / Consistency Gate / Utils

import 'rp_pattern_matcher.dart';

/// Result of appearance extraction
class AppearanceRef {
  /// Attribute type (e.g., 'hair_color', 'eye_color')
  final String attribute;

  /// Detected value
  final String value;

  /// Position in source text
  final int position;

  /// Confidence of extraction
  final double confidence;

  const AppearanceRef({
    required this.attribute,
    required this.value,
    required this.position,
    required this.confidence,
  });

  @override
  String toString() => 'AppearanceRef($attribute: $value)';
}

/// Result of character reference extraction
class CharacterRef {
  /// Character name
  final String name;

  /// Type of reference (dialogue, action, mention)
  final CharacterRefType type;

  /// Position in source text
  final int position;

  /// The specific text that referenced the character
  final String context;

  const CharacterRef({
    required this.name,
    required this.type,
    required this.position,
    required this.context,
  });

  @override
  String toString() => 'CharacterRef($name: $type)';
}

/// Type of character reference
enum CharacterRefType {
  /// Character is speaking (dialogue)
  dialogue,

  /// Character is performing an action
  action,

  /// Character is mentioned (indirect)
  mention,
}

/// Result of item reference extraction
class ItemRef {
  /// Item name
  final String itemName;

  /// Usage type (possession, use, draw)
  final ItemUsageType usageType;

  /// Position in source text
  final int position;

  /// Context around the item reference
  final String context;

  const ItemRef({
    required this.itemName,
    required this.usageType,
    required this.position,
    required this.context,
  });

  @override
  String toString() => 'ItemRef($itemName: $usageType)';
}

/// Type of item usage
enum ItemUsageType {
  /// Character possesses the item
  possession,

  /// Character uses the item
  use,

  /// Character draws/equips the item
  draw,
}

/// Extracts information from roleplay output text
class RpTextExtractor {
  RpTextExtractor._();

  /// Extract appearance references from text
  static List<AppearanceRef> extractAppearanceRefs(String text) {
    final refs = <AppearanceRef>[];

    // Extract hair color mentions
    final hairMatches = RpPatternMatcher.findMatches(
      text,
      RpPatternMatcher.hairPatterns,
      category: 'appearance',
      key: 'hair',
    );

    if (hairMatches.isNotEmpty) {
      // Find associated color
      final colors = RpPatternMatcher.findColorMentions(text);
      for (final colorEntry in colors.entries) {
        for (final colorMatch in colorEntry.value) {
          // Check if color is near hair mention
          for (final hairMatch in hairMatches) {
            if ((colorMatch.start - hairMatch.end).abs() < 20 ||
                (hairMatch.start - colorMatch.end).abs() < 20) {
              refs.add(AppearanceRef(
                attribute: 'hair_color',
                value: colorEntry.key,
                position: hairMatch.start,
                confidence: (hairMatch.confidence + colorMatch.confidence) / 2,
              ));
            }
          }
        }
      }
    }

    // Extract eye color mentions
    final eyeMatches = RpPatternMatcher.findMatches(
      text,
      RpPatternMatcher.eyePatterns,
      category: 'appearance',
      key: 'eye',
    );

    if (eyeMatches.isNotEmpty) {
      final colors = RpPatternMatcher.findColorMentions(text);
      for (final colorEntry in colors.entries) {
        for (final colorMatch in colorEntry.value) {
          for (final eyeMatch in eyeMatches) {
            if ((colorMatch.start - eyeMatch.end).abs() < 20 ||
                (eyeMatch.start - colorMatch.end).abs() < 20) {
              refs.add(AppearanceRef(
                attribute: 'eye_color',
                value: colorEntry.key,
                position: eyeMatch.start,
                confidence: (eyeMatch.confidence + colorMatch.confidence) / 2,
              ));
            }
          }
        }
      }
    }

    // Extract height mentions
    final heightMatches = RpPatternMatcher.findMatches(
      text,
      RpPatternMatcher.heightPatterns,
      category: 'appearance',
      key: 'height',
    );

    for (final match in heightMatches) {
      refs.add(AppearanceRef(
        attribute: 'height',
        value: match.matchedText,
        position: match.start,
        confidence: match.confidence,
      ));
    }

    // Extract gender mentions
    final genderMatches = RpPatternMatcher.findMatches(
      text,
      RpPatternMatcher.genderPatterns,
      category: 'appearance',
      key: 'gender',
    );

    for (final match in genderMatches) {
      String gender = 'unknown';
      final lower = match.matchedText.toLowerCase();
      if (lower == '他' ||
          lower == 'he' ||
          lower == 'him' ||
          lower == 'his' ||
          lower.contains('男') ||
          lower == 'male' ||
          lower == 'man') {
        gender = 'male';
      } else if (lower == '她' ||
          lower == 'she' ||
          lower == 'her' ||
          lower.contains('女') ||
          lower == 'female' ||
          lower == 'woman') {
        gender = 'female';
      }

      if (gender != 'unknown') {
        refs.add(AppearanceRef(
          attribute: 'gender',
          value: gender,
          position: match.start,
          confidence: match.confidence,
        ));
      }
    }

    return refs;
  }

  /// Extract item references from text
  static List<ItemRef> extractItemRefs(
    String text, {
    List<String> knownItems = const [],
  }) {
    final refs = <ItemRef>[];

    // Find possession patterns
    final possessionMatches = RpPatternMatcher.findMatches(
      text,
      RpPatternMatcher.itemPatterns,
      category: 'state',
      key: 'possession',
    );

    // Find action patterns (drawing/using items)
    final actionMatches = RpPatternMatcher.findMatches(
      text,
      RpPatternMatcher.actionPatterns,
      category: 'state',
      key: 'action',
    );

    // Extract context around matches and look for known items
    for (final match in possessionMatches) {
      final context = _extractContext(text, match.start, match.end);
      for (final item in knownItems) {
        if (context.contains(item)) {
          refs.add(ItemRef(
            itemName: item,
            usageType: ItemUsageType.possession,
            position: match.start,
            context: context,
          ));
        }
      }
    }

    for (final match in actionMatches) {
      final context = _extractContext(text, match.start, match.end);
      final usageType = match.matchedText.contains(RegExp(r'拔|drew'))
          ? ItemUsageType.draw
          : ItemUsageType.use;
      for (final item in knownItems) {
        if (context.contains(item)) {
          refs.add(ItemRef(
            itemName: item,
            usageType: usageType,
            position: match.start,
            context: context,
          ));
        }
      }
    }

    return refs;
  }

  /// Extract character references from text
  static List<CharacterRef> extractCharacterRefs(
    String text,
    List<String> knownCharacters,
  ) {
    final refs = <CharacterRef>[];

    // Find dialogue patterns
    final dialogueMatches = RpPatternMatcher.findMatches(
      text,
      RpPatternMatcher.dialoguePatterns,
      category: 'presence',
      key: 'dialogue',
    );

    // Find action patterns
    final actionMatches = RpPatternMatcher.findMatches(
      text,
      RpPatternMatcher.characterActionPatterns,
      category: 'presence',
      key: 'action',
    );

    // Check character names around dialogue
    for (final match in dialogueMatches) {
      final context = _extractContext(text, match.start, match.end, radius: 30);
      for (final character in knownCharacters) {
        if (context.contains(character)) {
          refs.add(CharacterRef(
            name: character,
            type: CharacterRefType.dialogue,
            position: match.start,
            context: context,
          ));
        }
      }
    }

    // Check character names around actions
    for (final match in actionMatches) {
      final context = _extractContext(text, match.start, match.end, radius: 30);
      for (final character in knownCharacters) {
        if (context.contains(character)) {
          refs.add(CharacterRef(
            name: character,
            type: CharacterRefType.action,
            position: match.start,
            context: context,
          ));
        }
      }
    }

    // Simple mention detection
    for (final character in knownCharacters) {
      int index = 0;
      while ((index = text.indexOf(character, index)) != -1) {
        // Check if not already captured as dialogue or action
        final alreadyCaptured = refs.any((r) =>
            r.name == character &&
            (r.position - index).abs() < 50 &&
            r.type != CharacterRefType.mention);

        if (!alreadyCaptured) {
          refs.add(CharacterRef(
            name: character,
            type: CharacterRefType.mention,
            position: index,
            context: _extractContext(text, index, index + character.length),
          ));
        }
        index += character.length;
      }
    }

    return refs;
  }

  /// Extract actions/verbs from text
  static List<String> extractActions(String text) {
    final actions = <String>[];

    final matches = RpPatternMatcher.findMatches(
      text,
      [
        ...RpPatternMatcher.actionPatterns,
        ...RpPatternMatcher.characterActionPatterns,
      ],
      category: 'action',
      key: 'verb',
    );

    for (final match in matches) {
      actions.add(match.matchedText);
    }

    return actions;
  }

  /// Extract a context window around a position
  static String _extractContext(String text, int start, int end,
      {int radius = 50}) {
    final contextStart = (start - radius).clamp(0, text.length);
    final contextEnd = (end + radius).clamp(0, text.length);
    return text.substring(contextStart, contextEnd);
  }

  /// Check if text contains injury/state mentions
  static bool containsInjuryMention(String text) {
    final matches = RpPatternMatcher.findMatches(
      text,
      RpPatternMatcher.injuryPatterns,
      category: 'state',
      key: 'injury',
    );
    return matches.isNotEmpty;
  }
}
