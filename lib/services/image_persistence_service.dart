import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_cache_manager/flutter_cache_manager.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

/// 持久化过期的网络图片到本地文件系统
///
/// - 将图片存储到应用支持目录下
/// - 重写 Markdown 中的图片 URL 为 `file://` URI
/// - 优先从 CachedNetworkImage 缓存复用已下载图片
class ImagePersistenceService {
  static final ImagePersistenceService _instance =
      ImagePersistenceService._internal();
  factory ImagePersistenceService() => _instance;
  ImagePersistenceService._internal();

  static const String _rootDirName = 'persisted_images';
  static const String _versionDirName = 'v1';
  static const String _fileExtension = 'img';

  final Map<String, Future<File?>> _inflightById = <String, Future<File?>>{};

  static final RegExp _markdownImageRegex =
      RegExp(r'!\[([^\]]*)\]\(([^)]*)\)');

  /// 从 Markdown 文本中提取所有网络图片 URL
  static Iterable<String> extractNetworkImageUrlsFromMarkdown(
    String markdown,
  ) sync* {
    for (final match in _markdownImageRegex.allMatches(markdown)) {
      final inner = match.group(2) ?? '';
      final parsed = _parseImageInner(inner);
      if (parsed == null) continue;

      final uri = Uri.tryParse(parsed.url);
      if (uri == null) continue;
      if (uri.scheme == 'http' || uri.scheme == 'https') {
        yield parsed.url;
      }
    }
  }

  /// 持久化 Markdown 中的所有网络图片到本地文件
  /// 返回更新后的 Markdown 和是否有变更
  Future<({String markdown, bool changed})> persistMarkdownImagesToLocalFiles(
    String markdown,
  ) async {
    final matches = _markdownImageRegex.allMatches(markdown).toList();
    if (matches.isEmpty) {
      return (markdown: markdown, changed: false);
    }

    var changed = false;
    final out = StringBuffer();
    var last = 0;

    for (final match in matches) {
      out.write(markdown.substring(last, match.start));

      final alt = match.group(1) ?? '';
      final inner = match.group(2) ?? '';
      final parsed = _parseImageInner(inner);
      if (parsed == null) {
        out.write(markdown.substring(match.start, match.end));
        last = match.end;
        continue;
      }

      final uri = Uri.tryParse(parsed.url);
      if (uri == null || (uri.scheme != 'http' && uri.scheme != 'https')) {
        out.write(markdown.substring(match.start, match.end));
        last = match.end;
        continue;
      }

      final persisted = await persistNetworkImage(parsed.url);
      if (persisted == null) {
        out.write(markdown.substring(match.start, match.end));
        last = match.end;
        continue;
      }

      changed = true;
      final persistedUrl = persisted.uri.toString();
      final newInner = '${parsed.leading}${parsed.angle ? '<' : ''}'
          '$persistedUrl${parsed.angle ? '>' : ''}${parsed.trailing}';

      out.write('![$alt]($newInner)');
      last = match.end;
    }

    out.write(markdown.substring(last));
    return (markdown: out.toString(), changed: changed);
  }

  /// 持久化单张网络图片到本地
  Future<File?> persistNetworkImage(String url) {
    final uri = Uri.tryParse(url);
    if (uri == null || (uri.scheme != 'http' && uri.scheme != 'https')) {
      return Future<File?>.value(null);
    }

    final id = _idForUrl(url);
    final existing = _inflightById[id];
    if (existing != null) return existing;

    final future = _persistNetworkImageInternal(url, id);
    _inflightById[id] = future;
    return future.whenComplete(() {
      _inflightById.remove(id);
    });
  }

  /// 清理陈旧/损坏的文件
  Future<void> cleanupStaleFiles() async {
    try {
      final dir = await _dir(create: false);
      if (!await dir.exists()) return;

      await for (final entity in dir.list(followLinks: false)) {
        if (entity is! File) continue;

        final path = entity.path;
        if (path.endsWith('.tmp')) {
          await entity.delete();
          continue;
        }
        if (path.endsWith('.$_fileExtension')) {
          final len = await entity.length();
          if (len <= 0) {
            await entity.delete();
          }
        }
      }
    } catch (e) {
      if (kDebugMode) {
        debugPrint('[image_persistence] cleanupStaleFiles failed: $e');
      }
    }
  }

