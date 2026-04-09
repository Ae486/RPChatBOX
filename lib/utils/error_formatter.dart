/// 错误格式化工具
/// 将各类错误转换为统一的 <error> 标签格式，用于持久化和 UI 渲染

/// 错误类型枚举
enum ErrorType {
  upstream,   // 上游 API 错误（有 HTTP 状态码）
  connection, // 连接错误
  timeout,    // 超时错误
  parse,      // 解析错误
  backend,    // 后端服务错误
  unknown,    // 未知错误
}

/// 错误信息结构
class ErrorInfo {
  final ErrorType type;
  final int? code;
  final String brief;
  final String details;

  const ErrorInfo({
    required this.type,
    this.code,
    required this.brief,
    required this.details,
  });

  /// 获取显示用的第一行文本（类型/状态码）
  String get firstLine {
    if (code != null) {
      return 'ERROR $code';
    }
    return switch (type) {
      ErrorType.upstream => 'API 错误',
      ErrorType.connection => '连接错误',
      ErrorType.timeout => '超时',
      ErrorType.parse => '解析错误',
      ErrorType.backend => '后端错误',
      ErrorType.unknown => '错误',
    };
  }

  /// 转换为 <error> 标签格式
  String toErrorTag() {
    final codeAttr = code != null ? ' code="$code"' : '';
    final escapedBrief = _escapeXml(brief);
    final escapedDetails = _escapeXml(details);
    return '<error type="${type.name}"$codeAttr brief="$escapedBrief">$escapedDetails</error>';
  }

  static String _escapeXml(String input) {
    return input
        .replaceAll('&', '&amp;')
        .replaceAll('"', '&quot;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;');
  }
}

/// 错误格式化器
class ErrorFormatter {
  static const String requestAbortedMessage = 'Request was aborted';

  /// 手动截断请求时使用的统一错误信息。
  static ErrorInfo requestAborted() => const ErrorInfo(
    type: ErrorType.unknown,
    brief: requestAbortedMessage,
    details: requestAbortedMessage,
  );

  /// 从异常解析错误信息
  static ErrorInfo parse(dynamic error) {
    if (error is ErrorInfo) {
      return error;
    }

    final errorStr = error.toString();

    // 尝试提取 HTTP 状态码
    final codeMatch = RegExp(r'status[_\s]?code[=:\s]*(\d{3})', caseSensitive: false)
        .firstMatch(errorStr);
    final code = codeMatch != null ? int.tryParse(codeMatch.group(1)!) : null;

    // 尝试提取错误类型
    final type = _detectErrorType(errorStr, code);

    // 提取简略信息
    final brief = _extractBrief(errorStr, type, code);

    return ErrorInfo(
      type: type,
      code: code,
      brief: brief,
      details: errorStr,
    );
  }

  /// 从 SSE 错误响应解析（格式：[type] message）
  static ErrorInfo parseFromSseError(String errorMessage) {
    // 格式: [RateLimitError] litellm.RateLimitError: status_code=429, message=...
    final typeMatch = RegExp(r'^\[(\w+)\]\s*').firstMatch(errorMessage);
    String typeStr = typeMatch?.group(1) ?? '';
    String message = typeMatch != null
        ? errorMessage.substring(typeMatch.end)
        : errorMessage;

    // 提取状态码
    final codeMatch = RegExp(r'status[_\s]?code[=:\s]*(\d{3})', caseSensitive: false)
        .firstMatch(message);
    final code = codeMatch != null ? int.tryParse(codeMatch.group(1)!) : null;

    // 映射错误类型
    final type = _mapErrorType(typeStr, code);

    // 提取简略信息
    final brief = _extractBriefFromMessage(message, code);

    return ErrorInfo(
      type: type,
      code: code,
      brief: brief,
      details: errorMessage,
    );
  }

  static ErrorType _detectErrorType(String errorStr, int? code) {
    final lower = errorStr.toLowerCase();

    if (lower.contains('timeout') || lower.contains('timed out')) {
      return ErrorType.timeout;
    }
    if (lower.contains('connection') ||
        lower.contains('connect failed') ||
        lower.contains('connection refused') ||
        lower.contains('无法连接')) {
      return ErrorType.connection;
    }
    if (lower.contains('parse') ||
        lower.contains('json') ||
        lower.contains('decode') ||
        lower.contains('format')) {
      return ErrorType.parse;
    }
    if (code != null) {
      return ErrorType.upstream;
    }
    return ErrorType.unknown;
  }

