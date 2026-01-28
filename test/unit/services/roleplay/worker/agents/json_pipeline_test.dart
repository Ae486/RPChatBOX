import 'package:flutter_test/flutter_test.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/json/json_extractor.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/json/json_sanitizer.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/json/json_validator.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/json/json_repairer.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/json/json_pipeline.dart';

void main() {
  group('JsonExtractor', () {
    late JsonExtractor extractor;

    setUp(() {
      extractor = JsonExtractor();
    });

    test('extracts JSON from fenced code block', () {
      const input = '''
Some text before
```json
{"key": "value"}
```
Some text after
''';
      expect(extractor.extract(input), '{"key": "value"}');
    });

    test('extracts JSON from plain code block', () {
      const input = '''
```
{"detected": true}
```
''';
      expect(extractor.extract(input), '{"detected": true}');
    });

    test('extracts JSON by brace matching', () {
      const input = 'Here is the result: {"ok": true, "data": [1,2,3]} end';
      expect(extractor.extract(input), '{"ok": true, "data": [1,2,3]}');
    });

    test('extracts array JSON when no object present', () {
      const input = 'Result: ["a", "b", "c"]';
      final result = extractor.extract(input);
      expect(result, isNotNull);
      expect(result, '["a", "b", "c"]');
    });

    test('returns null for no JSON', () {
      const input = 'No JSON here';
      expect(extractor.extract(input), isNull);
    });
  });

  group('JsonSanitizer', () {
    late JsonSanitizer sanitizer;

    setUp(() {
      sanitizer = JsonSanitizer();
    });

    test('removes trailing commas', () {
      const input = '{"a": 1, "b": 2,}';
      expect(sanitizer.sanitize(input), '{"a": 1, "b": 2}');
    });

    test('fixes smart quotes', () {
      const input = '{"key": "value"}';
      expect(sanitizer.sanitize(input), '{"key": "value"}');
    });

    test('fixes Python booleans', () {
      const input = '{"ok": True, "error": None, "valid": False}';
      expect(sanitizer.sanitize(input), '{"ok": true, "error": null, "valid": false}');
    });

    test('fixes unquoted keys', () {
      const input = '{detected: true, count: 5}';
      expect(sanitizer.sanitize(input), '{"detected": true, "count": 5}');
    });

    test('fixes single quotes', () {
      const input = "{'key': 'value'}";
      expect(sanitizer.sanitize(input), '{"key": "value"}');
    });
  });

  group('JsonValidator', () {
    late JsonValidator validator;

    setUp(() {
      validator = JsonValidator();
    });

    test('validates correct JSON', () {
      const input = '{"detected": true, "updates": []}';
      final result = validator.validate(input);
      expect(result.valid, isTrue);
      expect(result.data, isNotNull);
    });

    test('fails on invalid JSON', () {
      const input = '{invalid json}';
      final result = validator.validate(input);
      expect(result.valid, isFalse);
    });

    test('accepts array as valid', () {
      const input = '[{"a": 1}]';
      final result = validator.validate(input);
      expect(result.valid, isTrue);
    });
  });

  group('JsonRepairer', () {
    late JsonRepairer repairer;

    setUp(() {
      repairer = JsonRepairer();
    });

    test('ensures required fields exist', () {
      const input = '{"detected": true}';
      final result = repairer.repair(input);
      expect(result.contains('"ok"'), isTrue);
    });

    test('handles parse failure gracefully', () {
      const input = 'not json at all';
      final result = repairer.repair(input);
      expect(result.contains('"ok"'), isTrue);
      expect(result.contains('false'), isTrue);
    });
  });

  group('JsonPipeline', () {
    late JsonPipeline pipeline;

    setUp(() {
      pipeline = JsonPipeline();
    });

    test('processes valid JSON successfully', () async {
      const input = '{"detected": false}';
      final result = await pipeline.process(input);
      expect(result.success, isTrue);
      expect(result.repairStage, 0);
    });

    test('repairs and processes invalid JSON', () async {
      const input = '''
Here is the result:
```json
{detected: True, updates: [],}
```
''';
      final result = await pipeline.process(input);
      expect(result.success, isTrue);
    });

    test('fails on completely invalid input', () async {
      const input = 'No JSON anywhere';
      final result = await pipeline.process(input);
      expect(result.success, isFalse);
      expect(result.errorCode, isNotNull);
    });
  });
}
