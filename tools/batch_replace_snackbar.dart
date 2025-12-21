/// 批量替换SnackBar为AppleToast的工具脚本
/// 
/// 使用方法:
/// dart run tools/batch_replace_snackbar.dart

import 'dart:io';

void main() async {
  print('🔄 开始批量替换SnackBar为AppleToast...\n');
  
  // 需要手动处理的文件列表（因为SnackBar的上下文较复杂）
  final filesToProcess = [
    'lib/pages/custom_roles_page.dart',
    'lib/pages/chat_page.dart',
    'lib/pages/model_services_page.dart',
    'lib/pages/settings_page.dart',
    'lib/pages/latex_test_page.dart',
    'lib/pages/provider_detail_page.dart',
    'lib/pages/model_edit_page.dart',
    'lib/rendering/widgets/latex_error_widget.dart',
    'lib/widgets/add_provider_dialog.dart',
    'lib/widgets/enhanced_latex_renderer.dart',
    'lib/widgets/optimized_latex_renderer.dart',
    'lib/widgets/enhanced_input_area.dart',
  ];
  
  int filesChecked = 0;
  int snackBarFound = 0;
  
  for (final filePath in filesToProcess) {
    final file = File(filePath);
    if (!await file.exists()) {
      print('⚠️  文件不存在: $filePath');
      continue;
    }
    
    String content = await file.readAsString();
    filesChecked++;
    
    // 检查是否包含SnackBar
    if (content.contains('ScaffoldMessenger.of(context).showSnackBar')) {
      final count = RegExp(r'ScaffoldMessenger\.of\(context\)\.showSnackBar').allMatches(content).length;
      snackBarFound += count;
      print('📝 $filePath: 发现 $count 处SnackBar');
      
      // 确保导入了apple_toast
      if (!content.contains("import 'apple_toast.dart'") &&
          !content.contains("import '../widgets/apple_toast.dart'") &&
          !content.contains("import 'package:chatbox/widgets/apple_toast.dart'")) {
        print('   ⚠️  需要添加 apple_toast.dart 导入');
      }
    }
  }
  
  print('\n📊 统计:');
  print('  - 检查文件: $filesChecked');
  print('  - 发现SnackBar: $snackBarFound 处');
  print('\n💡 这些SnackBar需要手动替换，因为它们的上下文和参数各不相同');
  print('   建议替换模式:');
  print('   - 成功消息: AppleToast.success(context, message: \'...\')');
  print('   - 错误消息: AppleToast.error(context, message: \'...\')');
  print('   - 警告消息: AppleToast.warning(context, message: \'...\')');
  print('   - 信息消息: AppleToast.info(context, message: \'...\')');
}
