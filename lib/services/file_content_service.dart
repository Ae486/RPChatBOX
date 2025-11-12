import 'dart:convert';
import 'dart:io';
import 'package:path/path.dart' as path;
import 'package:syncfusion_flutter_pdf/pdf.dart';
import 'package:archive/archive.dart';

/// 文件内容提取服务
/// 支持从各种文件类型中提取文本内容
class FileContentService {
  /// 从文件中提取文本内容
  static Future<String> extractTextContent(File file, String mimeType) async {
    try {
      final extension = path.extension(file.path).toLowerCase();

      switch (extension) {
        case '.txt':
          return await _extractFromText(file);
        case '.md':
          return await _extractFromMarkdown(file);
        case '.json':
          return await _extractFromJson(file);
        case '.pdf':
          return await _extractFromPdf(file);
        case '.doc':
        case '.docx':
          return await _extractFromWord(file);
        case '.csv':
          return await _extractFromCsv(file);
        case '.html':
        case '.htm':
          return await _extractFromHtml(file);
        case '.xml':
          return await _extractFromXml(file);
        default:
          if (mimeType.startsWith('text/')) {
            return await _extractFromText(file);
          }
          return await _extractFallback(file);
      }
    } catch (e) {
      return '// 文件内容提取失败: ${e.toString()}\n// 文件: ${file.path}';
    }
  }

  /// 检查文件是否适合作为文本内容处理
  static bool isTextProcessable(String mimeType, String extension) {
    final textMimeTypes = [
      'text/plain',
      'text/markdown',
      'text/html',
      'text/xml',
      'text/csv',
      'application/json',
      'application/xml',
      'application/pdf', // PDF 文档
      'application/msword', // .doc
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document', // .docx
    ];

    final textExtensions = [
      '.txt', '.md', '.json', '.csv', '.html', '.htm', '.xml',
      '.log', '.yaml', '.yml', '.toml', '.ini', '.conf', '.config',
      '.js', '.ts', '.dart', '.py', '.java', '.cpp', '.c', '.h',
      '.css', '.scss', '.less', '.sql', '.sh', '.bat', '.ps1',
      '.gitignore', '.dockerfile', 'Dockerfile', '.env',
      '.pdf', '.doc', '.docx', // 文档文件
    ];

    return textMimeTypes.contains(mimeType) ||
           textExtensions.contains(extension.toLowerCase());
  }

  /// 从纯文本文件提取内容
  static Future<String> _extractFromText(File file) async {
    try {
      return await file.readAsString(encoding: utf8);
    } catch (e) {
      return await file.readAsString(); // 尝试系统默认编码
    }
  }

  /// 从Markdown文件提取内容
  static Future<String> _extractFromMarkdown(File file) async {
    final content = await file.readAsString();
    // 简单处理：直接返回markdown内容，让AI理解
    return content;
  }

  /// 从JSON文件提取内容
  static Future<String> _extractFromJson(File file) async {
    try {
      final content = await file.readAsString();
      // 尝试格式化JSON以便阅读
      final dynamic json = jsonDecode(content);
      return const JsonEncoder.withIndent('  ').convert(json);
    } catch (e) {
      // 如果JSON格式错误，返回原始内容
      return await file.readAsString();
    }
  }

  /// 从CSV文件提取内容
  static Future<String> _extractFromCsv(File file) async {
    final content = await file.readAsString();
    final lines = content.split('\n');

    // 简单的CSV表格格式化
    final formatted = <String>[];
    for (int i = 0; i < lines.length && i < 100; i++) { // 限制行数
      final line = lines[i].trim();
      if (line.isNotEmpty) {
        formatted.add(line);
      }
    }

    if (formatted.length < lines.length) {
      formatted.add('... (还有 ${lines.length - formatted.length} 行未显示)');
    }

    return formatted.join('\n');
  }

  /// 从HTML文件提取内容
  static Future<String> _extractFromHtml(File file) async {
    final content = await file.readAsString();

    // 简单的HTML标签移除
    String cleanText = content;

    // 移除常见HTML标签
    final htmlTags = [
      RegExp(r'<script[^>]*>.*?</script>', caseSensitive: false, dotAll: true),
      RegExp(r'<style[^>]*>.*?</style>', caseSensitive: false, dotAll: true),
      RegExp(r'<[^>]+>', caseSensitive: false),
    ];

    for (final tag in htmlTags) {
      cleanText = cleanText.replaceAll(tag, '');
    }

    // 清理多余的空白
    cleanText = cleanText.replaceAll(RegExp(r'\s+'), ' ');
    cleanText = cleanText.replaceAll(RegExp(r'\n\s*\n'), '\n');

    return cleanText.trim();
  }

  /// 从XML文件提取内容
  static Future<String> _extractFromXml(File file) async {
    return await file.readAsString();
  }

