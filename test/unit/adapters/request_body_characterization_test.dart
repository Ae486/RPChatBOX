import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:chatboxapp/adapters/ai_provider.dart';
import 'package:chatboxapp/adapters/hybrid_langchain_provider.dart';
import 'package:chatboxapp/adapters/proxy_openai_provider.dart';
import 'package:chatboxapp/models/backend_mode.dart';
import 'package:chatboxapp/models/circuit_breaker_config.dart';
import 'package:chatboxapp/models/model_config.dart';
import 'package:chatboxapp/models/provider_config.dart';
import 'package:chatboxapp/services/dio_service.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('request body characterization', () {
    setUp(() {
      ProxyOpenAIProvider.debugResetProviderRegistrySyncCache();
      ProxyOpenAIProvider.debugSetPreferTypedStreamEvents(true);
    });

    test(
      'HybridLangChainProvider filters empty system messages and trims unsupported defaults',
      () async {
        final captureAdapter = _CaptureHttpClientAdapter();
        final dio = DioService().dataPlaneDio;
        final originalAdapter = dio.httpClientAdapter;
        dio.httpClientAdapter = captureAdapter;
        addTearDown(() => dio.httpClientAdapter = originalAdapter);

        final provider = HybridLangChainProvider(
          _buildProviderConfig(apiUrl: 'https://direct.example.test/capture#'),
        );

        await provider.sendMessage(
          model: 'gpt-4o-mini',
          messages: [
            ChatMessage(role: 'system', content: ''),
            ChatMessage(role: 'user', content: 'hello'),
          ],
          parameters: const ModelParameters(
            temperature: 0.7,
            maxTokens: 2048,
            topP: 1.0,
            frequencyPenalty: 0.0,
            presencePenalty: 0.0,
            streamOutput: false,
          ),
        );

        final capturedRequest = captureAdapter.singleRequest('/capture');
        final body = capturedRequest.json;

        expect(body['model'], 'gpt-4o-mini');
        expect(body['stream'], isFalse);
        expect(body['include_reasoning'], isTrue);
        expect(body['messages'], [
          {'role': 'user', 'content': 'hello'},
        ]);
        expect(body['temperature'], 0.7);
        expect(body['max_tokens'], 2048);
        expect(body.containsKey('top_p'), isFalse);
        expect(body.containsKey('frequency_penalty'), isFalse);
        expect(body.containsKey('presence_penalty'), isFalse);
      },
    );

    test(
      'HybridLangChainProvider converts attached text and image files into multimodal content',
      () async {
        final captureAdapter = _CaptureHttpClientAdapter();
        final dio = DioService().dataPlaneDio;
        final originalAdapter = dio.httpClientAdapter;
        dio.httpClientAdapter = captureAdapter;
        addTearDown(() => dio.httpClientAdapter = originalAdapter);

        final tempDir = await Directory.systemTemp.createTemp(
          'request-body-hybrid',
        );
        addTearDown(() async {
          if (await tempDir.exists()) {
            await tempDir.delete(recursive: true);
          }
        });

        final textFile = File('${tempDir.path}\\notes.txt')
          ..writeAsStringSync('Alpha content');
        final imageFile = File('${tempDir.path}\\image.png')
          ..writeAsBytesSync(const [0x89, 0x50, 0x4E, 0x47]);

        final provider = HybridLangChainProvider(
          _buildProviderConfig(apiUrl: 'https://direct.example.test/capture#'),
        );

        await provider.sendMessage(
          model: 'gpt-4o-mini',
          messages: [ChatMessage(role: 'user', content: 'Summarize the files')],
          parameters: const ModelParameters(streamOutput: false),
          files: [
            AttachedFileData(
              path: textFile.path,
              mimeType: 'text/plain',
              name: 'notes.txt',
            ),
            AttachedFileData(
              path: imageFile.path,
              mimeType: 'image/png',
              name: 'image.png',
            ),
          ],
        );

        final body = captureAdapter.singleRequest('/capture').json;
        final messages = body['messages'] as List<dynamic>;
        final userMessage = messages.single as Map<String, dynamic>;
        final content = userMessage['content'] as List<dynamic>;

        expect(content, hasLength(2));

        final textPart = content[0] as Map<String, dynamic>;
        final imagePart = content[1] as Map<String, dynamic>;

        expect(textPart['type'], 'text');
        final textValue = textPart['text'] as String;
        expect(textValue, contains('以下是文件 "notes.txt" (text/plain) 的内容:'));
        expect(textValue, contains('Alpha content'));
        expect(textValue, contains('Summarize the files'));

        expect(imagePart['type'], 'image_url');
        expect(
          (imagePart['image_url'] as Map<String, dynamic>)['url'] as String,
          startsWith('data:image/png;base64,'),
        );
      },
    );

    test(
      'ProxyOpenAIProvider requests typed stream mode for proxy streaming',
      () async {
        final captureAdapter = _StreamingCaptureHttpClientAdapter();
        final dataDio = DioService().dataPlaneDio;
        final controlDio = DioService().controlPlaneDio;
        final originalDataAdapter = dataDio.httpClientAdapter;
        final originalControlAdapter = controlDio.httpClientAdapter;
        dataDio.httpClientAdapter = captureAdapter;
        controlDio.httpClientAdapter = captureAdapter;
        addTearDown(() {
          dataDio.httpClientAdapter = originalDataAdapter;
          controlDio.httpClientAdapter = originalControlAdapter;
        });

        final provider = ProxyOpenAIProvider(
          _buildProviderConfig(
            apiUrl: 'https://api.example.com/v1/chat/completions#',
            proxyApiUrl: 'https://proxy.example.test',
          ),
        );

        final outputs = await provider
            .sendMessageStream(
              model: 'gpt-4o-mini',
              messages: [ChatMessage(role: 'user', content: 'hello')],
              parameters: const ModelParameters(streamOutput: true),
            )
            .toList();

        final body = captureAdapter.singleRequest('/v1/chat/completions').json;
        expect(body['stream'], isTrue);
        expect(body['stream_event_mode'], 'typed');
        expect(outputs, ['ok']);
      },
    );

    test(
      'ProxyOpenAIProvider syncs backend registry and sends provider reference plus files metadata',
      () async {
        final captureAdapter = _CaptureHttpClientAdapter();
        final dataDio = DioService().dataPlaneDio;
        final controlDio = DioService().controlPlaneDio;
        final originalDataAdapter = dataDio.httpClientAdapter;
        final originalControlAdapter = controlDio.httpClientAdapter;
        dataDio.httpClientAdapter = captureAdapter;
        controlDio.httpClientAdapter = captureAdapter;
        addTearDown(() {
          dataDio.httpClientAdapter = originalDataAdapter;
          controlDio.httpClientAdapter = originalControlAdapter;
        });

        final tempDir = await Directory.systemTemp.createTemp(
          'request-body-proxy',
        );
        addTearDown(() async {
          if (await tempDir.exists()) {
            await tempDir.delete(recursive: true);
          }
        });

        final textFile = File('${tempDir.path}\\notes.txt')
          ..writeAsStringSync('Alpha content');

        final provider = ProxyOpenAIProvider(
          _buildProviderConfig(
            apiUrl: 'https://api.example.com/v1/chat/completions#',
            proxyApiUrl: 'https://proxy.example.test',
          ),
        );

        await provider.sendMessage(
          model: 'gpt-4o-mini',
          messages: [
            ChatMessage(role: 'system', content: ''),
            ChatMessage(role: 'user', content: 'hello'),
          ],
          parameters: const ModelParameters(
            temperature: 0.7,
            maxTokens: 2048,
            topP: 1.0,
            frequencyPenalty: 0.0,
            presencePenalty: 0.0,
            streamOutput: false,
          ),
          files: [
            AttachedFileData(
              path: textFile.path,
              mimeType: 'text/plain',
              name: 'notes.txt',
            ),
          ],
        );

        final registryBody = captureAdapter
            .singleRequest('/api/providers/provider-1')
            .json;
        final body = captureAdapter.singleRequest('/v1/chat/completions').json;

        expect(body['model'], 'gpt-4o-mini');
        expect(body['stream'], isFalse);
        expect(body['include_reasoning'], isTrue);
        expect(body['provider_id'], 'provider-1');
        expect(body.containsKey('provider'), isFalse);
        expect(body['messages'], [
          {'role': 'system', 'content': ''},
          {'role': 'user', 'content': 'hello'},
        ]);
        expect(body['temperature'], 0.7);
        expect(body['max_tokens'], 2048);
        expect(body['top_p'], 1.0);
        expect(body['frequency_penalty'], 0.0);
        expect(body['presence_penalty'], 0.0);
        expect(body['files'], [
          {
            'path': textFile.path,
            'mime_type': 'text/plain',
            'name': 'notes.txt',
          },
        ]);
        expect(registryBody['id'], 'provider-1');
        expect(registryBody['name'], 'Test Provider');
        expect(registryBody['type'], 'openai');
        expect(registryBody['api_key'], 'sk-test');
        expect(
          registryBody['api_url'],
          'https://api.example.com/v1/chat/completions',
        );
        expect(registryBody['is_enabled'], true);
        expect(registryBody['created_at'], isA<String>());
        expect(registryBody['updated_at'], isA<String>());
        expect(registryBody['custom_headers'], <String, dynamic>{});
        expect(registryBody['description'], isNull);
        expect(registryBody.containsKey('backend_mode'), isFalse);
        expect(registryBody.containsKey('fallback_enabled'), isFalse);
        expect(registryBody.containsKey('fallback_timeout_ms'), isFalse);
      },
    );

    test(
      'ProxyOpenAIProvider persists explicit routing hints into backend registry sync payload',
      () async {
        final captureAdapter = _CaptureHttpClientAdapter();
        final dataDio = DioService().dataPlaneDio;
        final controlDio = DioService().controlPlaneDio;
        final originalDataAdapter = dataDio.httpClientAdapter;
        final originalControlAdapter = controlDio.httpClientAdapter;
        dataDio.httpClientAdapter = captureAdapter;
        controlDio.httpClientAdapter = captureAdapter;
        addTearDown(() {
          dataDio.httpClientAdapter = originalDataAdapter;
          controlDio.httpClientAdapter = originalControlAdapter;
        });

        final provider = ProxyOpenAIProvider(
          _buildProviderConfig(
            apiUrl: 'https://api.example.com/v1/chat/completions#',
            proxyApiUrl: 'https://proxy.example.test',
            backendMode: BackendMode.auto,
            fallbackEnabled: false,
            fallbackTimeoutMs: 9000,
            circuitBreaker: const CircuitBreakerConfig(
              failureThreshold: 4,
              windowMs: 120000,
              openMs: 45000,
              halfOpenMaxCalls: 3,
            ),
          ),
        );

        await provider.sendMessage(
          model: 'gpt-4o-mini',
          messages: [ChatMessage(role: 'user', content: 'hello')],
          parameters: const ModelParameters(streamOutput: false),
        );

        final registryBody = captureAdapter
            .singleRequest('/api/providers/provider-1')
            .json;
        final body = captureAdapter.singleRequest('/v1/chat/completions').json;

        expect(body['provider_id'], 'provider-1');
        expect(body.containsKey('provider'), isFalse);

        expect(registryBody['id'], 'provider-1');
        expect(registryBody['name'], 'Test Provider');
        expect(registryBody['type'], 'openai');
        expect(registryBody['api_key'], 'sk-test');
        expect(
          registryBody['api_url'],
          'https://api.example.com/v1/chat/completions',
        );
        expect(registryBody['is_enabled'], true);
        expect(registryBody['created_at'], isA<String>());
        expect(registryBody['updated_at'], isA<String>());
        expect(registryBody['custom_headers'], <String, dynamic>{});
        expect(registryBody['description'], isNull);
        expect(registryBody['backend_mode'], 'auto');
        expect(registryBody['fallback_enabled'], false);
        expect(registryBody['fallback_timeout_ms'], 9000);
        expect(registryBody['circuit_breaker'], {
          'failure_threshold': 4,
          'window_ms': 120000,
          'open_ms': 45000,
          'half_open_max_calls': 3,
        });
      },
    );

    test(
      'ProxyOpenAIProvider retries model detection on /v1/models when /models returns 404',
      () async {
        final captureAdapter = _ModelsFallbackHttpClientAdapter();
        final dataDio = DioService().dataPlaneDio;
        final controlDio = DioService().controlPlaneDio;
        final originalDataAdapter = dataDio.httpClientAdapter;
        final originalControlAdapter = controlDio.httpClientAdapter;
        dataDio.httpClientAdapter = captureAdapter;
        controlDio.httpClientAdapter = captureAdapter;
        addTearDown(() {
          dataDio.httpClientAdapter = originalDataAdapter;
          controlDio.httpClientAdapter = originalControlAdapter;
        });

        final provider = ProxyOpenAIProvider(
          _buildProviderConfig(
            apiUrl: 'https://api.example.com/v1/chat/completions#',
            proxyApiUrl: 'https://proxy.example.test',
          ),
        );

        final models = await provider.listAvailableModels();

        expect(models, ['gpt-4o-mini']);
        expect(captureAdapter.requestCount('/models'), 1);
        expect(captureAdapter.requestCount('/v1/models'), 1);
      },
    );

    test(
      'ProxyOpenAIProvider isolates registry sync on control plane and chat on data plane',
      () async {
        final controlAdapter = _CaptureHttpClientAdapter();
        final dataAdapter = _CaptureHttpClientAdapter();
        final dataDio = DioService().dataPlaneDio;
        final controlDio = DioService().controlPlaneDio;
        final originalDataAdapter = dataDio.httpClientAdapter;
        final originalControlAdapter = controlDio.httpClientAdapter;
        dataDio.httpClientAdapter = dataAdapter;
        controlDio.httpClientAdapter = controlAdapter;
        addTearDown(() {
          dataDio.httpClientAdapter = originalDataAdapter;
          controlDio.httpClientAdapter = originalControlAdapter;
        });

        final provider = ProxyOpenAIProvider(
          _buildProviderConfig(
            apiUrl: 'https://api.example.com/v1/chat/completions#',
            proxyApiUrl: 'https://proxy.example.test',
          ),
        );

        await provider.sendMessage(
          model: 'gpt-4o-mini',
          messages: [ChatMessage(role: 'user', content: 'hello')],
          parameters: const ModelParameters(streamOutput: false),
          modelId: 'model-1',
        );

        expect(controlAdapter.requestCount('/api/providers/provider-1'), 1);
        expect(controlAdapter.requestCount('/v1/chat/completions'), 0);
        expect(dataAdapter.requestCount('/api/providers/provider-1'), 0);
        expect(dataAdapter.requestCount('/v1/chat/completions'), 1);
        expect(
          dataAdapter.singleRequest('/v1/chat/completions').json['model_id'],
          'model-1',
        );
      },
    );
  });
}

