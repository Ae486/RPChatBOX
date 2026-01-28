/// JSON 验证器（S2/S5 阶段）
///
/// 验证 JSON 结构和 Schema
/// POS: Services / Roleplay / Worker / Agents / JSON
library;

import 'dart:convert';

/// JSON 验证结果
class JsonValidateResult {
  final bool valid;
  final Map<String, dynamic>? data;
  final String? error;

  const JsonValidateResult.success(this.data)
      : valid = true,
        error = null;

  const JsonValidateResult.failed(this.error)
      : valid = false,
        data = null;
}

/// JSON 验证器
class JsonValidator {
  /// 验证 JSON 字符串
  JsonValidateResult validate(String json, {String? schema}) {
    // 尝试解析
    dynamic decoded;
    try {
      decoded = jsonDecode(json);
    } catch (e) {
      return JsonValidateResult.failed('JSON parse error: $e');
    }

    // 确保是 Map
    if (decoded is! Map<String, dynamic>) {
      if (decoded is List) {
        // 数组也接受，后续会包装
        return JsonValidateResult.success({'_array': decoded});
      }
      return JsonValidateResult.failed('Expected object, got ${decoded.runtimeType}');
    }

    // 基础结构验证
    final structureError = _validateStructure(decoded);
    if (structureError != null) {
      return JsonValidateResult.failed(structureError);
    }

    return JsonValidateResult.success(decoded);
  }

  /// 验证基础结构
  String? _validateStructure(Map<String, dynamic> data) {
    // 检查是否有任何有效的输出字段
    final hasValidOutput = data.containsKey('detected') ||
        data.containsKey('updates') ||
        data.containsKey('events') ||
        data.containsKey('violations') ||
        data.containsKey('proposals') ||
        data.containsKey('ok');

    if (!hasValidOutput) {
      // 检查是否完全为空
      if (data.isEmpty) {
        return 'Empty JSON object';
      }
    }

    // 验证数组字段类型
    for (final key in ['updates', 'events', 'violations', 'proposals', 'logs']) {
      if (data.containsKey(key) && data[key] != null && data[key] is! List) {
        return 'Field "$key" must be an array';
      }
    }

    return null;
  }
}
