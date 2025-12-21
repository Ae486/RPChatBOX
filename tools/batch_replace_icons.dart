/// 批量替换Icons为AppleIcons的工具脚本
/// 
/// 使用方法:
/// dart run tools/batch_replace_icons.dart

import 'dart:io';

void main() async {
  print('🔄 开始批量替换Icons为AppleIcons...\n');
  
  final replacements = <String, String>{
    // 导航与操作
    'Icons.close': 'AppleIcons.close',
    'Icons.arrow_back': 'AppleIcons.back',
    'Icons.menu': 'AppleIcons.menu',
    'Icons.settings': 'AppleIcons.settings',
    'Icons.search': 'AppleIcons.search',
    'Icons.more_vert': 'AppleIcons.moreVertical',
    'Icons.more_horiz': 'AppleIcons.moreHorizontal',
    
    // 编辑与输入
    'Icons.add': 'AppleIcons.add',
    'Icons.add_circle_outline': 'AppleIcons.addCircle',
    'Icons.edit': 'AppleIcons.edit',
    'Icons.delete': 'AppleIcons.delete',
    'Icons.delete_outline': 'AppleIcons.delete',
    'Icons.copy': 'AppleIcons.copy',
    'Icons.content_copy': 'AppleIcons.copy',
    'Icons.check': 'AppleIcons.check',
    'Icons.check_circle': 'AppleIcons.checkCircle',
    'Icons.clear': 'AppleIcons.close',
    
    // 文件与文档
    'Icons.text_snippet': 'AppleIcons.document',
    'Icons.description': 'AppleIcons.document',
    'Icons.insert_drive_file': 'AppleIcons.file',
    'Icons.insert_drive_file_outlined': 'AppleIcons.file',
    'Icons.file_download': 'AppleIcons.download',
    'Icons.upload_file': 'AppleIcons.upload',
    'Icons.attach_file': 'AppleIcons.attach',
    
    // 媒体
    'Icons.image': 'AppleIcons.image',
    'Icons.broken_image': 'AppleIcons.imageOff',
    'Icons.image_not_supported': 'AppleIcons.imageOff',
    'Icons.videocam': 'AppleIcons.video',
    'Icons.audiotrack': 'AppleIcons.audio',
    'Icons.play_arrow': 'AppleIcons.play',
    
    // 用户与账户
    'Icons.person_rounded': 'AppleIcons.person',
    'Icons.person': 'AppleIcons.person',
    'Icons.person_add': 'AppleIcons.personAdd',
    'Icons.group': 'AppleIcons.group',
    
    // AI与智能
    'Icons.smart_toy': 'AppleIcons.chatbot',
    'Icons.code': 'AppleIcons.code',
    
    // 状态与指示
    'Icons.error': 'AppleIcons.error',
    'Icons.warning': 'AppleIcons.warning',
    'Icons.info': 'AppleIcons.info',
    'Icons.lightbulb': 'AppleIcons.lightbulb',
    
    // 展开与收起
    'Icons.expand_more': 'AppleIcons.arrowDown',
    'Icons.expand_less': 'AppleIcons.arrowUp',
    'Icons.keyboard_arrow_down': 'AppleIcons.arrowDown',
    'Icons.keyboard_arrow_up': 'AppleIcons.arrowUp',
    'Icons.chevron_right': 'AppleIcons.arrowRight',
    
    // 选择与交互
    'Icons.select_all': 'AppleIcons.selectAll',
    'Icons.deselect': 'AppleIcons.close',
    'Icons.open_in_new': 'AppleIcons.externalLink',
    
    // 移除与删除
    'Icons.remove_circle_outline': 'AppleIcons.removeCircle',
  };
  
  final libDir = Directory('lib');
  final dartFiles = <File>[];
  
  // 递归查找所有dart文件
  await for (final entity in libDir.list(recursive: true)) {
    if (entity is File && entity.path.endsWith('.dart')) {
      // 跳过apple_icons.dart本身
      if (!entity.path.contains('apple_icons.dart')) {
        dartFiles.add(entity);
      }
    }
  }
  
  print('📁 找到 ${dartFiles.length} 个Dart文件\n');
  
  int totalReplacements = 0;
  int filesModified = 0;
  
  for (final file in dartFiles) {
    String content = await file.readAsString();
    String originalContent = content;
    int fileReplacements = 0;
    
    // 执行所有替换
    for (final entry in replacements.entries) {
      final oldPattern = entry.key;
      final newPattern = entry.value;
      
      final count = RegExp(oldPattern).allMatches(content).length;
      if (count > 0) {
        content = content.replaceAll(oldPattern, newPattern);
        fileReplacements += count;
      }
    }
    
    // 如果有修改，写回文件
    if (fileReplacements > 0) {
      // 确保导入了apple_icons
      if (!content.contains("import '../design_system/apple_icons.dart'") &&
          !content.contains("import 'package:chatbox/design_system/apple_icons.dart'")) {
        // 在第一个import后面添加
        final firstImportIndex = content.indexOf("import '");
        if (firstImportIndex != -1) {
          final lineEnd = content.indexOf('\n', firstImportIndex);
          if (lineEnd != -1) {
            content = content.substring(0, lineEnd + 1) +
                "import '../design_system/apple_icons.dart';\n" +
                content.substring(lineEnd + 1);
          }
        }
      }
      
      await file.writeAsString(content);
      filesModified++;
      totalReplacements += fileReplacements;
      
      final relativePath = file.path.substring(file.path.indexOf('lib'));
      print('✅ $relativePath: $fileReplacements 处替换');
    }
  }
  
  print('\n🎉 完成！');
  print('📊 共修改 $filesModified 个文件');
  print('🔄 共替换 $totalReplacements 处Icons');
}