ProviderConfig _buildProviderConfig({
  required String apiUrl,
  String? proxyApiUrl,
  ProviderType type = ProviderType.openai,
  BackendMode backendMode = BackendMode.direct,
  bool fallbackEnabled = true,
  int fallbackTimeoutMs = 5000,
  CircuitBreakerConfig? circuitBreaker,
}) {
  return ProviderConfig(
    id: 'provider-1',
    name: 'Test Provider',
    type: type,
    apiUrl: apiUrl,
    apiKey: 'sk-test',
    proxyApiUrl: proxyApiUrl,
    backendMode: backendMode,
    fallbackEnabled: fallbackEnabled,
    fallbackTimeoutMs: fallbackTimeoutMs,
    circuitBreaker: circuitBreaker,
  );
}

class _CapturedRequest {
  final String path;
  final Map<String, dynamic> json;

  _CapturedRequest(this.path, this.json);
}

Map<String, dynamic> _providerSummaryResponse(Map<String, dynamic> decoded) {
  return {
    'id': decoded['id'] ?? 'provider-1',
    'name': decoded['name'] ?? 'Test Provider',
    'type': decoded['type'] ?? 'openai',
    'api_url':
        decoded['api_url'] ?? 'https://api.example.com/v1/chat/completions',
    'is_enabled': decoded['is_enabled'] ?? true,
    'created_at': decoded['created_at'] ?? '2026-04-08T00:00:00.000Z',
    'updated_at': decoded['updated_at'] ?? '2026-04-08T00:00:00.000Z',
    'custom_headers': decoded['custom_headers'] ?? <String, dynamic>{},
    'description': decoded['description'],
    if (decoded.containsKey('backend_mode'))
      'backend_mode': decoded['backend_mode'],
    if (decoded.containsKey('fallback_enabled'))
      'fallback_enabled': decoded['fallback_enabled'],
    if (decoded.containsKey('fallback_timeout_ms'))
      'fallback_timeout_ms': decoded['fallback_timeout_ms'],
    if (decoded.containsKey('circuit_breaker'))
      'circuit_breaker': decoded['circuit_breaker'],
  };
}

