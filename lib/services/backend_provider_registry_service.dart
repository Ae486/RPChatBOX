import 'package:dio/dio.dart';

import '../models/backend_mode.dart';
import '../models/provider_config.dart';
import 'dio_service.dart';

class BackendProviderSummary {
  final String id;
  final String name;
  final ProviderType type;
  final String apiUrl;
  final bool isEnabled;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final Map<String, dynamic> customHeaders;
  final String? description;
  final BackendMode? backendMode;
  final bool? fallbackEnabled;
  final int? fallbackTimeoutMs;

  const BackendProviderSummary({
    required this.id,
    required this.name,
    required this.type,
    required this.apiUrl,
    required this.isEnabled,
    required this.createdAt,
    required this.updatedAt,
    required this.customHeaders,
    required this.description,
    required this.backendMode,
    required this.fallbackEnabled,
    required this.fallbackTimeoutMs,
  });

  factory BackendProviderSummary.fromJson(Map<String, dynamic> json) {
    return BackendProviderSummary(
      id: json['id'] as String,
      name: json['name'] as String,
      type: ProviderType.values.firstWhere(
        (value) => value.name == json['type'],
        orElse: () => ProviderType.openai,
      ),
      apiUrl: json['api_url'] as String,
      isEnabled: json['is_enabled'] as bool? ?? true,
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'] as String)
          : null,
      updatedAt: json['updated_at'] != null
          ? DateTime.tryParse(json['updated_at'] as String)
          : null,
      customHeaders: Map<String, dynamic>.from(json['custom_headers'] ?? {}),
      description: json['description'] as String?,
      backendMode: json['backend_mode'] != null
          ? BackendMode.values.firstWhere(
              (value) => value.name == json['backend_mode'],
              orElse: () => BackendMode.direct,
            )
          : null,
      fallbackEnabled: json['fallback_enabled'] as bool?,
      fallbackTimeoutMs: json['fallback_timeout_ms'] as int?,
    );
  }
}

/// Backend provider registry client.
///
/// Persists provider configs into the Python backend so proxy chat/model
/// requests can reference them by `provider_id` instead of uploading secrets
/// on every request.
class BackendProviderRegistryService {
  static const String defaultBaseUrl = 'http://localhost:8765';

  final Dio _dio;

  BackendProviderRegistryService({Dio? dio})
    : _dio = dio ?? DioService().controlPlaneDio;

  String _resolveBaseUrl(String? proxyApiUrl) => proxyApiUrl ?? defaultBaseUrl;

  Options _buildOptions(Map<String, dynamic>? proxyHeaders) {
    final headers = <String, dynamic>{'Content-Type': 'application/json'};
    if (proxyHeaders != null) {
      headers.addAll(proxyHeaders);
    }
    return Options(headers: headers);
  }

  Map<String, dynamic> _buildPayload(ProviderConfig provider) {
    final payload = <String, dynamic>{
      'id': provider.id,
      'name': provider.name,
      'type': provider.type.name,
      'api_key': provider.apiKey,
      'api_url': provider.actualApiUrl,
      'is_enabled': provider.isEnabled,
      'created_at': provider.createdAt.toIso8601String(),
      'updated_at': provider.updatedAt.toIso8601String(),
      'custom_headers': provider.customHeaders,
      'description': provider.description,
    };

    // Always persist explicit routing mode so the backend does not
    // fall back to implicit "auto" for entries without backend_mode.
    payload['backend_mode'] = provider.backendMode.name;

    if (provider.backendMode == BackendMode.auto) {
      payload['fallback_enabled'] = provider.fallbackEnabled;
      payload['fallback_timeout_ms'] = provider.fallbackTimeoutMs;
      if (provider.circuitBreaker != null) {
        payload['circuit_breaker'] = {
          'failure_threshold': provider.circuitBreaker!.failureThreshold,
          'window_ms': provider.circuitBreaker!.windowMs,
          'open_ms': provider.circuitBreaker!.openMs,
          'half_open_max_calls': provider.circuitBreaker!.halfOpenMaxCalls,
        };
      }
    } else if (!provider.fallbackEnabled) {
      payload['fallback_enabled'] = false;
    }

    return payload;
  }

  Future<BackendProviderSummary> upsertProvider(ProviderConfig provider) async {
    final response = await _dio.put(
      '${_resolveBaseUrl(provider.proxyApiUrl)}/api/providers/${provider.id}',
      data: _buildPayload(provider),
      options: _buildOptions(provider.proxyHeaders),
    );

    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend provider sync failed: ${response.statusCode}');
    }

    return BackendProviderSummary.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<void> deleteProvider(ProviderConfig provider) async {
    final response = await _dio.delete(
      '${_resolveBaseUrl(provider.proxyApiUrl)}/api/providers/${provider.id}',
      options: _buildOptions(provider.proxyHeaders),
    );

    final statusCode = response.statusCode ?? 500;
    if (statusCode == 404) {
      return;
    }
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend provider delete failed: ${response.statusCode}');
    }
  }

  Future<List<BackendProviderSummary>> listProviders({
    String? proxyApiUrl,
    Map<String, dynamic>? proxyHeaders,
  }) async {
    final response = await _dio.get(
      '${_resolveBaseUrl(proxyApiUrl)}/api/providers',
      options: _buildOptions(proxyHeaders),
    );

    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend provider list failed: ${response.statusCode}');
    }

    final data = response.data as Map<String, dynamic>;
    final items = data['data'] as List? ?? const [];
    return items
        .whereType<Map>()
        .map(
          (item) =>
              BackendProviderSummary.fromJson(Map<String, dynamic>.from(item)),
        )
        .toList();
  }
}
