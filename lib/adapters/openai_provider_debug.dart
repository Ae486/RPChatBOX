/// INPUT: API 调试信息
/// OUTPUT: 调试日志输出方法
/// POS: Adapters / OpenAI Provider - 调试方法 Part

part of 'openai_provider.dart';

/// OpenAI Provider 调试方法扩展
extension OpenAIProviderDebug on OpenAIProvider {
  /// 调试方法：打印请求内容
  void debugPrintRequest(String url, Map<String, dynamic> requestBody) {
    // 仅在调试模式启用详细日志
    if (!kDebugMode) return;

    debugPrint('\n╔═══════════════════════════════════════════════════════════════');
    debugPrint('║ 🐛 API 请求调试信息');
    debugPrint('╠═══════════════════════════════════════════════════════════════');
    debugPrint('║ 📍 API 地址: $url');
    debugPrint('║ 🏢 Provider: ${config.name} (${config.type.toString().split('.').last})');
    debugPrint('║ 🔑 API Key: ${config.apiKey.substring(0, math.min(10, config.apiKey.length))}...****');
    debugPrint('╠═══════════════════════════════════════════════════════════════');
    debugPrint('║ 📤 完整请求体:');
    debugPrint('║');

    // 格式化输出JSON（截断过长的messages）
    final displayBody = Map<String, dynamic>.from(requestBody);
    if (displayBody.containsKey('messages')) {
      final messages = displayBody['messages'] as List?;
      if (messages != null && messages.length > 3) {
        // 只显示前2条和最后1条消息
        final summary = [
          messages[0],
          messages[1],
          {'role': '...', 'content': '(${messages.length - 3}条消息已隐藏)'},
          messages.last,
        ];
        displayBody['messages'] = summary;
      }
    }

    final prettyJson = const JsonEncoder.withIndent('  ').convert(displayBody);
    for (var line in prettyJson.split('\n')) {
      debugPrint('║   $line');
    }

    debugPrint('║');
    debugPrint('╠══════════════════════════════════════════════════════════════╗');
    debugPrint('║ 📊 参数摘要:');
    debugPrint('║   • 模型: ${requestBody['model']}');
    debugPrint('║   • 流式模式: ${requestBody['stream']}');
    if (requestBody.containsKey('temperature')) {
      debugPrint('║   • Temperature: ${requestBody['temperature']}');
    }
    if (requestBody.containsKey('max_tokens')) {
      debugPrint('║   • Max Tokens: ${requestBody['max_tokens']}');
    }
    if (requestBody.containsKey('top_p')) {
      debugPrint('║   • Top P: ${requestBody['top_p']}');
    }
    if (requestBody.containsKey('frequency_penalty')) {
      debugPrint('║   • Frequency Penalty: ${requestBody['frequency_penalty']}');
    }
    if (requestBody.containsKey('presence_penalty')) {
      debugPrint('║   • Presence Penalty: ${requestBody['presence_penalty']}');
    }
    final messages = requestBody['messages'] as List?;
    if (messages != null) {
      debugPrint('║   • 消息数: ${messages.length}');
    }
    debugPrint('╚══════════════════════════════════════════════════════════════╗\n');
  }

  /// 调试方法：打印错误信息
  void debugPrintError(ApiError error) {
    if (!kDebugMode) return;

    debugPrint('\n╔══════════════════════════════════════════════════════════════╗');
    debugPrint('║ ${error.title}');
    debugPrint('╠══════════════════════════════════════════════════════════════╗');
    debugPrint('║ 🔴 状态码: ${error.statusCode}');
    debugPrint('║ 📝 消息: ${error.message}');
    if (error.errorCode != null) {
      debugPrint('║ 🎯 错误代码: ${error.errorCode}');
    }
    if (error.details != null) {
      debugPrint('║ ℹ️ 详情: ${error.details}');
    }
    debugPrint('║ 🕒 时间: ${error.timestamp}');
    debugPrint('║ ♾️ 可重试: ${error.isRetryable}');
    if (error.isRetryable) {
      debugPrint('║ ✇️ 建议延迟: ${error.retryDelayMs}ms');
    }
    debugPrint('╚══════════════════════════════════════════════════════════════╗\n');
  }
}

/// 静态辅助方法
extension OpenAIProviderHelpers on OpenAIProvider {
  /// 判断类型是否为思考/推理类型
  static bool isReasoningType(String type) {
    final lower = type.toLowerCase();
    return lower.contains('reason') || lower.contains('think') || lower.contains('thought');
  }

  /// 从不同格式中提取文本
  static String? extractText(dynamic v) {
    if (v is String) return v;
    if (v is Map<String, dynamic>) return (v['content'] ?? v['text']) as String?;
    if (v is List) {
      return v.map((e) {
        if (e is String) return e;
        if (e is Map<String, dynamic>) return (e['content'] ?? e['text'] ?? '').toString();
        return '';
      }).where((s) => s.isNotEmpty).join('');
    }
    return null;
  }
}