class _CaptureHttpClientAdapter implements HttpClientAdapter {
  final List<_CapturedRequest> _requests = [];

  _CapturedRequest singleRequest(String path) {
    final matches = _requests.where((request) => request.path == path).toList();
    expect(
      matches,
      hasLength(1),
      reason: 'Expected exactly one request for $path',
    );
    return matches.single;
  }

  int requestCount(String path) {
    return _requests.where((request) => request.path == path).length;
  }

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    final rawData = options.data;
    final decoded = rawData is Map
        ? Map<String, dynamic>.from(rawData)
        : <String, dynamic>{};

    _requests.add(_CapturedRequest(options.uri.path, decoded));

    if (options.uri.path == '/api/providers/provider-1') {
      return ResponseBody.fromString(
        jsonEncode(_providerSummaryResponse(decoded)),
        HttpStatus.ok,
        headers: {
          Headers.contentTypeHeader: ['application/json'],
        },
      );
    }

    final response = {
      'id': 'chatcmpl-test',
      'object': 'chat.completion',
      'created': 123,
      'model': decoded['model'] ?? 'test-model',
      'choices': [
        {
          'index': 0,
          'message': {'role': 'assistant', 'content': 'ok'},
          'finish_reason': 'stop',
        },
      ],
    };

    return ResponseBody.fromString(
      jsonEncode(response),
      HttpStatus.ok,
      headers: {
        Headers.contentTypeHeader: ['application/json'],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

class _ModelsFallbackHttpClientAdapter extends _CaptureHttpClientAdapter {
  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    final rawData = options.data;
    final decoded = rawData is Map
        ? Map<String, dynamic>.from(rawData)
        : <String, dynamic>{};

    _requests.add(_CapturedRequest(options.uri.path, decoded));

    if (options.uri.path == '/api/providers/provider-1') {
      return ResponseBody.fromString(
        jsonEncode(_providerSummaryResponse(decoded)),
        HttpStatus.ok,
        headers: {
          Headers.contentTypeHeader: ['application/json'],
        },
      );
    }

    if (options.uri.path == '/models') {
      return ResponseBody.fromString(
        jsonEncode({'error': 'not found'}),
        HttpStatus.notFound,
        headers: {
          Headers.contentTypeHeader: ['application/json'],
        },
      );
    }

    if (options.uri.path == '/v1/models') {
      return ResponseBody.fromString(
        jsonEncode({
          'object': 'list',
          'data': [
            {'id': 'gpt-4o-mini', 'object': 'model'},
          ],
        }),
        HttpStatus.ok,
        headers: {
          Headers.contentTypeHeader: ['application/json'],
        },
      );
    }

    return super.fetch(options, requestStream, cancelFuture);
  }
}

class _StreamingCaptureHttpClientAdapter extends _CaptureHttpClientAdapter {
  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    final rawData = options.data;
    final decoded = rawData is Map
        ? Map<String, dynamic>.from(rawData)
        : <String, dynamic>{};

    _requests.add(_CapturedRequest(options.uri.path, decoded));

    if (options.uri.path == '/api/providers/provider-1') {
      return ResponseBody.fromString(
        jsonEncode(_providerSummaryResponse(decoded)),
        HttpStatus.ok,
        headers: {
          Headers.contentTypeHeader: ['application/json'],
        },
      );
    }

    if (options.uri.path == '/v1/chat/completions' &&
        decoded['stream'] == true) {
      return ResponseBody.fromString(
        'data: {"type":"text_delta","delta":"ok"}\n\n'
        'data: {"type":"done"}\n\n',
        HttpStatus.ok,
        headers: {
          Headers.contentTypeHeader: ['text/event-stream'],
        },
      );
    }

    return super.fetch(options, requestStream, cancelFuture);
  }
}