  /// 从 PDF 文件提取内容
  static Future<String> _extractFromPdf(File file) async {
    try {
      // 使用 Syncfusion PDF 库提取文本
      final bytes = await file.readAsBytes();
      final PdfDocument document = PdfDocument(inputBytes: bytes);
      
      final StringBuffer textBuffer = StringBuffer();
      
      // 提取每一页的文本
      final PdfTextExtractor extractor = PdfTextExtractor(document);
      
      for (int i = 0; i < document.pages.count; i++) {
        if (i > 0) textBuffer.writeln('\n--- 第 ${i + 1} 页 ---\n');
        
        final String pageText = extractor.extractText(startPageIndex: i, endPageIndex: i);
        textBuffer.write(pageText);
        
        // 限制提取的页数（防止过大的PDF占用太多token）
        if (i >= 49) { // 最多50页
          textBuffer.writeln('\n\n... (还有 ${document.pages.count - 50} 页未提取)');
          break;
        }
      }
      
      document.dispose();
      
      final extractedText = textBuffer.toString().trim();
      
      if (extractedText.isEmpty) {
        return 'PDF文档信息: ${file.path}\n\n[注意: 该PDF文件为空白或无法提取文本，可能是扫描的图片PDF]';
      }
      
      return extractedText;
    } catch (e) {
      return 'PDF文件处理失败: ${e.toString()}\n\n文件: ${file.path}';
    }
  }

  /// 从 Word 文档提取内容
  static Future<String> _extractFromWord(File file) async {
    try {
      final extension = path.extension(file.path).toLowerCase();
      
      if (extension == '.docx') {
        // DOCX 是 ZIP 格式，可以解析
        final bytes = await file.readAsBytes();
        final archive = ZipDecoder().decodeBytes(bytes);
        
        // 查找 word/document.xml 文件
        final documentXml = archive.findFile('word/document.xml');
        
        if (documentXml != null) {
          final content = utf8.decode(documentXml.content as List<int>);
          
          // 简单的XML文本提取（提取<w:t>标签内的文本）
          final textRegex = RegExp(r'<w:t[^>]*>([^<]*)</w:t>');
          final matches = textRegex.allMatches(content);
          
          final StringBuffer textBuffer = StringBuffer();
          for (final match in matches) {
            if (match.group(1) != null) {
              textBuffer.write(match.group(1));
            }
          }
          
          // 处理段落分隔
          String extractedText = textBuffer.toString();
          extractedText = extractedText.replaceAll(RegExp(r'(\w)(<w:p[^>]*>)'), r'\1\n\2');
          
          if (extractedText.trim().isEmpty) {
            return 'Word文档信息: ${file.path}\n\n[注意: 该Word文档为空白或无法提取文本]';
          }
          
          return extractedText.trim();
        } else {
          return 'Word文档信息: ${file.path}\n\n[注意: 无法找到文档内容]';
        }
      } else {
        // .doc 格式需要更复杂的解析，暂不支持
        final fileSize = await file.length();
        return '''Word文档信息 (.doc):
文件路径: ${file.path}
文件大小: ${_formatFileSize(fileSize)}

[注意: 旧版 .doc 格式暂不支持提取，请转换为 .docx 格式]''';
      }
    } catch (e) {
      return 'Word文档处理失败: ${e.toString()}\n\n文件: ${file.path}';
    }
  }

  /// 通用后备处理方法
  static Future<String> _extractFallback(File file) async {
    try {
      final fileSize = await file.length();
      final lastModified = await file.lastModified();
      final extension = path.extension(file.path);

      // 对于二进制文件，尝试读取一小部分来判断是否包含文本
      final bytes = await file.openRead(0, 1024).toList();
      final byteString = String.fromCharCodes(bytes.expand((e) => e).toList());

      // 检查是否包含可打印字符的比例
      int printableChars = 0;
      for (int char in byteString.codeUnits) {
        if ((char >= 32 && char <= 126) || char == 9 || char == 10 || char == 13) {
          printableChars++;
        }
      }

      final printableRatio = printableChars / byteString.length;

      if (printableRatio > 0.7) {
        // 主要是文本内容，尝试读取
        try {
          final content = await file.readAsString();
          return content.length > 5000
              ? '${content.substring(0, 5000)}\n... (内容过长，已截断)'
              : content;
        } catch (e) {
          // 无法作为文本读取
        }
      }

      return '''文件信息:
文件路径: ${file.path}
文件类型: $extension
文件大小: ${_formatFileSize(fileSize)}
最后修改: ${lastModified.toLocal()}
文本内容比例: ${(printableRatio * 100).toStringAsFixed(1)}%
[此文件类型暂不支持内容提取]''';
    } catch (e) {
      return '// 文件处理失败: ${e.toString()}';
    }
  }

  /// 格式化文件大小
  static String _formatFileSize(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    if (bytes < 1024 * 1024 * 1024) return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB';
  }

  /// 生成文件内容的提示文本
  static String generateFilePrompt(String fileName, String mimeType, String content) {
    final prompt = StringBuffer();
    prompt.writeln('以下是文件 "$fileName" ($mimeType) 的内容:');
    prompt.writeln('---');
    prompt.writeln(content);
    prompt.writeln('---');
    prompt.writeln();
    prompt.writeln('请基于上述文件内容回答用户的问题。');

    return prompt.toString();
  }
}