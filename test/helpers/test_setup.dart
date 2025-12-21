import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:chatboxapp/main.dart';
import 'package:chatboxapp/services/model_service_manager.dart';

/// 测试环境设置辅助类
///
/// 提供初始化全局依赖的方法，确保测试环境正确配置。
///
/// 使用示例：
/// ```dart
/// setUpAll(() async {
///   await TestSetup.initialize();
/// });
///
/// tearDownAll(() async {
///   await TestSetup.reset();
/// });
/// ```
class TestSetup {
  /// 初始化测试环境
  ///
  /// 必须在使用依赖全局变量的 Widget 测试前调用。
  /// 例如：ConversationView 依赖 globalModelServiceManager
  static Future<void> initialize() async {
    TestWidgetsFlutterBinding.ensureInitialized();

    // 设置 SharedPreferences mock
    SharedPreferences.setMockInitialValues({
      'config_version': 2, // 跳过迁移
    });

    // 初始化全局 ModelServiceManager
    final prefs = await SharedPreferences.getInstance();
    globalModelServiceManager = ModelServiceManager(prefs);
    await globalModelServiceManager.initialize();
  }

  /// 重置测试环境
  ///
  /// 在 tearDownAll 中调用以清理状态，防止测试间状态泄漏
  static Future<void> reset() async {
    SharedPreferences.setMockInitialValues({
      'config_version': 2,
    });
    final prefs = await SharedPreferences.getInstance();
    globalModelServiceManager = ModelServiceManager(prefs);
    await globalModelServiceManager.initialize();
  }

  /// 设置带有预配置 Provider 和 Model 的测试环境
  static Future<void> initializeWithDefaultProvider() async {
    TestWidgetsFlutterBinding.ensureInitialized();

    final now = DateTime.now().toIso8601String();

    // 设置带有默认 Provider 的 SharedPreferences
    // 注意：字段名必须与 fromJson 方法中的字段名一致
    SharedPreferences.setMockInitialValues({
      'providers': '[{"id":"test-provider-1","name":"Test Provider","type":"openai","apiUrl":"https://api.test.com/v1/chat/completions","apiKey":"test-key","isEnabled":true,"createdAt":"$now","updatedAt":"$now","customHeaders":{}}]',
      'models': '[{"id":"test-model-1","providerId":"test-provider-1","modelName":"gpt-3.5-turbo","displayName":"GPT-3.5","capabilities":["text"],"isEnabled":true,"createdAt":"$now","updatedAt":"$now"}]',
      'config_version': 2,
    });

    final prefs = await SharedPreferences.getInstance();
    globalModelServiceManager = ModelServiceManager(prefs);
    await globalModelServiceManager.initialize();
  }

  /// 创建独立的 ModelServiceManager 实例（用于持久化验证测试）
  ///
  /// 返回一个新的 ModelServiceManager 实例，使用当前的 SharedPreferences 状态。
  /// 这对于验证数据是否正确持久化非常有用。
  ///
  /// 使用示例：
  /// ```dart
  /// // 写入数据
  /// await manager.addProvider(provider);
  ///
  /// // 创建新实例验证持久化
  /// final newManager = await TestSetup.createFreshManager();
  /// expect(newManager.getProviders().length, equals(1));
  /// ```
  static Future<ModelServiceManager> createFreshManager() async {
    final prefs = await SharedPreferences.getInstance();
    final manager = ModelServiceManager(prefs);
    await manager.initialize();
    return manager;
  }

  /// 创建带有自定义初始数据的 ModelServiceManager 实例
  ///
  /// [initialValues] SharedPreferences 的初始值
  static Future<ModelServiceManager> createManagerWithData(
    Map<String, Object> initialValues,
  ) async {
    SharedPreferences.setMockInitialValues(initialValues);
    final prefs = await SharedPreferences.getInstance();
    final manager = ModelServiceManager(prefs);
    await manager.initialize();
    return manager;
  }
}

/// 测试数据构建器
///
/// 提供构建测试用 JSON 数据的便捷方法
class TestDataBuilder {
  /// 构建 Provider JSON 字符串
  static String buildProviderJson({
    required String id,
    required String name,
    String type = 'openai',
    String apiUrl = 'https://api.test.com/v1',
    String apiKey = 'test-key',
    bool isEnabled = true,
    DateTime? createdAt,
    DateTime? updatedAt,
  }) {
    final now = (createdAt ?? DateTime.now()).toIso8601String();
    final updated = (updatedAt ?? DateTime.now()).toIso8601String();
    return '{"id":"$id","name":"$name","type":"$type","apiUrl":"$apiUrl","apiKey":"$apiKey","isEnabled":$isEnabled,"createdAt":"$now","updatedAt":"$updated","customHeaders":{}}';
  }

  /// 构建 Model JSON 字符串
  static String buildModelJson({
    required String id,
    required String providerId,
    required String modelName,
    required String displayName,
    List<String> capabilities = const ['text'],
    bool isEnabled = true,
    DateTime? createdAt,
    DateTime? updatedAt,
  }) {
    final now = (createdAt ?? DateTime.now()).toIso8601String();
    final updated = (updatedAt ?? DateTime.now()).toIso8601String();
    final caps = capabilities.map((c) => '"$c"').join(',');
    return '{"id":"$id","providerId":"$providerId","modelName":"$modelName","displayName":"$displayName","capabilities":[$caps],"isEnabled":$isEnabled,"createdAt":"$now","updatedAt":"$updated"}';
  }

  /// 构建包含多个 Provider 的 JSON 数组字符串
  static String buildProvidersArrayJson(List<String> providerJsons) {
    return '[${providerJsons.join(',')}]';
  }

  /// 构建包含多个 Model 的 JSON 数组字符串
  static String buildModelsArrayJson(List<String> modelJsons) {
    return '[${modelJsons.join(',')}]';
  }
}
