import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/custom_role.dart';

/// 自定义角色管理服务
class CustomRoleService {
  static const String _customRolesKey = 'custom_roles';

  /// 保存自定义角色列表
  Future<void> saveCustomRoles(List<CustomRole> roles) async {
    final prefs = await SharedPreferences.getInstance();
    final jsonList = roles.map((role) => role.toJson()).toList();
    await prefs.setString(_customRolesKey, json.encode(jsonList));
  }

  /// 加载自定义角色列表
  Future<List<CustomRole>> loadCustomRoles() async {
    final prefs = await SharedPreferences.getInstance();
    final jsonStr = prefs.getString(_customRolesKey);

    if (jsonStr == null || jsonStr.isEmpty) {
      return [];
    }

    try {
      final jsonList = json.decode(jsonStr) as List;
      return jsonList.map((json) => CustomRole.fromJson(json)).toList();
    } catch (e) {
      return [];
    }
  }

  /// 添加自定义角色
  Future<void> addCustomRole(CustomRole role) async {
    final roles = await loadCustomRoles();
    roles.add(role);
    await saveCustomRoles(roles);
  }

  /// 删除自定义角色
  Future<void> deleteCustomRole(String roleId) async {
    final roles = await loadCustomRoles();
    roles.removeWhere((r) => r.id == roleId);
    await saveCustomRoles(roles);
  }

  /// 更新自定义角色
  Future<void> updateCustomRole(CustomRole role) async {
    final roles = await loadCustomRoles();
    final index = roles.indexWhere((r) => r.id == role.id);
    if (index >= 0) {
      roles[index] = role;
      await saveCustomRoles(roles);
    }
  }
}



