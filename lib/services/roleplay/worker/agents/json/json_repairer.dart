/// JSON 结构修复器（S3 阶段）
///
/// 确定性修复 JSON 结构问题
/// POS: Services / Roleplay / Worker / Agents / JSON
library;

import 'dart:convert';

/// JSON 结构修复器
class JsonRepairer {
  /// 修复 JSON 结构
  ///
  /// 处理：
  /// - 确保必需字段存在
  /// - 数组包装（如果期望对象但收到数组）
  /// - 类型修正
  String repair(String json, {String? schema}) {
    Map<String, dynamic> obj;

    try {
      final decoded = jsonDecode(json);
      if (decoded is Map<String, dynamic>) {
        obj = decoded;
      } else if (decoded is List) {
        // 数组包装为对象
        obj = _wrapArray(decoded);
      } else {
        // 其他类型包装
        obj = {'value': decoded};
      }
    } catch (_) {
      // 解析失败，返回空结构
      return jsonEncode(_getDefaultStructure());
    }

    // 确保必需字段存在
    obj = _ensureRequiredFields(obj);

    // 类型修正
    obj = _fixTypes(obj);

    return jsonEncode(obj);
  }

  /// 包装数组为对象
  Map<String, dynamic> _wrapArray(List<dynamic> array) {
    // 尝试推断数组类型
    if (array.isNotEmpty) {
      final first = array.first;
      if (first is Map<String, dynamic>) {
        // 检查是否是 proposals 数组
        if (first.containsKey('kind') || first.containsKey('type')) {
          return {'proposals': array};
        }
        // 检查是否是 updates 数组
        if (first.containsKey('domain') || first.containsKey('field')) {
          return {'updates': array};
        }
        // 检查是否是 events 数组
        if (first.containsKey('summary') || first.containsKey('timestamp')) {
          return {'events': array};
        }
        // 检查是否是 violations 数组
        if (first.containsKey('violation') || first.containsKey('description')) {
          return {'violations': array};
        }
      }
    }
    return {'items': array};
  }

  /// 确保必需字段存在
  Map<String, dynamic> _ensureRequiredFields(Map<String, dynamic> obj) {
    // 通用字段
    if (!obj.containsKey('ok')) {
      obj['ok'] = obj['error'] == null;
    }

    // 确保数组字段为 List
    for (final key in ['proposals', 'updates', 'events', 'violations', 'logs']) {
      if (obj.containsKey(key) && obj[key] is! List) {
        obj[key] = <dynamic>[];
      }
    }

    return obj;
  }

  /// 修正类型
  Map<String, dynamic> _fixTypes(Map<String, dynamic> obj) {
    // 修正布尔值
    if (obj.containsKey('detected')) {
      obj['detected'] = _toBool(obj['detected']);
    }
    if (obj.containsKey('ok')) {
      obj['ok'] = _toBool(obj['ok']);
    }

    // 修正数值
    if (obj.containsKey('confidence')) {
      obj['confidence'] = _toDouble(obj['confidence']);
    }

    return obj;
  }

  /// 转换为布尔值
  bool _toBool(dynamic value) {
    if (value is bool) return value;
    if (value is String) {
      return value.toLowerCase() == 'true' || value == '1';
    }
    if (value is num) return value != 0;
    return false;
  }

  /// 转换为 double
  double _toDouble(dynamic value) {
    if (value is double) return value;
    if (value is int) return value.toDouble();
    if (value is String) return double.tryParse(value) ?? 0.0;
    return 0.0;
  }

  /// 获取默认结构
  Map<String, dynamic> _getDefaultStructure() {
    return {
      'ok': false,
      'error': 'parse_failed',
      'proposals': <dynamic>[],
      'logs': <dynamic>[],
    };
  }
}
