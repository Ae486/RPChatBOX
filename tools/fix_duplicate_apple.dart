/// 修复重复的AppleAppleIcons错误
import 'dart:io';

void main() async {
  print('🔄 开始修复AppleAppleIcons重复问题...\n');
  
  final libDir = Directory('lib');
  final dartFiles = <File>[];
  
  // 递归查找所有dart文件
  await for (final entity in libDir.list(recursive: true)) {
    if (entity is File && entity.path.endsWith('.dart')) {
      dartFiles.add(entity);
    }
  }
  
  int filesFixed = 0;
  int totalReplacements = 0;
  
  for (final file in dartFiles) {
    String content = await file.readAsString();
    
    if (content.contains('AppleAppleIcons')) {
      final count = 'AppleAppleIcons'.allMatches(content).length;
      content = content.replaceAll('AppleAppleIcons', 'AppleIcons');
      
      await file.writeAsString(content);
      filesFixed++;
      totalReplacements += count;
      
      final relativePath = file.path.substring(file.path.indexOf('lib'));
      print('✅ $relativePath: $count 处修复');
    }
  }
  
  print('\n🎉 完成！');
  print('📊 共修复 $filesFixed 个文件');
  print('🔄 共替换 $totalReplacements 处重复');
}
