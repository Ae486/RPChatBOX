import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

/// Dio 网络请求服务
/// 提供统一的网络请求管理，支持拦截器、取消、重试等功能
class DioService {
  // 单例模式
  static final DioService _instance = DioService._internal();
  factory DioService() => _instance;

  late final Dio dataPlaneDio;
  late final Dio controlPlaneDio;

  /// Backward-compatible alias.
  /// Prefer using `dataPlaneDio` / `controlPlaneDio` explicitly in new code.
  Dio get dio => dataPlaneDio;

  DioService._internal() {
    dataPlaneDio = _createDio(
      plane: 'data',
      connectTimeout: const Duration(seconds: 30),
      receiveTimeout: const Duration(seconds: 120),
      sendTimeout: const Duration(seconds: 60),
    );
    controlPlaneDio = _createDio(
      plane: 'control',
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 30),
      sendTimeout: const Duration(seconds: 30),
    );
  }

  Dio _createDio({
    required String plane,
    required Duration connectTimeout,
    required Duration receiveTimeout,
    required Duration sendTimeout,
  }) {
    final dio = Dio(
      BaseOptions(
        connectTimeout: connectTimeout,
        receiveTimeout: receiveTimeout,
        sendTimeout: sendTimeout,
        validateStatus: (status) {
          // 接受所有状态码，让业务层处理
          return status != null;
        },
      ),
    );

    dio.interceptors.add(_createInterceptor(plane));
    return dio;
  }

  /// 创建拦截器
  Interceptor _createInterceptor(String plane) {
    return InterceptorsWrapper(
      onRequest: (options, handler) {
        options.extra['start_time'] = DateTime.now();
        options.extra['plane'] ??= plane;

        // 请求前统一处理
        if (kDebugMode) {
          debugPrint(
            '\n╔═══════════════════════════════════════════════════════════════',
          );
          debugPrint(
            '║ 🚀 [DIO:${options.extra['plane']}] 请求: ${options.method} ${options.uri}',
          );
          debugPrint('║ 📤 Headers: ${options.headers}');
          if (options.data != null && options.data.toString().length < 1000) {
            debugPrint('║ 📦 Data: ${options.data}');
          }
          debugPrint(
            '╚═══════════════════════════════════════════════════════════════\n',
          );
        }
        handler.next(options);
      },
      onResponse: (response, handler) {
        // 响应后统一处理
        if (kDebugMode) {
          debugPrint(
            '\n╔═══════════════════════════════════════════════════════════════',
          );
          debugPrint(
            '║ ✅ [DIO:${response.requestOptions.extra['plane'] ?? plane}] 响应: ${response.statusCode} ${response.requestOptions.uri}',
          );
          debugPrint(
            '║ ⏱️  耗时: ${response.requestOptions.extra['start_time'] != null ? DateTime.now().difference(response.requestOptions.extra['start_time']).inMilliseconds : '?'}ms',
          );
          debugPrint(
            '╚═══════════════════════════════════════════════════════════════\n',
          );
        }
        handler.next(response);
      },
      onError: (error, handler) {
        // 错误统一处理
        if (kDebugMode) {
          debugPrint(
            '\n╔═══════════════════════════════════════════════════════════════',
          );
          debugPrint(
            '║ ❌ [DIO:${error.requestOptions.extra['plane'] ?? plane}] 错误: ${error.requestOptions.uri}',
          );
          debugPrint('║ 类型: ${error.type}');
          debugPrint('║ 消息: ${error.message}');
          if (error.response != null) {
            debugPrint('║ 状态码: ${error.response?.statusCode}');
          }
          debugPrint(
            '╚═══════════════════════════════════════════════════════════════\n',
          );
        }

        // 可以在这里统一处理常见错误
        if (error.type == DioExceptionType.connectionTimeout) {
          debugPrint('连接超时，请检查网络');
        } else if (error.type == DioExceptionType.receiveTimeout) {
          debugPrint('接收超时，请稍后重试');
        } else if (error.type == DioExceptionType.sendTimeout) {
          debugPrint('发送超时，请检查网络');
        }

        handler.next(error);
      },
    );
  }

  /// 创建取消令牌（用于取消请求）
  CancelToken createCancelToken() => CancelToken();

  /// 通用 GET 请求
  Future<Response<T>> get<T>(
    String path, {
    Map<String, dynamic>? queryParameters,
    Options? options,
    CancelToken? cancelToken,
  }) async {
    return dio.get<T>(
      path,
      queryParameters: queryParameters,
      options: options,
      cancelToken: cancelToken,
    );
  }

  /// 通用 POST 请求
  Future<Response<T>> post<T>(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    Options? options,
    CancelToken? cancelToken,
    ProgressCallback? onSendProgress,
    ProgressCallback? onReceiveProgress,
  }) async {
    return dio.post<T>(
      path,
      data: data,
      queryParameters: queryParameters,
      options: options,
      cancelToken: cancelToken,
      onSendProgress: onSendProgress,
      onReceiveProgress: onReceiveProgress,
    );
  }

  /// 通用 PUT 请求
  Future<Response<T>> put<T>(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    Options? options,
    CancelToken? cancelToken,
  }) async {
    return dio.put<T>(
      path,
      data: data,
      queryParameters: queryParameters,
      options: options,
      cancelToken: cancelToken,
    );
  }

  /// 通用 DELETE 请求
  Future<Response<T>> delete<T>(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    Options? options,
    CancelToken? cancelToken,
  }) async {
    return dio.delete<T>(
      path,
      data: data,
      queryParameters: queryParameters,
      options: options,
      cancelToken: cancelToken,
    );
  }

  /// 下载文件
  Future<Response> download(
    String urlPath,
    dynamic savePath, {
    ProgressCallback? onReceiveProgress,
    CancelToken? cancelToken,
    Map<String, dynamic>? queryParameters,
    Options? options,
  }) async {
    return dio.download(
      urlPath,
      savePath,
      onReceiveProgress: onReceiveProgress,
      cancelToken: cancelToken,
      queryParameters: queryParameters,
      options: options,
    );
  }
}
