/// 批量修复所有SnackBar为AppleToast
import 'dart:io';

void main() async {
  print('🔄 开始批量修复SnackBar为AppleToast...\n');
  
  final files = <String, List<SnackBarReplacement>>{
    'lib/pages/chat_page.dart': [
      SnackBarReplacement(
        oldPattern: r"ScaffoldMessenger\.of\(context\)\.showSnackBar\(\s*SnackBar\(\s*content:\s*Text\('([^']+)'\)",
        messageGroup: 1,
        toastType: 'error',
      ),
    ],
    'lib/pages/model_services_page.dart': [
      SnackBarReplacement(
        oldPattern: r"ScaffoldMessenger\.of\(context\)\.showSnackBar\(\s*SnackBar\(\s*content:\s*Text\('([^']+)'\)",
        messageGroup: 1,
        toastType: 'error',
      ),
    ],
    'lib/pages/settings_page.dart': [
      SnackBarReplacement(
        oldPattern: r"ScaffoldMessenger\.of\(context\)\.showSnackBar\(\s*SnackBar\(\s*content:\s*Text\('([^']+)'\)",
        messageGroup: 1,
        toastType: 'info',
      ),
    ],
  };
  
  // 简单替换模式
  final simpleReplacements = <String, String>{
    "ScaffoldMessenger.of(context).showSnackBar(": "// TODO: Replace with AppleToast\n      // ",
  };
  
  int filesProcessed = 0;
  
  for (final entry in files.entries) {
    final filePath = entry.key;
    final file = File(filePath);
    
    if (!await file.exists()) {
      print('⚠️  文件不存在: $filePath');
      continue;
    }
    
    String content = await file.readAsString();
    bool modified = false;
    
    // 添加导入如果需要
    if (content.contains('ScaffoldMessenger') && 
        !content.contains("import '../widgets/apple_toast.dart'") &&
        !content.contains("import 'apple_toast.dart'")) {
      
      final firstImport = content.indexOf("import '");
      if (firstImport != -1) {
        final lineEnd = content.indexOf('\n', firstImport);
        final isWidget = filePath.contains('/widgets/');
        final importPath = isWidget 
            ? "import 'apple_toast.dart';"
            : "import '../widgets/apple_toast.dart';";
        content = content.substring(0, lineEnd + 1) +
            "$importPath\n" +
            content.substring(lineEnd + 1);
        modified = true;
      }
    }
    
    if (modified) {
      await file.writeAsString(content);
      filesProcessed++;
      print('✅ $filePath: 已添加导入');
    }
  }
  
  print('\n✅ 完成导入添加');
  print('📊 处理 $filesProcessed 个文件');
  print('\n⚠️  请手动替换SnackBar为AppleToast：');
  print('   - success消息: AppleToast.success(context, message: \'...\')');
  print('   - error消息: AppleToast.error(context, message: \'...\')');
  print('   - warning消息: AppleToast.warning(context, message: \'...\')');
  print('   - info消息: AppleToast.info(context, message: \'...\')');
}

class SnackBarReplacement {
  final String oldPattern;
  final int messageGroup;
  final String toastType;
  
  SnackBarReplacement({
    required this.oldPattern,
    required this.messageGroup,
    required this.toastType,
  });
}
