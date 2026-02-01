import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'conversation_service.dart';
import 'hive_conversation_service.dart';

/// 数据迁移服务
/// 
/// 负责将 SharedPreferences 中的数据迁移到 Hive
class DataMigrationService {
  static const String _migrationCompleteKey = 'hive_migration_complete';
  
  /// 检查是否需要迁移
  Future<bool> needsMigration() async {
    final prefs = await SharedPreferences.getInstance();
    final migrationComplete = prefs.getBool(_migrationCompleteKey) ?? false;
    
    // 如果已经迁移过，不需要再次迁移
    if (migrationComplete) {
      return false;
    }
    
    // 检查 SharedPreferences 中是否有数据
    final conversationsKey = 'conversations';
    final hasOldData = prefs.containsKey(conversationsKey);
    
    return hasOldData;
  }
  
  /// 执行迁移
  Future<void> migrate() async {
    debugPrint('开始数据迁移: SharedPreferences -> Hive');
    
    try {
      // 从 SharedPreferences 加载数据
      final oldService = ConversationService();
      final conversations = await oldService.loadConversations();
      final currentConversationId = await oldService.loadCurrentConversationId();
      
      debugPrint('从 SharedPreferences 读取到 ${conversations.length} 个会话');
      
      // 初始化并保存到 Hive
      final newService = HiveConversationService();
      await newService.initialize();
      
      // 迁移会话数据
      if (conversations.isNotEmpty) {
        await newService.saveConversations(conversations);
        debugPrint('成功迁移 ${conversations.length} 个会话到 Hive');
      }
      
      // 迁移当前会话 ID
      if (currentConversationId != null) {
        await newService.saveCurrentConversationId(currentConversationId);
        debugPrint('成功迁移当前会话 ID: $currentConversationId');
      }
      
      // 标记迁移完成
      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool(_migrationCompleteKey, true);
      
      debugPrint('数据迁移完成');
      
    } catch (e, stackTrace) {
      debugPrint('数据迁移失败: $e');
      debugPrint('Stack trace: $stackTrace');
      rethrow;
    }
  }
  
  /// 重置迁移状态（用于测试）
  Future<void> resetMigrationStatus() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_migrationCompleteKey);
    debugPrint('已重置迁移状态');
  }
}
