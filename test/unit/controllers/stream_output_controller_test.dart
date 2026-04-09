import 'package:chatboxapp/adapters/ai_provider.dart';
import 'package:chatboxapp/controllers/stream_output_controller.dart';
import 'package:chatboxapp/models/model_config.dart';
import 'package:chatboxapp/models/provider_config.dart';
import 'package:flutter_test/flutter_test.dart';

class _FakeEventProvider extends AIProvider {
  _FakeEventProvider(super.config);

  String? lastModelId;

  @override
  Future<List<String>> listAvailableModels() async => const [];

  @override
  Future<String> sendMessage({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
    String? modelId,
  }) async => 'ok';

  @override
  Stream<String> sendMessageStream({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
    String? modelId,
  }) async* {
    yield 'legacy';
  }

  @override
  Stream<AIStreamEvent> sendMessageEventStream({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
    String? modelId,
  }) async* {
    lastModelId = modelId;
    yield AIStreamEvent.thinking('先分析');
    yield AIStreamEvent.text('最终回答', isTypedSemantic: true);
  }

  @override
  Future<ProviderTestResult> testConnection() async {
    return ProviderTestResult.success(responseTimeMs: 1);
  }
}

ProviderConfig _providerConfig() => ProviderConfig(
  id: 'provider-1',
  name: 'Test',
  type: ProviderType.openai,
  apiUrl: 'https://api.example.com/v1',
  apiKey: 'sk-test',
);

void main() {
  group('StreamOutputController event stream', () {
    test('dispatches typed events and text chunks together', () async {
      final controller = StreamOutputController();
      final provider = _FakeEventProvider(_providerConfig());

      final chunks = <String>[];
      final events = <AIStreamEvent>[];
      var completed = false;

      await controller.startStreaming(
        provider: provider,
        modelName: 'gpt-4o-mini',
        modelId: 'model-1',
        messages: [ChatMessage(role: 'user', content: 'hello')],
        parameters: const ModelParameters(),
        onChunk: chunks.add,
        onEvent: events.add,
        onDone: () {
          completed = true;
        },
        onError: (error) => fail('unexpected error: $error'),
      );

      await Future<void>.delayed(const Duration(milliseconds: 10));

      expect(chunks, ['最终回答']);
      expect(events.map((e) => e.type), [
        AIStreamEventType.thinking,
        AIStreamEventType.text,
      ]);
      expect(provider.lastModelId, 'model-1');
      expect(completed, isTrue);
    });
  });
}
