/// 项目级 Provider 测试工具
/// 使用项目的 SseParser + ThinkingExtractor 进行测试
///
/// 用法: dart run tools/project_provider_test.dart [options]

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';

// 导入项目的 SSE 解析模块
import '../lib/adapters/sse/sse_parser.dart';
import '../lib/adapters/sse/thinking_extractor.dart';
import '../lib/adapters/sse/gemini_parser.dart';

void main(List<String> args) async {
  final config = _parseArgs(args);

  if (config['help'] == true) {
    _printHelp();
    exit(0);
  }

  final apiKey = config['apiKey'] ?? Platform.environment['OPENAI_API_KEY'];
  final baseUrl = config['baseUrl'] ??
      Platform.environment['OPENAI_BASE_URL'] ??
      'https://api.openai.com/v1';
  final model = config['model'] ?? 'gpt-4o-mini';
  final message = config['message'] ?? 'Say "test ok" in 3 words or less';
  final stream = config['stream'] ?? true; // 默认流式
  final timeout = int.tryParse(config['timeout']?.toString() ?? '60') ?? 60;
  final isGemini = model.toLowerCase().contains('gemini');

  if (apiKey == null || apiKey.isEmpty) {
    _outputJson({
      'success': false,
      'error': 'API Key 未设置',
    });
    exit(1);
  }

  final result = <String, dynamic>{
    'timestamp': DateTime.now().toIso8601String(),
    'config': {
      'baseUrl': baseUrl,
      'model': model,
      'stream': stream,
      'isGemini': isGemini,
    },
  };

  final dio = Dio(BaseOptions(
    connectTimeout: Duration(seconds: timeout),
    receiveTimeout: Duration(seconds: timeout * 2),
  ));

  final stopwatch = Stopwatch()..start();

  try {
    final url = '$baseUrl/chat/completions';
    final headers = {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer $apiKey',
    };

    final body = {
      'model': model,
      'messages': [
        {'role': 'user', 'content': message}
      ],
      'stream': stream,
      'max_tokens': 500,
      'include_reasoning': true, // 启用 reasoning
    };

    // Gemini 特殊参数
    if (isGemini) {
      body['extra_body'] = {
        'google': {
          'thinking_config': {'include_thoughts': true},
        },
      };
    }

    result['request'] = {
      'url': url,
      'model': model,
      'message': message,
    };

    if (stream) {
      // ========== 使用项目的 SSE 解析模块 ==========
      final response = await dio.post(
        url,
        data: body,
        options: Options(
          headers: headers,
          responseType: ResponseType.stream,
        ),
      );

      final responseStream = (response.data as ResponseBody).stream;

      // 使用项目的 SseParser
      final sseStream = SseParser.parse(responseStream.cast<List<int>>());

      // 使用项目的解析器
      final thinkingExtractor = ThinkingExtractor();
      final geminiParser = GeminiParser();

      final allChunks = <String>[];
      final thinkingChunks = <String>[];
      final contentChunks = <String>[];
      var hasThinking = false;
      var hasContent = false;

      await for (final event in sseStream) {
        switch (event) {
          case SseDataEvent(:final data):
            // 处理 choices 格式 (OpenAI/DeepSeek)
            final choices = data['choices'] as List?;
            if (choices != null && choices.isNotEmpty) {
              final choice = choices[0] as Map<String, dynamic>;
              final delta = choice['delta'] as Map<String, dynamic>?;
              if (delta != null) {
                for (final chunk in thinkingExtractor.extract(delta)) {
                  allChunks.add(chunk);
                  if (chunk == '<think>') {
                    hasThinking = true;
                  } else if (chunk == '</think>') {
                    // skip
                  } else if (hasThinking && !chunk.startsWith('</')) {
                    thinkingChunks.add(chunk);
                  } else {
                    contentChunks.add(chunk);
                    hasContent = true;
                  }
                }
              }
            }

            // 处理 candidates 格式 (Gemini)
            final candidates = data['candidates'] as List?;
            if (candidates != null && candidates.isNotEmpty) {
              for (final chunk
                  in geminiParser.extractFromCandidates(candidates, isGemini: isGemini)) {
                allChunks.add(chunk);
                if (chunk == '<think>') {
                  hasThinking = true;
                } else if (chunk == '</think>') {
                  hasThinking = false;
                } else if (hasThinking) {
                  thinkingChunks.add(chunk);
                } else {
                  contentChunks.add(chunk);
                }
              }
            }

          case SseErrorEvent(:final type, :final message, :final code):
            throw Exception('[$type] $message (code: $code)');

          case SseDoneEvent():
            break;
        }
      }

      // 关闭标签
      final thinkingClosing = thinkingExtractor.getClosingTag();
      if (thinkingClosing != null) allChunks.add(thinkingClosing);

      final geminiClosing = geminiParser.getClosingTag();
      if (geminiClosing != null) allChunks.add(geminiClosing);

      stopwatch.stop();

      final fullOutput = allChunks.join('');
      final thinkingContent = thinkingChunks.join('');
      final normalContent = contentChunks.join('');

      result['response'] = {
        'success': true,
        'stream': true,
        'parser': 'PROJECT_SSE_PARSER',
        'chunkCount': allChunks.length,
        'hasThinkingTags': fullOutput.contains('<think>'),
        'thinkingLength': thinkingContent.length,
        'contentLength': normalContent.length,
        'thinking': thinkingContent.length > 200
            ? '${thinkingContent.substring(0, 200)}...(${thinkingContent.length} chars)'
            : thinkingContent,
        'content': normalContent.length > 500
            ? '${normalContent.substring(0, 500)}...(${normalContent.length} chars)'
            : normalContent,
        'fullOutput': fullOutput.length > 1000
            ? '${fullOutput.substring(0, 1000)}...(${fullOutput.length} chars)'
            : fullOutput,
        'latencyMs': stopwatch.elapsedMilliseconds,
      };
    } else {
      // 非流式
      final response = await dio.post(
        url,
        data: body,
        options: Options(headers: headers),
      );

      stopwatch.stop();

      if (response.statusCode == 200) {
        final data = response.data as Map<String, dynamic>;
        final choices = data['choices'] as List?;
        final content = choices?.isNotEmpty == true
            ? (choices![0]['message']?['content'] as String? ?? '')
            : '';

        result['response'] = {
          'success': true,
          'stream': false,
          'content': content,
          'latencyMs': stopwatch.elapsedMilliseconds,
          'usage': data['usage'],
        };
      } else {
        result['response'] = {
          'success': false,
          'statusCode': response.statusCode,
          'body': response.data.toString(),
        };
      }
    }
  } on DioException catch (e) {
    stopwatch.stop();

    // 尝试读取响应体
    String? responseBody;
    try {
      if (e.response?.data is ResponseBody) {
        final stream = (e.response!.data as ResponseBody).stream;
        final bytes = await stream.fold<List<int>>(
          [],
          (prev, chunk) => prev..addAll(chunk),
        );
        responseBody = utf8.decode(bytes);
      } else if (e.response?.data != null) {
        responseBody = e.response!.data.toString();
      }
    } catch (_) {
      responseBody = e.response?.data?.toString();
    }

    // 尝试解析 JSON 错误
    Map<String, dynamic>? parsedError;
    try {
      if (responseBody != null) {
        final json = jsonDecode(responseBody);
        if (json is Map<String, dynamic>) {
          parsedError = json['error'] as Map<String, dynamic>?;
        }
      }
    } catch (_) {}

    result['response'] = {
      'success': false,
      'error': 'DioException',
      'type': e.type.toString(),
      'statusCode': e.response?.statusCode,
      'upstreamError': parsedError,
      'responseBody': responseBody,
      'dioMessage': e.message,
      'latencyMs': stopwatch.elapsedMilliseconds,
    };
  } catch (e, st) {
    stopwatch.stop();
    result['response'] = {
      'success': false,
      'error': 'Exception',
      'message': e.toString(),
      'stackTrace': st.toString().split('\n').take(5).join('\n'),
      'latencyMs': stopwatch.elapsedMilliseconds,
    };
  }

  _outputJson(result);
}

