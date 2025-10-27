import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/chat_settings.dart';
import '../models/message.dart';
import '../utils/token_counter.dart';

/// 本地存储服务
class StorageService {
  static const String _settingsKey = 'chat_settings';
  static const String _messagesKey = 'chat_messages';
  static const String _tokenUsageKey = 'token_usage';

  /// 保存设置
  Future<void> saveSettings(ChatSettings settings) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_settingsKey, json.encode(settings.toJson()));
  }

  /// 加载设置
  Future<ChatSettings> loadSettings() async {
    final prefs = await SharedPreferences.getInstance();
    final jsonStr = prefs.getString(_settingsKey);
    
    if (jsonStr == null) {
      return ChatSettings(); // 返回默认设置
    }
    
    return ChatSettings.fromJson(json.decode(jsonStr));
  }

  /// 保存消息列表
  Future<void> saveMessages(List<Message> messages) async {
    final prefs = await SharedPreferences.getInstance();
    final jsonList = messages.map((msg) => msg.toJson()).toList();
    await prefs.setString(_messagesKey, json.encode(jsonList));
  }

  /// 加载消息列表
  Future<List<Message>> loadMessages() async {
    final prefs = await SharedPreferences.getInstance();
    final jsonStr = prefs.getString(_messagesKey);
    
    if (jsonStr == null) {
      return [];
    }
    
    final jsonList = json.decode(jsonStr) as List;
    return jsonList.map((json) => Message.fromJson(json)).toList();
  }

  /// 清空消息
  Future<void> clearMessages() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_messagesKey);
  }

  /// 保存 Token 使用统计
  Future<void> saveTokenUsage(TokenUsage usage) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_tokenUsageKey, json.encode(usage.toJson()));
  }

  /// 加载 Token 使用统计
  Future<TokenUsage> loadTokenUsage() async {
    final prefs = await SharedPreferences.getInstance();
    final jsonStr = prefs.getString(_tokenUsageKey);
    
    if (jsonStr == null) {
      return TokenUsage();
    }
    
    return TokenUsage.fromJson(json.decode(jsonStr));
  }

  /// 清空 Token 统计
  Future<void> clearTokenUsage() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenUsageKey);
  }
}