  static ErrorType _mapErrorType(String typeStr, int? code) {
    final lower = typeStr.toLowerCase();

    if (lower.contains('timeout')) return ErrorType.timeout;
    if (lower.contains('connection') || lower.contains('connect')) {
      return ErrorType.connection;
    }
    if (lower.contains('parse') || lower.contains('json')) {
      return ErrorType.parse;
    }
    if (code != null ||
        lower.contains('ratelimit') ||
        lower.contains('auth') ||
        lower.contains('badrequest') ||
        lower.contains('notfound') ||
        lower.contains('serviceunavailable')) {
      return ErrorType.upstream;
    }
    return ErrorType.unknown;
  }

  static String _extractBrief(String errorStr, ErrorType type, int? code) {
    // 尝试提取 message= 后的内容
    final msgMatch = RegExp(r'message[=:]\s*["\x27]?([^"\x27}\n]+)', caseSensitive: false)
        .firstMatch(errorStr);
    if (msgMatch != null) {
      return _truncate(msgMatch.group(1)!.trim(), 50);
    }

    // 根据类型返回默认信息
    return switch (type) {
      ErrorType.timeout => '请求超时',
      ErrorType.connection => '无法连接到服务',
      ErrorType.parse => '数据解析失败',
      ErrorType.upstream => code != null ? _getHttpStatusMessage(code) : '请求失败',
      ErrorType.backend => '后端服务异常',
      ErrorType.unknown => '发生未知错误',
    };
  }

  static String _extractBriefFromMessage(String message, int? code) {
    // 尝试提取 message= 后的内容
    final msgMatch = RegExp(r'message[=:]\s*["\x27]?([^"\x27}\n]+)', caseSensitive: false)
        .firstMatch(message);
    if (msgMatch != null) {
      return _truncate(msgMatch.group(1)!.trim(), 50);
    }

    // 尝试提取冒号后的主要内容
    final colonIdx = message.indexOf(':');
    if (colonIdx > 0 && colonIdx < message.length - 1) {
      final afterColon = message.substring(colonIdx + 1).trim();
      // 去除 litellm. 前缀等
      final cleaned = afterColon.replaceFirst(RegExp(r'^litellm\.\w+:\s*'), '');
      return _truncate(cleaned, 50);
    }

    return _truncate(message, 50);
  }

  static String _truncate(String text, int maxLength) {
    if (text.length <= maxLength) return text;
    return '${text.substring(0, maxLength - 3)}...';
  }

  static String _getHttpStatusMessage(int code) {
    return switch (code) {
      400 => 'Bad Request',
      401 => 'Unauthorized',
      403 => 'Forbidden',
      404 => 'Not Found',
      429 => 'Rate Limit Exceeded',
      500 => 'Internal Server Error',
      502 => 'Bad Gateway',
      503 => 'Service Unavailable',
      504 => 'Gateway Timeout',
      _ => 'HTTP Error',
    };
  }
}

/// 从消息内容中提取 <error> 标签
class ErrorTagParser {
  static final _errorTagRegex = RegExp(
    r'<error\s+type="(\w+)"(?:\s+code="(\d+)")?(?:\s+brief="([^"]*)")?>([^<]*)</error>',
    dotAll: true,
  );

  /// 检测消息是否包含错误标签
  static bool hasErrorTag(String content) {
    return _errorTagRegex.hasMatch(content);
  }

  /// 提取错误信息（如果存在）
  static ErrorInfo? extractError(String content) {
    final match = _errorTagRegex.firstMatch(content);
    if (match == null) return null;

    final typeStr = match.group(1)!;
    final codeStr = match.group(2);
    final brief = _unescapeXml(match.group(3) ?? '');
    final details = _unescapeXml(match.group(4) ?? '');

    final type = ErrorType.values.firstWhere(
      (e) => e.name == typeStr,
      orElse: () => ErrorType.unknown,
    );

    return ErrorInfo(
      type: type,
      code: codeStr != null ? int.tryParse(codeStr) : null,
      brief: brief.isNotEmpty ? brief : _extractBriefFromDetails(details),
      details: details,
    );
  }

  /// 移除错误标签，返回纯内容
  static String removeErrorTag(String content) {
    return content.replaceAll(_errorTagRegex, '').trim();
  }

  static String _unescapeXml(String input) {
    return input
        .replaceAll('&quot;', '"')
        .replaceAll('&lt;', '<')
        .replaceAll('&gt;', '>')
        .replaceAll('&amp;', '&');
  }

  static String _extractBriefFromDetails(String details) {
    if (details.length <= 50) return details;
    return '${details.substring(0, 47)}...';
  }
}
