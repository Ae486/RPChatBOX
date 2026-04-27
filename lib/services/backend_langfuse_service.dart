import 'package:dio/dio.dart';

import '../models/langfuse_settings.dart';
import 'dio_service.dart';

class BackendLangfuseService {
  static const String defaultBaseUrl = 'http://localhost:8765';

  final Dio _dio;

  BackendLangfuseService({Dio? dio})
    : _dio = dio ?? DioService().controlPlaneDio;

  Future<LangfuseSettingsStatus> getSettings() async {
    final response = await _dio.get(
      '$defaultBaseUrl/api/observability/langfuse',
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('获取 Langfuse 配置失败: $statusCode');
    }
    return LangfuseSettingsStatus.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<LangfuseSettingsStatus> updateSettings(
    LangfuseSettingsUpdateRequest request,
  ) async {
    final response = await _dio.put(
      '$defaultBaseUrl/api/observability/langfuse',
      data: request.toJson(),
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('保存 Langfuse 配置失败: $statusCode');
    }
    return LangfuseSettingsStatus.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }
}
