import 'package:dio/dio.dart';

import '../models/model_config.dart';
import '../models/provider_config.dart';
import 'dio_service.dart';

class BackendModelSummary {
  final String id;
  final String providerId;
  final String modelName;
  final String displayName;
  final Set<ModelCapability> capabilities;
  final ModelParameters defaultParams;
  final bool isEnabled;
  final String? description;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  const BackendModelSummary({
    required this.id,
    required this.providerId,
    required this.modelName,
    required this.displayName,
    required this.capabilities,
    required this.defaultParams,
    required this.isEnabled,
    required this.description,
    required this.createdAt,
    required this.updatedAt,
  });

  factory BackendModelSummary.fromJson(Map<String, dynamic> json) {
    final rawCapabilities = json['capabilities'] as List? ?? const [];
    return BackendModelSummary(
      id: json['id'] as String,
      providerId: json['provider_id'] as String,
      modelName: json['model_name'] as String,
      displayName: json['display_name'] as String,
      capabilities: rawCapabilities
          .map(
            (item) => ModelCapability.values.firstWhere(
              (value) => value.name == item,
              orElse: () => ModelCapability.text,
            ),
          )
          .toSet(),
      defaultParams: json['default_params'] != null
          ? ModelParameters.fromJson(
              _defaultParamsFromBackend(
                Map<String, dynamic>.from(json['default_params'] as Map),
              ),
            )
          : const ModelParameters(),
      isEnabled: json['is_enabled'] as bool? ?? true,
      description: json['description'] as String?,
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'] as String)
          : null,
      updatedAt: json['updated_at'] != null
          ? DateTime.tryParse(json['updated_at'] as String)
          : null,
    );
  }

  static Map<String, dynamic> _defaultParamsFromBackend(
    Map<String, dynamic> json,
  ) {
    return {
      'temperature': json['temperature'],
      'maxTokens': json['max_tokens'],
      'topP': json['top_p'],
      'frequencyPenalty': json['frequency_penalty'],
      'presencePenalty': json['presence_penalty'],
      'streamOutput': json['stream_output'],
    };
  }
}

class BackendModelRegistryService {
  static const String defaultBaseUrl = 'http://localhost:8765';

  final Dio _dio;

  BackendModelRegistryService({Dio? dio})
    : _dio = dio ?? DioService().controlPlaneDio;

  String _resolveBaseUrl(String? proxyApiUrl) => proxyApiUrl ?? defaultBaseUrl;

  Options _buildOptions(Map<String, dynamic>? proxyHeaders) {
    final headers = <String, dynamic>{'Content-Type': 'application/json'};
    if (proxyHeaders != null) {
      headers.addAll(proxyHeaders);
    }
    return Options(headers: headers);
  }

  Map<String, dynamic> _buildPayload(ModelConfig model) {
    return {
      'id': model.id,
      'provider_id': model.providerId,
      'model_name': model.modelName,
      'display_name': model.displayName,
      'capabilities': model.capabilities.map((item) => item.name).toList(),
      'default_params': {
        'temperature': model.defaultParams.temperature,
        'max_tokens': model.defaultParams.maxTokens,
        'top_p': model.defaultParams.topP,
        'frequency_penalty': model.defaultParams.frequencyPenalty,
        'presence_penalty': model.defaultParams.presencePenalty,
        'stream_output': model.defaultParams.streamOutput,
      },
      'is_enabled': model.isEnabled,
      'description': model.description,
      'created_at': model.createdAt.toIso8601String(),
      'updated_at': model.updatedAt.toIso8601String(),
    };
  }

  Future<BackendModelSummary> upsertModel({
    required ProviderConfig provider,
    required ModelConfig model,
  }) async {
    final response = await _dio.put(
      '${_resolveBaseUrl(provider.proxyApiUrl)}/api/providers/${provider.id}/models/${model.id}',
      data: _buildPayload(model),
      options: _buildOptions(provider.proxyHeaders),
    );

    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend model sync failed: ${response.statusCode}');
    }

    return BackendModelSummary.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<void> deleteModel({
    required ProviderConfig provider,
    required ModelConfig model,
  }) async {
    final response = await _dio.delete(
      '${_resolveBaseUrl(provider.proxyApiUrl)}/api/providers/${provider.id}/models/${model.id}',
      options: _buildOptions(provider.proxyHeaders),
    );

    final statusCode = response.statusCode ?? 500;
    if (statusCode == 404) {
      return;
    }
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend model delete failed: ${response.statusCode}');
    }
  }

  Future<List<BackendModelSummary>> listModels({
    required ProviderConfig provider,
  }) async {
    final response = await _dio.get(
      '${_resolveBaseUrl(provider.proxyApiUrl)}/api/providers/${provider.id}/models',
      options: _buildOptions(provider.proxyHeaders),
    );

    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend model list failed: ${response.statusCode}');
    }

    final data = response.data as Map<String, dynamic>;
    final items = data['data'] as List? ?? const [];
    return items
        .whereType<Map>()
        .map(
          (item) =>
              BackendModelSummary.fromJson(Map<String, dynamic>.from(item)),
        )
        .toList();
  }
}
