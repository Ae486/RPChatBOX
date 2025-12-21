/// 修复错误的图标名称
import 'dart:io';

void main() async {
  print('🔄 开始修复错误的图标名称...\n');
  
  final replacements = <String, String>{
    'AppleIcons.moreVertical': 'AppleIcons.moreVert',
    'AppleIcons.search_off': 'AppleIcons.searchOff',
    'AppleIcons.error_outline': 'AppleIcons.error',
    'AppleIcons.info_outline': 'AppleIcons.info',
    'AppleIcons.warning_amber_rounded': 'AppleIcons.warning',
  };
  
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
    bool modified = false;
    int fileReplacements = 0;
    
    for (final entry in replacements.entries) {
      if (content.contains(entry.key)) {
        final count = entry.key.allMatches(content).length;
        content = content.replaceAll(entry.key, entry.value);
        fileReplacements += count;
        modified = true;
      }
    }
    
    if (modified) {
      await file.writeAsString(content);
      filesFixed++;
      totalReplacements += fileReplacements;
      
      final relativePath = file.path.substring(file.path.indexOf('lib'));
      print('✅ $relativePath: $fileReplacements 处修复');
    }
  }
  
  print('\n🎉 完成！');
  print('📊 共修复 $filesFixed 个文件');
  print('🔄 共替换 $totalReplacements 处错误名称');
}
