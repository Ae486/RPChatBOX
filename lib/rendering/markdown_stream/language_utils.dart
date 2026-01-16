import 'package:flutter/material.dart';

import '../../chat_ui/owui/owui_icons.dart';

/// 语言别名映射
/// 参考 markstream-vue: src/utils/languageIcon.ts
const Map<String, String> _languageAliasMap = {
  '': 'plain',
  'javascript': 'javascript',
  'js': 'javascript',
  'mjs': 'javascript',
  'cjs': 'javascript',
  'typescript': 'typescript',
  'ts': 'typescript',
  'jsx': 'jsx',
  'tsx': 'tsx',
  'golang': 'go',
  'py': 'python',
  'rb': 'ruby',
  'sh': 'shell',
  'bash': 'shell',
  'zsh': 'shell',
  'shellscript': 'shell',
  'bat': 'shell',
  'batch': 'shell',
  'ps1': 'powershell',
  'plaintext': 'plain',
  'text': 'plain',
  'c++': 'cpp',
  'c#': 'csharp',
  'objective-c': 'objectivec',
  'objective-c++': 'objectivecpp',
  'yml': 'yaml',
  'md': 'markdown',
  'rs': 'rust',
  'kt': 'kotlin',
};

/// 语言显示名称映射
const Map<String, String> _languageDisplayNames = {
  'javascript': 'JavaScript',
  'typescript': 'TypeScript',
  'jsx': 'JSX',
  'tsx': 'TSX',
  'html': 'HTML',
  'css': 'CSS',
  'scss': 'SCSS',
  'sass': 'Sass',
  'json': 'JSON',
  'python': 'Python',
  'ruby': 'Ruby',
  'go': 'Go',
  'java': 'Java',
  'kotlin': 'Kotlin',
  'c': 'C',
  'cpp': 'C++',
  'csharp': 'C#',
  'php': 'PHP',
  'swift': 'Swift',
  'rust': 'Rust',
  'scala': 'Scala',
  'shell': 'Shell',
  'powershell': 'PowerShell',
  'sql': 'SQL',
  'yaml': 'YAML',
  'xml': 'XML',
  'markdown': 'Markdown',
  'dart': 'Dart',
  'lua': 'Lua',
  'perl': 'Perl',
  'r': 'R',
  'julia': 'Julia',
  'haskell': 'Haskell',
  'erlang': 'Erlang',
  'elixir': 'Elixir',
  'clojure': 'Clojure',
  'vue': 'Vue',
  'svelte': 'Svelte',
  'docker': 'Docker',
  'dockerfile': 'Dockerfile',
  'terraform': 'Terraform',
  'graphql': 'GraphQL',
  'protobuf': 'Protobuf',
  'toml': 'TOML',
  'ini': 'INI',
  'diff': 'Diff',
  'mermaid': 'Mermaid',
  'plain': 'Plain Text',
  'plaintext': 'Plain Text',
};

/// 语言图标数据 (使用 OwuiIcons)
const Map<String, IconData> _languageIcons = {
  'javascript': OwuiIcons.code,
  'typescript': OwuiIcons.code,
  'python': OwuiIcons.code,
  'dart': OwuiIcons.code,
  'html': OwuiIcons.code,
  'css': OwuiIcons.code,
  'json': OwuiIcons.code,
  'markdown': OwuiIcons.document,
  'shell': OwuiIcons.terminal,
  'powershell': OwuiIcons.terminal,
  'sql': OwuiIcons.database,
  'docker': OwuiIcons.cloud,
  'dockerfile': OwuiIcons.cloud,
  'yaml': OwuiIcons.settings,
  'xml': OwuiIcons.code,
  'diff': OwuiIcons.code,
  'mermaid': OwuiIcons.accountTree,
  'plain': OwuiIcons.document,
};

/// 提取语言标识符
String _extractLanguageToken(String? lang) {
  if (lang == null || lang.isEmpty) return '';
  final trimmed = lang.trim();
  if (trimmed.isEmpty) return '';
  final firstToken = trimmed.split(RegExp(r'\s+'))[0];
  final base = firstToken.split(':')[0];
  return base.toLowerCase();
}

/// 标准化语言标识符
/// 
/// 将各种语言别名统一为规范名称
String normalizeLanguageIdentifier(String? lang) {
  final token = _extractLanguageToken(lang);
  return _languageAliasMap[token] ?? token;
}

/// 获取语言显示名称
/// 
/// 返回用于UI显示的友好名称
String getLanguageDisplayName(String lang) {
  final normalized = normalizeLanguageIdentifier(lang);
  return _languageDisplayNames[normalized] ?? 
         (normalized.isNotEmpty ? normalized.toUpperCase() : 'Plain Text');
}

/// 获取语言图标
///
/// 返回对应的 OwuiIcons 图标，如果没有则返回默认代码图标
IconData getLanguageIcon(String lang) {
  final normalized = normalizeLanguageIdentifier(lang);
  return _languageIcons[normalized] ?? OwuiIcons.code;
}

/// 检测是否为 diff 代码
bool looksLikeUnifiedDiff(String code) {
  final sample = code.length > 2000 ? code.substring(0, 2000) : code;
  return sample.contains('diff --git ') ||
      sample.contains('\n@@') ||
      sample.contains('\n--- ') ||
      sample.contains('\n+++ ') ||
      sample.startsWith('diff --git ') ||
      sample.startsWith('--- ') ||
      sample.startsWith('+++ ') ||
      sample.startsWith('@@');
}

/// 推断代码语言
/// 
/// 如果声明的语言为空或 plaintext，尝试从代码内容推断
String inferCodeLanguage({required String declaredLanguage, required String code}) {
  final lang = declaredLanguage.trim().toLowerCase();
  if (lang.isNotEmpty && lang != 'plaintext' && lang != 'plain' && lang != 'text') {
    return normalizeLanguageIdentifier(lang);
  }
  if (looksLikeUnifiedDiff(code)) return 'diff';
  return 'plain';
}

/// 语言信息
class LanguageInfo {
  final String identifier;
  final String displayName;
  final IconData icon;

  const LanguageInfo({
    required this.identifier,
    required this.displayName,
    required this.icon,
  });

  factory LanguageInfo.fromLanguage(String lang) {
    final normalized = normalizeLanguageIdentifier(lang);
    return LanguageInfo(
      identifier: normalized,
      displayName: getLanguageDisplayName(lang),
      icon: getLanguageIcon(lang),
    );
  }

  factory LanguageInfo.infer({required String declaredLanguage, required String code}) {
    final inferred = inferCodeLanguage(declaredLanguage: declaredLanguage, code: code);
    return LanguageInfo.fromLanguage(inferred);
  }
}
