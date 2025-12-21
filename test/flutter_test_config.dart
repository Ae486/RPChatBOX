import 'dart:async';
import 'package:golden_toolkit/golden_toolkit.dart';

/// 全局测试配置
/// 
/// Flutter 会在运行测试前自动调用此文件中的 testExecutable 函数。
/// 这里配置全局的测试环境，如加载字体、设置设备尺寸等。
Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  // 配置 Golden 测试工具
  return GoldenToolkit.runWithConfiguration(
    () async {
      // 加载应用字体（确保 Golden 测试字体一致）
      await loadAppFonts();
      
      // 执行测试
      await testMain();
    },
    config: GoldenToolkitConfiguration(
      // 配置默认的测试设备尺寸
      // 为不同的设备尺寸生成 Golden 文件
      defaultDevices: const [
        Device.phone,              // 手机尺寸 (375x667)
        Device.tabletLandscape,    // 平板横屏 (1024x768)
      ],
      // 启用跳过 Golden 文件断言（在 CI 中有用）
      skipGoldenAssertion: () => false,
    ),
  );
}