  /// 清理所有持久化图片
  Future<void> clearAllPersistedImages() async {
    try {
      final dir = await _dir(create: false);
      if (await dir.exists()) {
        await dir.delete(recursive: true);
      }
    } catch (e) {
      if (kDebugMode) {
        debugPrint('[image_persistence] clearAllPersistedImages failed: $e');
      }
    }
  }

  String _idForUrl(String url) {
    return sha256.convert(utf8.encode(url)).toString();
  }

  Future<File?> _persistNetworkImageInternal(String url, String id) async {
    final target = await _targetFile(id);
    if (await target.exists()) {
      final len = await target.length();
      if (len > 0) return target;
      try {
        await target.delete();
      } catch (_) {
        // ignore
      }
    }

    // 1) 优先从 CachedNetworkImage 缓存复用
    try {
      final cached = await DefaultCacheManager().getFileFromCache(url);
      final cachedFile = cached?.file;
      if (cachedFile != null &&
          await cachedFile.exists() &&
          await cachedFile.length() > 0) {
        final copied = await _copyAtomically(cachedFile, target);
        if (copied != null) return copied;
      }
    } catch (_) {
      // ignore
    }

    // 2) 通过 DefaultCacheManager 下载
    try {
      final downloaded = await DefaultCacheManager().getSingleFile(url);
      if (await downloaded.exists() && await downloaded.length() > 0) {
        final copied = await _copyAtomically(downloaded, target);
        if (copied != null) return copied;
      }
    } catch (_) {
      // ignore
    }

    return null;
  }

  Future<File?> _copyAtomically(File source, File target) async {
    try {
      final tmp = File('${target.path}.tmp');
      if (await tmp.exists()) {
        await tmp.delete();
      }

      await source.copy(tmp.path);
      final len = await tmp.length();
      if (len <= 0) {
        await tmp.delete();
        return null;
      }

      if (await target.exists()) {
        await target.delete();
      }

      await tmp.rename(target.path);
      return target;
    } catch (_) {
      return null;
    }
  }

  Future<File> _targetFile(String id) async {
    final dir = await _dir(create: true);
    return File(p.join(dir.path, '$id.$_fileExtension'));
  }

  Future<Directory> _dir({required bool create}) async {
    final base = await getApplicationSupportDirectory();
    final dir = Directory(p.join(base.path, _rootDirName, _versionDirName));
    if (create && !await dir.exists()) {
      await dir.create(recursive: true);
    }
    return dir;
  }

  /// 解析 Markdown 图片语法的内部部分
  /// 支持: ![alt](url) 和 ![alt](<url> "title")
  static _ParsedImageInner? _parseImageInner(String inner) {
    final trimmedLeft = inner.trimLeft();
    final leading = inner.substring(0, inner.length - trimmedLeft.length);

    if (trimmedLeft.isEmpty) return null;

    // 支持 <...> 形式: ![alt](<url> "title")
    if (trimmedLeft.startsWith('<')) {
      final closeIdx = trimmedLeft.indexOf('>');
      if (closeIdx <= 1) return null;

      final url = trimmedLeft.substring(1, closeIdx);
      final trailing = trimmedLeft.substring(closeIdx + 1);
      return _ParsedImageInner(
        leading: leading,
        url: url,
        angle: true,
        trailing: trailing,
      );
    }

    // 提取第一个 token (URL) 并保留其余部分 (如 title)
    final m = RegExp(r'^(\S+)([\s\S]*)$').firstMatch(trimmedLeft);
    if (m == null) return null;

    final url = m.group(1) ?? '';
    final trailing = m.group(2) ?? '';
    if (url.isEmpty) return null;
    return _ParsedImageInner(
      leading: leading,
      url: url,
      angle: false,
      trailing: trailing,
    );
  }
}

class _ParsedImageInner {
  final String leading;
  final String url;
  final bool angle;
  final String trailing;

  const _ParsedImageInner({
    required this.leading,
    required this.url,
    required this.angle,
    required this.trailing,
  });
}
