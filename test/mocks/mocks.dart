import 'package:mockito/annotations.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:chatboxapp/services/hive_conversation_service.dart';

/// Mock 类定义
/// 
/// 使用 mockito 的 @GenerateMocks 注解来自动生成 Mock 类。
/// 运行 `flutter pub run build_runner build` 来生成 mocks.mocks.dart 文件。
/// 
/// 生成后，可以在测试中这样使用：
/// ```dart
/// import 'mocks.mocks.dart';
/// 
/// final mockService = MockHiveConversationService();
/// when(mockService.loadConversations()).thenAnswer((_) async => []);
/// ```
@GenerateMocks([
  HiveConversationService,
  SharedPreferences,
])
void main() {
  // 这个文件仅用于生成 Mock 类，不包含实际测试
  // 运行: flutter pub run build_runner build --delete-conflicting-outputs
}
