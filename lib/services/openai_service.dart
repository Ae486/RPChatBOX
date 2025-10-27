import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/chat_settings.dart';
import '../models/message.dart';

/// OpenAI API 服务类
class OpenAIService {
  final ChatSettings settings;

  OpenAIService(this.settings);

  /// 发送消息并获取流式响应
  /// 返回一个 Stream，实时输出 AI 的回复内容
  Stream<String> sendMessage(List<Message> messages) async* {
    try {
      // 构建请求体
      final requestBody = {
        'model': settings.model,
        'messages': messages.map((msg) {
          return {
            'role': msg.isUser ? 'user' : 'assistant',
            'content': msg.content,
          };
        }).toList(),
        'temperature': settings.temperature,
        'top_p': settings.topP,
        'max_tokens': settings.maxTokens,
        'stream': true, // 启用流式响应
      };

      // 发送 POST 请求
      final request = http.Request('POST', Uri.parse(settings.apiUrl));
      request.headers.addAll({
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ${settings.apiKey}',
      });
      request.body = json.encode(requestBody);

      // 获取流式响应
      final streamedResponse = await request.send();

      if (streamedResponse.statusCode != 200) {
        final errorBody = await streamedResponse.stream.bytesToString();
        throw Exception('API 请求失败: ${streamedResponse.statusCode}\n$errorBody');
      }

      // 逐行读取 SSE (Server-Sent Events) 数据
      await for (var chunk in streamedResponse.stream.transform(utf8.decoder).transform(const LineSplitter())) {
        if (chunk.isEmpty) continue;
        
        // SSE 格式: "data: {json}"
        if (chunk.startsWith('data: ')) {
          final data = chunk.substring(6);
          
          // 流结束标记
          if (data == '[DONE]') {
            break;
          }

          try {
            final jsonData = json.decode(data);
            final content = jsonData['choices']?[0]?['delta']?['content'];
            
            if (content != null && content is String) {
              yield content;
            }
          } catch (e) {
            // 忽略解析错误的块
            continue;
          }
        }
      }
    } catch (e) {
      yield '\n\n❌ 错误: $e';
    }
  }

  /// 测试 API 连接
  Future<bool> testConnection() async {
    try {
      final testMessage = Message(
        id: 'test',
        content: 'Hi',
        isUser: true,
        timestamp: DateTime.now(),
      );

      await for (var _ in sendMessage([testMessage])) {
        // 只要能收到第一个响应就算成功
        return true;
      }
      return false;
    } catch (e) {
      return false;
    }
  }
}

