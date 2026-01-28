/// Provider 错误映射器
///
/// 将各种 LangChain 和 Provider 异常统一转换为 ApiError
class ProviderErrorMapper {
  const ProviderErrorMapper._();

  /// 将任意错误转换为 ApiError
  ///
  /// [error] - 原始错误
  /// [providerName] - Provider 名称（用于错误消息）
  static ApiError toApiError(Object error, {String? providerName}) {
    final provider = providerName ?? 'Provider';

    // 处理已知的错误类型
    final errorString = error.toString().toLowerCase();
    final errorMessage = error.toString();

    // 认证错误
    if (_isAuthenticationError(errorString)) {
      return ApiError(
        message: '$provider: API 密钥无效或已过期',
        statusCode: 401,
        originalError: error,
      );
    }

    // 速率限制
    if (_isRateLimitError(errorString)) {
      return ApiError(
        message: '$provider: 请求过于频繁，请稍后重试',
        statusCode: 429,
        originalError: error,
      );
    }

    // 配额超限
    if (_isQuotaError(errorString)) {
      return ApiError(
        message: '$provider: API 配额已用尽',
        statusCode: 402,
        originalError: error,
      );
    }

    // 模型不可用
    if (_isModelNotFoundError(errorString)) {
      return ApiError(
        message: '$provider: 指定的模型不可用',
        statusCode: 404,
        originalError: error,
      );
    }

    // 内容过滤
    if (_isContentFilterError(errorString)) {
      return ApiError(
        message: '$provider: 内容被安全过滤器拦截',
        statusCode: 400,
        originalError: error,
      );
    }

    // 上下文长度超限
    if (_isContextLengthError(errorString)) {
      return ApiError(
        message: '$provider: 消息过长，超出模型上下文限制',
        statusCode: 400,
        originalError: error,
      );
    }

    // 网络错误
    if (_isNetworkError(errorString)) {
      return ApiError(
        message: '$provider: 网络连接失败，请检查网络设置',
        statusCode: 503,
        originalError: error,
      );
    }

    // 超时
    if (_isTimeoutError(errorString)) {
      return ApiError(
        message: '$provider: 请求超时，请稍后重试',
        statusCode: 504,
        originalError: error,
      );
    }

    // 服务器错误
    if (_isServerError(errorString)) {
      return ApiError(
        message: '$provider: 服务暂时不可用',
        statusCode: 500,
        originalError: error,
      );
    }

    // 解析错误
    if (_isParseError(errorString)) {
      return ApiError(
        message: '$provider: 响应解析失败',
        statusCode: 422,
        originalError: error,
      );
    }

    // 默认：未知错误
    return ApiError(
      message: '$provider: $errorMessage',
      statusCode: 500,
      originalError: error,
    );
  }

  // ===== 错误类型检测 =====

  static bool _isAuthenticationError(String error) {
    return error.contains('unauthorized') ||
        error.contains('invalid api key') ||
        error.contains('invalid_api_key') ||
        error.contains('authentication') ||
        error.contains('401') ||
        error.contains('api key') && error.contains('invalid');
  }

  static bool _isRateLimitError(String error) {
    return error.contains('rate limit') ||
        error.contains('rate_limit') ||
        error.contains('too many requests') ||
        error.contains('429');
  }

  static bool _isQuotaError(String error) {
    return error.contains('quota') ||
        error.contains('insufficient_quota') ||
        error.contains('billing') ||
        error.contains('payment required');
  }

  static bool _isModelNotFoundError(String error) {
    return error.contains('model not found') ||
        error.contains('model_not_found') ||
        error.contains('does not exist') ||
        error.contains('unknown model');
  }

  static bool _isContentFilterError(String error) {
    return error.contains('content filter') ||
        error.contains('content_filter') ||
        error.contains('safety') ||
        error.contains('blocked') ||
        error.contains('harmful');
  }

  static bool _isContextLengthError(String error) {
    return error.contains('context length') ||
        error.contains('context_length') ||
        error.contains('maximum context') ||
        error.contains('token limit') ||
        error.contains('too long');
  }

  static bool _isNetworkError(String error) {
    return error.contains('socketexception') ||
        error.contains('connection refused') ||
        error.contains('connection failed') ||
        error.contains('network') ||
        error.contains('dns');
  }

  static bool _isTimeoutError(String error) {
    return error.contains('timeout') ||
        error.contains('timed out') ||
        error.contains('timeoutexception');
  }

  static bool _isServerError(String error) {
    return error.contains('500') ||
        error.contains('502') ||
        error.contains('503') ||
        error.contains('internal server error') ||
        error.contains('service unavailable');
  }

  static bool _isParseError(String error) {
    return error.contains('parse') ||
        error.contains('json') ||
        error.contains('format') ||
        error.contains('unexpected');
  }
}

/// 统一的 API 错误类型
class ApiError implements Exception {
  /// 用户友好的错误消息
  final String message;

  /// HTTP 状态码（或等效错误码）
  final int statusCode;

  /// 原始错误对象（用于调试）
  final Object? originalError;

  ApiError({
    required this.message,
    required this.statusCode,
    this.originalError,
  });

  @override
  String toString() => 'ApiError($statusCode): $message';

  /// 是否为可重试的错误
  bool get isRetryable {
    return statusCode == 429 || // 速率限制
        statusCode == 503 || // 服务不可用
        statusCode == 504; // 超时
  }

  /// 是否为认证错误
  bool get isAuthError => statusCode == 401 || statusCode == 403;

  /// 是否为客户端错误
  bool get isClientError => statusCode >= 400 && statusCode < 500;

  /// 是否为服务器错误
  bool get isServerError => statusCode >= 500;
}
