import 'dart:convert';

import 'package:flutter/material.dart';

import '../chat_ui/owui/owui_icons.dart';

/// API 错误信息类
class ApiError implements Exception {
  final int statusCode;
  final String message;
  final String? errorCode;
  final String? details;
  final dynamic rawResponse;
  final DateTime timestamp;

  ApiError({
    required this.statusCode,
    required this.message,
    this.errorCode,
    this.details,
    this.rawResponse,
    DateTime? timestamp,
  }) : timestamp = timestamp ?? DateTime.now();

  /// 获取错误标题
  String get title => 'API 请求失败 (HTTP $statusCode)';

  /// 获取人类可读的错误描述
  String get friendlyMessage {
    switch (statusCode) {
      case 400:
        return '请求参数错误：$message';
      case 401:
        return '认证失败：API Key 无效或已过期';
      case 403:
        return '禁止访问：没有权限访问此资源';
      case 404:
        return '资源不存在：请检查 API 地址和端口';
      case 429:
        return '请求过于频繁：已触发速率限制，请稍后重试';
      case 500:
        return 'AI 服务器错误：服务方遇到问题，请稍后重试';
      case 502:
        return '网关错误：服务临时不可用';
      case 503:
        return '服务不可用：服务器维护中';
      case 504:
        return '网关超时：请求处理超时';
      default:
        return message;
    }
  }

  /// 是否是客户端错误（4xx）
  bool get isClientError => statusCode >= 400 && statusCode < 500;

  /// 是否是服务器错误（5xx）
  bool get isServerError => statusCode >= 500 && statusCode < 600;

  /// 是否是认证错误
  bool get isAuthError => statusCode == 401 || statusCode == 403;

  /// 是否是速率限制
  bool get isRateLimited => statusCode == 429;

  /// 是否可重试
  bool get isRetryable =>
      statusCode == 429 ||
      statusCode == 500 ||
      statusCode == 502 ||
      statusCode == 503 ||
      statusCode == 504;

  /// 建议重试延迟（毫秒）
  int get retryDelayMs {
    if (statusCode == 429) return 5000; // 速率限制：5 秒后重试
    if (statusCode >= 500) return 3000; // 服务器错误：3 秒后重试
    return 1000; // 其他：1 秒后重试
  }

  /// 获取完整错误信息（用于调试）
  String get fullMessage {
    final buffer = StringBuffer();
    buffer.writeln('══ API 错误详情 ══');
    buffer.writeln('状态码: $statusCode');
    buffer.writeln('消息: $message');
    if (errorCode != null) buffer.writeln('错误代码: $errorCode');
    if (details != null) buffer.writeln('详情: $details');
    buffer.writeln('时间: $timestamp');
    if (rawResponse != null) buffer.writeln('原始响应: $rawResponse');
    return buffer.toString();
  }

  @override
  String toString() => 'ApiError($statusCode): $message';
}

/// HTTP 状态码
enum HttpStatusCode {
  ok(200),
  badRequest(400),
  unauthorized(401),
  forbidden(403),
  notFound(404),
  conflict(409),
  tooManyRequests(429),
  internalServerError(500),
  badGateway(502),
  serviceUnavailable(503),
  gatewayTimeout(504);

  final int code;
  const HttpStatusCode(this.code);
}

/// 状态码分类
enum HttpStatus {
  // 1xx - 信息
  continue_(100, '继续'),
  switchingProtocols(101, '正在切换协议'),

  // 2xx - 成功
  ok(200, '请求成功'),
  created(201, '资源已创建'),
  accepted(202, '请求已接受'),
  noContent(204, '无内容'),

  // 3xx - 重定向
  multipleChoices(300, '多个选择'),
  movePermanently(301, '永久移动'),
  found(302, '找到'),
  notModified(304, '未修改'),

  // 4xx - 客户端错误
  badRequest(400, '请求错误'),
  unauthorized(401, '未授权'),
  forbidden(403, '禁止访问'),
  notFound(404, '未找到'),
  methodNotAllowed(405, '方法不允许'),
  conflict(409, '冲突'),
  gone(410, '资源已删除'),
  unprocessableEntity(422, '无法处理的实体'),
  tooManyRequests(429, '请求过于频繁'),

  // 5xx - 服务器错误
  internalServerError(500, '服务器内部错误'),
  notImplemented(501, '未实现'),
  badGateway(502, '网关错误'),
  serviceUnavailable(503, '服务不可用'),
  gatewayTimeout(504, '网关超时');

  final int code;
  final String description;

  const HttpStatus(this.code, this.description);

  factory HttpStatus.fromCode(int code) {
    try {
      return HttpStatus.values.firstWhere((status) => status.code == code);
    } catch (_) {
      if (code >= 400 && code < 500) return HttpStatus.badRequest;
      if (code >= 500 && code < 600) return HttpStatus.internalServerError;
      return HttpStatus.ok;
    }
  }
}

