import 'package:flutter_test/flutter_test.dart';
import 'package:chatboxapp/services/roleplay/context_compiler/rp_token_estimator.dart';

void main() {
  group('RpTokenEstimator', () {
    const estimator = RpTokenEstimator();

    test('should estimate tokens based on character count', () {
      const text = 'Hello, World!'; // 13 characters
      final tokens = estimator.estimate(text);

      expect(tokens, (13 / 3.5).ceil()); // 4 tokens
    });

    test('should return 0 for empty text', () {
      final tokens = estimator.estimate('');
      expect(tokens, 0);
    });

    test('should estimate multiple texts', () {
      final texts = ['Hello', 'World'];
      final tokens = estimator.estimateAll(texts);

      expect(tokens, estimator.estimate('Hello') + estimator.estimate('World'));
    });

    test('fitsInBudget should return true when within budget', () {
      const text = 'Hello';
      expect(estimator.fitsInBudget(text, 10), true);
    });

    test('fitsInBudget should return false when over budget', () {
      const text = 'This is a much longer text that should exceed the budget';
      expect(estimator.fitsInBudget(text, 1), false);
    });

    test('truncateToFit should return full text when within budget', () {
      const text = 'Hello';
      final result = estimator.truncateToFit(text, 100);
      expect(result, text);
    });

    test('truncateToFit should truncate when over budget', () {
      const text = 'This is a much longer text that needs to be truncated';
      final result = estimator.truncateToFit(text, 5);

      expect(result.length < text.length, true);
      expect(result.endsWith('...'), true);
    });

    test('truncateToFit should return empty for zero budget', () {
      const text = 'Hello';
      final result = estimator.truncateToFit(text, 0);
      expect(result, '');
    });

    test('should handle CJK mixed text', () {
      const text = '你好世界Hello'; // 9 characters
      final tokens = estimator.estimate(text);

      expect(tokens, (9 / 3.5).ceil());
    });

    test('should allow custom chars per token', () {
      const customEstimator = RpTokenEstimator(charsPerToken: 4.0);
      const text = 'Hello World!'; // 12 characters
      final tokens = customEstimator.estimate(text);

      expect(tokens, 3); // 12 / 4 = 3
    });
  });
}
