import 'package:dio/dio.dart';

/// Policy for determining when to fallback from proxy to direct connection.
class FallbackPolicy {
  /// Determine if an error should trigger fallback to direct connection.
  ///
  /// [error] - The error that occurred
  /// [hasEmittedChunk] - Whether any response chunks have been emitted
  ///
  /// Returns true if fallback should be attempted.
  static bool shouldFallback(Object error, bool hasEmittedChunk) {
    // Rule FB-3: Never fallback after chunks have been emitted
    // This prevents duplicate/inconsistent responses
    if (hasEmittedChunk) {
      return false;
    }

    if (error is DioException) {
      return _shouldFallbackDioError(error);
    }

    // For unknown errors, don't fallback
    return false;
  }

  static bool _shouldFallbackDioError(DioException error) {
    // Network errors: Fallback (FB-1)
    switch (error.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
      case DioExceptionType.connectionError:
        return true;

      case DioExceptionType.badResponse:
        return _shouldFallbackStatusCode(error.response?.statusCode);

      case DioExceptionType.cancel:
        // User cancelled, don't fallback
        return false;

      case DioExceptionType.badCertificate:
      case DioExceptionType.unknown:
        // Certificate or unknown errors might be recoverable
        return true;
    }
  }

  static bool _shouldFallbackStatusCode(int? statusCode) {
    if (statusCode == null) return true;

    // Server errors: Fallback (FB-1)
    if (statusCode == 502 || statusCode == 503 || statusCode == 504) {
      return true;
    }

    // Auth errors: Don't fallback (FB-2)
    if (statusCode == 401 || statusCode == 403) {
      return false;
    }

    // Client errors: Don't fallback (FB-2)
    if (statusCode == 400 || statusCode == 404 || statusCode == 422) {
      return false;
    }

    // Rate limit: Don't fallback (user should wait)
    if (statusCode == 429) {
      return false;
    }

    // Other 5xx errors: Fallback
    if (statusCode >= 500) {
      return true;
    }

    // Other 4xx errors: Don't fallback
    if (statusCode >= 400) {
      return false;
    }

    return false;
  }

  /// Classify an error for logging/metrics purposes
  static ErrorCategory classifyError(Object error) {
    if (error is DioException) {
      switch (error.type) {
        case DioExceptionType.connectionTimeout:
        case DioExceptionType.sendTimeout:
        case DioExceptionType.receiveTimeout:
        case DioExceptionType.connectionError:
          return ErrorCategory.network;

        case DioExceptionType.badResponse:
          final statusCode = error.response?.statusCode;
          if (statusCode == 401 || statusCode == 403) {
            return ErrorCategory.auth;
          }
          if (statusCode == 429) {
            return ErrorCategory.rateLimit;
          }
          if (statusCode != null && statusCode >= 500) {
            return ErrorCategory.server;
          }
          return ErrorCategory.client;

        default:
          return ErrorCategory.unknown;
      }
    }

    return ErrorCategory.unknown;
  }
}

/// Error categories for classification
enum ErrorCategory {
  /// Network connectivity issues
  network,

  /// Authentication/authorization errors
  auth,

  /// Rate limiting
  rateLimit,

  /// Server-side errors (5xx)
  server,

  /// Client-side errors (4xx)
  client,

  /// Unknown/unclassified errors
  unknown,
}