/// 错误响应解析器
class ApiErrorParser {
  /// 从 HTTP 响应解析错误
  static ApiError parseFromResponse({
    required int statusCode,
    required String responseBody,
    String? apiProvider,
  }) {
    try {
      // 尝试解析 JSON 响应
      final json = _tryParseJson(responseBody);
      if (json != null) {
        return _parseJsonError(statusCode, json, responseBody);
      }
    } catch (_) {
      // JSON 解析失败，返回原始响应
    }

    return ApiError(
      statusCode: statusCode,
      message: responseBody.isNotEmpty
          ? responseBody
          : HttpStatus.fromCode(statusCode).description,
      rawResponse: responseBody,
    );
  }

  /// 解析 JSON 错误响应
  static ApiError _parseJsonError(
    int statusCode,
    Map<String, dynamic> json,
    String rawResponse,
  ) {
    // OpenAI 格式
    if (json.containsKey('error')) {
      final error = json['error'];
      if (error is Map<String, dynamic>) {
        return ApiError(
          statusCode: statusCode,
          message: error['message'] as String? ?? '未知错误',
          errorCode: error['code'] as String?,
          details: error['param'] as String?,
          rawResponse: rawResponse,
        );
      }
      return ApiError(
        statusCode: statusCode,
        message: error.toString(),
        rawResponse: rawResponse,
      );
    }

    // Claude 格式
    if (json.containsKey('message')) {
      return ApiError(
        statusCode: statusCode,
        message: json['message'] as String? ?? '未知错误',
        errorCode: json['type'] as String?,
        details: json['status'] as String?,
        rawResponse: rawResponse,
      );
    }

    // Gemini 格式
    if (json.containsKey('errors')) {
      final errors = json['errors'] as List?;
      if (errors != null && errors.isNotEmpty) {
        final firstError = errors[0];
        if (firstError is Map<String, dynamic>) {
          return ApiError(
            statusCode: statusCode,
            message: firstError['message'] as String? ?? '未知错误',
            errorCode: firstError['code'] as String?,
            rawResponse: rawResponse,
          );
        }
      }
    }

    // 通用格式
    final message = json['message'] as String? ??
        json['error_message'] as String? ??
        json['msg'] as String? ??
        '未知错误';

    return ApiError(
      statusCode: statusCode,
      message: message,
      errorCode: json['error_code'] as String? ?? json['code'] as String?,
      rawResponse: rawResponse,
    );
  }

  /// 尝试解析 JSON
  static Map<String, dynamic>? _tryParseJson(String text) {
    try {
      final decoded = jsonDecode(text);
      if (decoded is Map<String, dynamic>) {
        return decoded;
      }
    } catch (_) {
      return null;
    }
    return null;
  }
}

/// 错误展示组件
class ApiErrorWidget extends StatelessWidget {
  final ApiError error;
  final VoidCallback? onRetry;

  const ApiErrorWidget({
    super.key,
    required this.error,
    this.onRetry,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.all(16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.red.shade50,
        border: Border.all(color: Colors.red.shade200),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              const Icon(OwuiIcons.error, color: Colors.red),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  error.title,
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                    color: Colors.red,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            error.friendlyMessage,
            style: TextStyle(
              fontSize: 14,
              color: Colors.red.shade700,
              height: 1.5,
            ),
          ),
          if (error.errorCode != null) ...[
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: Colors.red.shade100,
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(
                '错误代码: ${error.errorCode}',
                style: TextStyle(
                  fontSize: 12,
                  color: Colors.red.shade600,
                  fontFamily: 'monospace',
                ),
              ),
            ),
          ],
          if (error.details != null) ...[
            const SizedBox(height: 8),
            Text(
              '详情: ${error.details}',
              style: TextStyle(
                fontSize: 12,
                color: Colors.red.shade600,
              ),
            ),
          ],
          const SizedBox(height: 12),
          Row(
            children: [
              if (onRetry != null && error.isRetryable)
                ElevatedButton.icon(
                  onPressed: onRetry,
                  icon: const Icon(OwuiIcons.refresh, size: 16),
                  label: const Text('重试'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.orange,
                    foregroundColor: Colors.white,
                  ),
                ),
              const SizedBox(width: 8),
              TextButton.icon(
                onPressed: () => _showDetails(context),
                icon: const Icon(OwuiIcons.info, size: 16),
                label: const Text('详情'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  void _showDetails(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('错误详情'),
        content: SingleChildScrollView(
          child: SelectableText(
            error.fullMessage,
            style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('关闭'),
          ),
        ],
      ),
    );
  }
}
