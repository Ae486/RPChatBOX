import 'package:dio/dio.dart';

import '../models/custom_role.dart';
import 'dio_service.dart';

class BackendCustomRoleService {
  static const String defaultBaseUrl = 'http://localhost:8765';

  final Dio _dio;
  final String _baseUrl;

  BackendCustomRoleService({Dio? dio, String? baseUrl})
    : _dio = dio ?? DioService().controlPlaneDio,
      _baseUrl = baseUrl ?? defaultBaseUrl;

  Future<List<CustomRole>> listRoles() async {
    final response = await _dio.get('$_baseUrl/api/custom-roles');
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend custom role list failed: $statusCode');
    }

    final payload = Map<String, dynamic>.from(response.data as Map);
    final items = payload['data'] as List? ?? const [];
    return items
        .whereType<Map>()
        .map((item) => _jsonToCustomRole(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<CustomRole> createRole(CustomRole role) async {
    final response = await _dio.post(
      '$_baseUrl/api/custom-roles',
      data: _customRoleToJson(role),
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend custom role create failed: $statusCode');
    }
    return _jsonToCustomRole(Map<String, dynamic>.from(response.data as Map));
  }

  Future<CustomRole> updateRole(CustomRole role) async {
    final response = await _dio.put(
      '$_baseUrl/api/custom-roles/${role.id}',
      data: _customRoleToJson(role),
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend custom role update failed: $statusCode');
    }
    return _jsonToCustomRole(Map<String, dynamic>.from(response.data as Map));
  }

  Future<void> deleteRole(String roleId) async {
    final response = await _dio.delete('$_baseUrl/api/custom-roles/$roleId');
    final statusCode = response.statusCode ?? 500;
    if (statusCode == 404) {
      return;
    }
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend custom role delete failed: $statusCode');
    }
  }

  Future<void> importMissingLocalRoles(List<CustomRole> localRoles) async {
    if (localRoles.isEmpty) return;
    final backendRoles = await listRoles();
    final backendIds = backendRoles.map((role) => role.id).toSet();
    for (final role in localRoles) {
      if (backendIds.contains(role.id)) continue;
      await createRole(role);
    }
  }

  CustomRole _jsonToCustomRole(Map<String, dynamic> json) {
    return CustomRole(
      id: json['id'] as String,
      name: json['name'] as String,
      description: json['description'] as String? ?? '',
      systemPrompt: json['system_prompt'] as String? ?? '',
      icon: json['icon'] as String? ?? '✨',
    );
  }

  Map<String, dynamic> _customRoleToJson(CustomRole role) {
    return {
      'id': role.id,
      'name': role.name,
      'description': role.description,
      'system_prompt': role.systemPrompt,
      'icon': role.icon,
    };
  }
}
