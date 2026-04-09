/// Provider 自动化测试工具
/// 用法: dart run tools/provider_tester.dart [options]
///
/// 环境变量:
///   OPENAI_API_KEY - OpenAI API Key
///   OPENAI_BASE_URL - API Base URL (默认: https://api.openai.com/v1)
///
/// 示例:
///   dart run tools/provider_tester.dart --model gpt-4o-mini --message "Hello"
///   dart run tools/provider_tester.dart --model deepseek-chat --stream --message "1+1=?"

import 'dart:convert';
import 'dart:io';

// 手动导入必要的依赖（避免 Flutter 依赖）
import 'package:dio/dio.dart';

void main(List<String> args) async {
  final config = _parseArgs(args);

  if (config['help'] == true) {
    _printHelp();
    exit(0);
  }

  final apiKey = config['apiKey'] ?? Platform.environment['OPENAI_API_KEY'];
  final baseUrl = config['baseUrl'] ?? Platform.environment['OPENAI_BASE_URL'] ?? 'https://api.openai.com/v1';
  final model = config['model'] ?? 'gpt-4o-mini';
  final message = config['message'] ?? 'Say "test ok" in 3 words or less';
  final stream = config['stream'] ?? false;
  final timeout = int.tryParse(config['timeout']?.toString() ?? '30') ?? 30;

  if (apiKey == null || apiKey.isEmpty) {
    _outputError('API Key 未设置。请设置 OPENAI_API_KEY 环境变量或使用 --api-key 参数');
    exit(1);
  }

  final result = <String, dynamic>{
    'timestamp': DateTime.now().toIso8601String(),
    'config': {
      'baseUrl': baseUrl,
      'model': model,
      'stream': stream,
      'timeout': timeout,
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
      'max_tokens': 100,
    };

    result['request'] = {
      'url': url,
      'model': model,
      'message': message,
    };

    if (stream) {
      // 流式请求
      final response = await dio.post(
        url,
        data: body,
        options: Options(
          headers: headers,
          responseType: ResponseType.stream,
        ),
      );

      final chunks = <String>[];
      final buffer = StringBuffer();

      await for (final chunk in (response.data as ResponseBody).stream) {
        final text = utf8.decode(chunk);
        for (final line in text.split('\n')) {
          final trimmed = line.trim();
          if (trimmed.isEmpty) continue;
          if (!trimmed.startsWith('data: ')) continue;

          final data = trimmed.substring(6);
          if (data == '[DONE]') break;

          try {
            final json = jsonDecode(data) as Map<String, dynamic>;

            // 检查错误
            final error = json['error'] as Map<String, dynamic>?;
            if (error != null) {
              throw Exception('[${error['type']}] ${error['message']}');
            }

            final choices = json['choices'] as List?;
            if (choices != null && choices.isNotEmpty) {
              final delta = choices[0]['delta'] as Map<String, dynamic>?;
              if (delta != null) {
                // 提取 thinking 内容
                for (final key in ['reasoning', 'reasoning_content', 'thinking']) {
                  final v = delta[key];
                  if (v is String && v.isNotEmpty) {
                    chunks.add('<think>$v</think>');
                    buffer.write(v);
                  }
                }
                // 提取正常内容
                final content = delta['content'];
                if (content is String && content.isNotEmpty) {
                  chunks.add(content);
                  buffer.write(content);
                }
              }
            }
          } catch (e) {
            if (e.toString().contains('[')) rethrow;
            // 忽略 JSON 解析错误
          }
        }
      }

      stopwatch.stop();

      result['response'] = {
        'success': true,
        'stream': true,
        'chunkCount': chunks.length,
        'content': buffer.toString(),
        'latencyMs': stopwatch.elapsedMilliseconds,
      };
    } else {
      // 非流式请求
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
          'latencyMs': stopwatch.elapsedMilliseconds,
        };
      }
    }
  } on DioException catch (e) {
    stopwatch.stop();
    result['response'] = {
      'success': false,
      'error': 'DioException',
      'type': e.type.toString(),
      'message': e.message,
      'statusCode': e.response?.statusCode,
      'responseBody': e.response?.data?.toString(),
      'latencyMs': stopwatch.elapsedMilliseconds,
    };
  } catch (e) {
    stopwatch.stop();
    result['response'] = {
      'success': false,
      'error': 'Exception',
      'message': e.toString(),
      'latencyMs': stopwatch.elapsedMilliseconds,
    };
  }

  // 输出 JSON 结果
  print(const JsonEncoder.withIndent('  ').convert(result));
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
Provider 自动化测试工具

用法: dart run tools/provider_tester.dart [options]

选项:
  -h, --help          显示帮助
  -k, --api-key KEY   API Key (或设置 OPENAI_API_KEY 环境变量)
  -u, --base-url URL  API Base URL (默认: https://api.openai.com/v1)
  -m, --model NAME    模型名称 (默认: gpt-4o-mini)
  --message TEXT      测试消息 (默认: "Say test ok in 3 words or less")
  -s, --stream        使用流式模式
  -t, --timeout SEC   超时时间秒 (默认: 30)

环境变量:
  OPENAI_API_KEY      API Key
  OPENAI_BASE_URL     API Base URL

示例:
  # 基本测试
  dart run tools/provider_tester.dart --model gpt-4o-mini

  # 流式测试
  dart run tools/provider_tester.dart --model gpt-4o-mini --stream

  # 测试 DeepSeek
  dart run tools/provider_tester.dart \\
    --base-url https://api.deepseek.com/v1 \\
    --model deepseek-chat \\
    --stream

  # 测试 thinking 模型
  dart run tools/provider_tester.dart \\
    --model deepseek-reasoner \\
    --stream \\
    --message "What is 15 * 23?"
''');
}

void _outputError(String message) {
  print(jsonEncode({
    'timestamp': DateTime.now().toIso8601String(),
    'response': {
      'success': false,
      'error': 'ConfigError',
      'message': message,
    },
  }));
}
