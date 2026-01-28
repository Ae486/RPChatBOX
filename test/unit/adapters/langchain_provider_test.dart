import 'package:flutter_test/flutter_test.dart';

import 'package:chatboxapp/adapters/ai_provider.dart';
import 'package:chatboxapp/adapters/langchain_provider.dart';
import 'package:chatboxapp/adapters/langchain_message_mapper.dart';
import 'package:chatboxapp/adapters/provider_error_mapper.dart';
import 'package:chatboxapp/models/provider_config.dart';
import 'package:chatboxapp/models/model_config.dart';
import 'package:langchain_core/chat_models.dart' as lc;

void main() {
  group('LangChainProvider', () {
    group('fromConfig', () {
      test('creates LangChainProvider for OpenAI', () {
        final config = ProviderConfig(
          id: 'test-openai',
          name: 'Test OpenAI',
          type: ProviderType.openai,
          apiUrl: 'https://api.openai.com/v1',
          apiKey: 'test-key',
        );

        final provider = LangChainProvider.fromConfig(config);

        expect(provider, isA<LangChainProvider>());
        expect(provider.type, equals(ProviderType.openai));
      });

      test('creates LangChainProvider for Gemini', () {
        final config = ProviderConfig(
          id: 'test-gemini',
          name: 'Test Gemini',
          type: ProviderType.gemini,
          apiUrl: 'https://generativelanguage.googleapis.com/v1',
          apiKey: 'test-key',
        );

        final provider = LangChainProvider.fromConfig(config);

        expect(provider, isA<LangChainProvider>());
        expect(provider.type, equals(ProviderType.gemini));
      });

      test('creates LangChainProvider for DeepSeek', () {
        final config = ProviderConfig(
          id: 'test-deepseek',
          name: 'Test DeepSeek',
          type: ProviderType.deepseek,
          apiUrl: 'https://api.deepseek.com/v1',
          apiKey: 'test-key',
        );

        final provider = LangChainProvider.fromConfig(config);

        expect(provider, isA<LangChainProvider>());
        expect(provider.type, equals(ProviderType.deepseek));
      });

      test('creates LangChainProvider for Claude', () {
        final config = ProviderConfig(
          id: 'test-claude',
          name: 'Test Claude',
          type: ProviderType.claude,
          apiUrl: 'https://api.anthropic.com/v1',
          apiKey: 'test-key',
        );

        final provider = LangChainProvider.fromConfig(config);

        expect(provider, isA<LangChainProvider>());
        expect(provider.type, equals(ProviderType.claude));
      });
    });

    group('listAvailableModels', () {
      test('returns empty list when API is unreachable', () async {
        final config = ProviderConfig(
          id: 'test',
          name: 'Test',
          type: ProviderType.openai,
          apiUrl: 'https://api.openai.com',
          apiKey: 'test-key',
        );

        final provider = LangChainProvider.fromConfig(config);
        final models = await provider.listAvailableModels();

        // 无网络时返回空列表
        expect(models, isEmpty);
      });

      test('returns empty list for Gemini when API is unreachable', () async {
        final config = ProviderConfig(
          id: 'test',
          name: 'Test',
          type: ProviderType.gemini,
          apiUrl: 'https://generativelanguage.googleapis.com',
          apiKey: 'test-key',
        );

        final provider = LangChainProvider.fromConfig(config);
        final models = await provider.listAvailableModels();

        // 无网络时返回空列表
        expect(models, isEmpty);
      });
    });
  });

  group('ProviderFactory', () {
    test('returns LangChainProvider when useLangChain is true', () {
      ProviderFactory.useLangChain = true;

      final config = ProviderConfig(
        id: 'test',
        name: 'Test',
        type: ProviderType.openai,
        apiUrl: 'https://api.openai.com/v1',
        apiKey: 'test-key',
      );

      final provider = ProviderFactory.createProvider(config);

      expect(provider, isA<LangChainProvider>());
    });

    test('returns OpenAIProvider when useLangChain is false', () {
      ProviderFactory.useLangChain = false;

      final config = ProviderConfig(
        id: 'test',
        name: 'Test',
        type: ProviderType.openai,
        apiUrl: 'https://api.openai.com/v1',
        apiKey: 'test-key',
      );

      final provider = ProviderFactory.createProvider(config);

      expect(provider is LangChainProvider, isFalse);

      // Reset
      ProviderFactory.useLangChain = true;
    });

    test('creates provider for all ProviderType values', () {
      ProviderFactory.useLangChain = true;

      for (final type in ProviderType.values) {
        final config = ProviderConfig(
          id: 'test-${type.name}',
          name: 'Test ${type.name}',
          type: type,
          apiUrl: type.defaultApiUrl,
          apiKey: 'test-key',
        );

        final provider = ProviderFactory.createProvider(config);

        expect(provider, isA<LangChainProvider>(),
            reason: 'Should create LangChainProvider for ${type.name}');
      }
    });
  });

  group('LangChainMessageMapper', () {
    test('converts system message', () async {
      final messages = [
        ChatMessage(role: 'system', content: 'You are a helpful assistant.'),
      ];

      final lcMessages = await LangChainMessageMapper.toLangChainMessages(
        messages: messages,
        providerType: ProviderType.openai,
      );

      expect(lcMessages.length, equals(1));
      expect(lcMessages[0], isA<lc.SystemChatMessage>());
      expect((lcMessages[0] as lc.SystemChatMessage).content,
          equals('You are a helpful assistant.'));
    });

    test('converts user message', () async {
      final messages = [
        ChatMessage(role: 'user', content: 'Hello!'),
      ];

      final lcMessages = await LangChainMessageMapper.toLangChainMessages(
        messages: messages,
        providerType: ProviderType.openai,
      );

      expect(lcMessages.length, equals(1));
      expect(lcMessages[0], isA<lc.HumanChatMessage>());
    });

    test('converts assistant message', () async {
      final messages = [
        ChatMessage(role: 'assistant', content: 'Hi there!'),
      ];

      final lcMessages = await LangChainMessageMapper.toLangChainMessages(
        messages: messages,
        providerType: ProviderType.openai,
      );

      expect(lcMessages.length, equals(1));
      expect(lcMessages[0], isA<lc.AIChatMessage>());
      expect((lcMessages[0] as lc.AIChatMessage).content, equals('Hi there!'));
    });

    test('converts multiple messages in order', () async {
      final messages = [
        ChatMessage(role: 'system', content: 'System prompt'),
        ChatMessage(role: 'user', content: 'User message'),
        ChatMessage(role: 'assistant', content: 'Assistant response'),
      ];

      final lcMessages = await LangChainMessageMapper.toLangChainMessages(
        messages: messages,
        providerType: ProviderType.openai,
      );

      expect(lcMessages.length, equals(3));
      expect(lcMessages[0], isA<lc.SystemChatMessage>());
      expect(lcMessages[1], isA<lc.HumanChatMessage>());
      expect(lcMessages[2], isA<lc.AIChatMessage>());
    });
  });

  group('ProviderErrorMapper', () {
    test('maps authentication error', () {
      final error = Exception('Unauthorized: Invalid API key');
      final apiError = ProviderErrorMapper.toApiError(error, providerName: 'OpenAI');

      expect(apiError.statusCode, equals(401));
      expect(apiError.message, contains('API 密钥无效'));
      expect(apiError.isAuthError, isTrue);
    });

    test('maps rate limit error', () {
      final error = Exception('Rate limit exceeded');
      final apiError = ProviderErrorMapper.toApiError(error, providerName: 'OpenAI');

      expect(apiError.statusCode, equals(429));
      expect(apiError.message, contains('请求过于频繁'));
      expect(apiError.isRetryable, isTrue);
    });

    test('maps network error', () {
      final error = Exception('SocketException: Connection refused');
      final apiError = ProviderErrorMapper.toApiError(error, providerName: 'OpenAI');

      expect(apiError.statusCode, equals(503));
      expect(apiError.message, contains('网络连接失败'));
    });

    test('maps timeout error', () {
      final error = Exception('TimeoutException: Request timed out');
      final apiError = ProviderErrorMapper.toApiError(error, providerName: 'OpenAI');

      expect(apiError.statusCode, equals(504));
      expect(apiError.message, contains('请求超时'));
      expect(apiError.isRetryable, isTrue);
    });

    test('maps unknown error', () {
      final error = Exception('Some unknown error');
      final apiError = ProviderErrorMapper.toApiError(error, providerName: 'Test');

      expect(apiError.statusCode, equals(500));
      expect(apiError.message, contains('Test'));
    });
  });
}
