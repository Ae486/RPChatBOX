import 'package:flutter_test/flutter_test.dart';
import 'package:chatboxapp/services/roleplay/consistency_gate/utils/rp_pattern_matcher.dart';

void main() {
  group('RpPatternMatcher', () {
    group('findMatches', () {
      test('should find Chinese hair patterns', () {
        const text = '她甩了甩金色的长发，秀发在阳光下闪闪发光。';

        final matches = RpPatternMatcher.findMatches(
          text,
          RpPatternMatcher.hairPatterns,
          category: 'appearance',
          key: 'hair',
        );

        expect(matches.length, greaterThanOrEqualTo(2));
        expect(matches.any((m) => m.matchedText.contains('长发')), true);
        expect(matches.any((m) => m.matchedText.contains('秀发')), true);
      });

      test('should find English hair patterns', () {
        const text = 'She ran her fingers through her golden hair.';

        final matches = RpPatternMatcher.findMatches(
          text,
          RpPatternMatcher.hairPatterns,
          category: 'appearance',
          key: 'hair',
        );

        expect(matches.length, greaterThanOrEqualTo(1));
        expect(matches.any((m) => m.matchedText.toLowerCase() == 'hair'), true);
      });

      test('should find eye patterns', () {
        const text = '他的眼睛是蓝色的，眼眸中透着智慧。';

        final matches = RpPatternMatcher.findMatches(
          text,
          RpPatternMatcher.eyePatterns,
          category: 'appearance',
          key: 'eye',
        );

        expect(matches.length, greaterThanOrEqualTo(2));
      });

      test('should find gender patterns', () {
        const text = '他走向前去，她则留在原地。';

        final matches = RpPatternMatcher.findMatches(
          text,
          RpPatternMatcher.genderPatterns,
          category: 'appearance',
          key: 'gender',
        );

        expect(matches.length, greaterThanOrEqualTo(2));
        expect(matches.any((m) => m.matchedText == '他'), true);
        expect(matches.any((m) => m.matchedText == '她'), true);
      });
    });

    group('findColorMentions', () {
      test('should find Chinese color mentions', () {
        const text = '她的黑色长发和蓝色眼眸十分引人注目。';

        final colors = RpPatternMatcher.findColorMentions(text);

        expect(colors.containsKey('black'), true);
        expect(colors.containsKey('blue'), true);
      });

      test('should find English color mentions', () {
        const text = 'Her golden hair and emerald eyes caught his attention.';

        final colors = RpPatternMatcher.findColorMentions(text);

        expect(colors.containsKey('gold'), true);
        expect(colors.containsKey('green'), true);
      });

      test('should handle mixed language', () {
        const text = 'She had 金色 hair and blue 眼睛.';

        final colors = RpPatternMatcher.findColorMentions(text);

        expect(colors.containsKey('gold'), true);
        expect(colors.containsKey('blue'), true);
      });
    });

    group('areColorsEquivalent', () {
      test('should match same color synonyms', () {
        expect(RpPatternMatcher.areColorsEquivalent('黑色', 'black'), true);
        expect(RpPatternMatcher.areColorsEquivalent('金色', 'golden'), true);
        expect(RpPatternMatcher.areColorsEquivalent('blonde', 'gold'), true);
      });

      test('should not match different colors', () {
        expect(RpPatternMatcher.areColorsEquivalent('黑色', 'gold'), false);
        expect(RpPatternMatcher.areColorsEquivalent('red', 'blue'), false);
      });
    });

    group('extractCharacterNames', () {
      test('should find known character names', () {
        const text = '艾拉走向约翰，两人开始交谈。';
        final names = RpPatternMatcher.extractCharacterNames(
          text,
          ['艾拉', '约翰', '玛丽'],
        );

        expect(names.length, 2);
        expect(names.contains('艾拉'), true);
        expect(names.contains('约翰'), true);
        expect(names.contains('玛丽'), false);
      });
    });

    group('mentionsAppearance', () {
      test('should detect hair mentions', () {
        expect(RpPatternMatcher.mentionsAppearance('她的头发很长', 'hair'), true);
        expect(RpPatternMatcher.mentionsAppearance('her hair', 'hair'), true);
        expect(RpPatternMatcher.mentionsAppearance('普通文本', 'hair'), false);
      });

      test('should detect eye mentions', () {
        expect(RpPatternMatcher.mentionsAppearance('他的眼睛', 'eye'), true);
        expect(RpPatternMatcher.mentionsAppearance('his eyes', 'eyes'), true);
      });

      test('should detect gender mentions', () {
        expect(RpPatternMatcher.mentionsAppearance('他说道', 'gender'), true);
        expect(RpPatternMatcher.mentionsAppearance('she said', 'gender'), true);
      });
    });
  });

  group('PatternMatch', () {
    test('should hold match data correctly', () {
      const match = PatternMatch(
        matchedText: '头发',
        start: 10,
        end: 12,
        category: 'appearance',
        key: 'hair',
        confidence: 0.9,
      );

      expect(match.matchedText, '头发');
      expect(match.start, 10);
      expect(match.end, 12);
      expect(match.category, 'appearance');
      expect(match.key, 'hair');
      expect(match.confidence, 0.9);
    });
  });
}
