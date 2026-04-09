import 'package:chatboxapp/models/provider_config.dart';
import 'package:chatboxapp/utils/api_url_helper.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('ApiUrlHelper.getActualApiUrl', () {
    test('appends endpoint to plain base url', () {
      final url = ApiUrlHelper.getActualApiUrl(
        'https://api.example.com',
        ProviderType.openai,
      );

      expect(url, 'https://api.example.com/v1/chat/completions');
    });

    test('appends endpoint path when input already ends with /v1', () {
      final url = ApiUrlHelper.getActualApiUrl(
        'https://api.example.com/v1',
        ProviderType.openai,
      );

      expect(url, 'https://api.example.com/v1/chat/completions');
    });

    test('does not duplicate full openai endpoint suffix', () {
      final url = ApiUrlHelper.getActualApiUrl(
        'https://api.example.com/v1/chat/completions',
        ProviderType.openai,
      );

      expect(url, 'https://api.example.com/v1/chat/completions');
    });

    test('does not duplicate claude endpoint suffix', () {
      final url = ApiUrlHelper.getActualApiUrl(
        'https://api.example.com/v1/messages',
        ProviderType.claude,
      );

      expect(url, 'https://api.example.com/v1/messages');
    });
  });
}