void _outputJson(Map<String, dynamic> data) {
  print(const JsonEncoder.withIndent('  ').convert(data));
}

Map<String, dynamic> _parseArgs(List<String> args) {
  final result = <String, dynamic>{};

  for (var i = 0; i < args.length; i++) {
    final arg = args[i];
    switch (arg) {
      case '-h':
      case '--help':
        result['help'] = true;
        break;
      case '-k':
      case '--api-key':
        if (i + 1 < args.length) result['apiKey'] = args[++i];
        break;
      case '-u':
      case '--base-url':
        if (i + 1 < args.length) result['baseUrl'] = args[++i];
        break;
      case '-m':
      case '--model':
        if (i + 1 < args.length) result['model'] = args[++i];
        break;
      case '--message':
        if (i + 1 < args.length) result['message'] = args[++i];
        break;
      case '-s':
      case '--stream':
        result['stream'] = true;
        break;
      case '--no-stream':
        result['stream'] = false;
        break;
      case '-t':
      case '--timeout':
        if (i + 1 < args.length) result['timeout'] = args[++i];
        break;
    }
  }

  return result;
}

void _printHelp() {
  print('''
项目级 Provider 测试工具 (使用项目 SSE 解析模块)

用法: dart run tools/project_provider_test.dart [options]

选项:
  -h, --help          显示帮助
  -k, --api-key KEY   API Key
  -u, --base-url URL  API Base URL
  -m, --model NAME    模型名称
  --message TEXT      测试消息
  -s, --stream        流式模式 (默认)
  --no-stream         非流式模式
  -t, --timeout SEC   超时时间秒 (默认: 60)

验证项:
  - SseParser 正确解析 SSE 流
  - ThinkingExtractor 正确提取 reasoning/thinking 内容
  - GeminiParser 正确处理 candidates 格式
  - <think> 标签正确注入
''');
}
