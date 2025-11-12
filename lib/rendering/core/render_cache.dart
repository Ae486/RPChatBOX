import 'package:flutter/material.dart';
import 'dart:convert';
import 'package:crypto/crypto.dart';

/// 简单的渲染缓存管理器
/// 使用LRU策略，基于内存的Widget缓存
class RenderCache {
  // 单例模式
  static final RenderCache _instance = RenderCache._internal();
  factory RenderCache() => _instance;
  RenderCache._internal();

  // 缓存存储
  final Map<String, _CachedWidget> _cache = {};
  final List<String> _accessOrder = []; // LRU顺序

  // 配置
  static const int maxCacheSize = 100; // 最大缓存数量
  static const Duration cacheExpiration = Duration(minutes: 30); // 缓存过期时间

  // 统计信息
  int _hits = 0;
  int _misses = 0;

  /// 生成缓存键
  static String generateKey(String content, {String? type, Map<String, dynamic>? options}) {
    final data = {
      'content': content,
      'type': type ?? 'default',
      'options': options ?? {},
    };
    final jsonStr = json.encode(data);
    return md5.convert(utf8.encode(jsonStr)).toString();
  }

  /// 获取缓存的Widget
  Widget? get(String key) {
    final cached = _cache[key];
    
    if (cached == null) {
      _misses++;
      return null;
    }

    // 检查是否过期
    if (DateTime.now().difference(cached.timestamp) > cacheExpiration) {
      _cache.remove(key);
      _accessOrder.remove(key);
      _misses++;
      return null;
    }

    // 更新访问顺序（LRU）
    _accessOrder.remove(key);
    _accessOrder.add(key);
    
    _hits++;
    return cached.widget;
  }

  /// 设置缓存
  void set(String key, Widget widget) {
    // 如果已存在，先移除旧的
    if (_cache.containsKey(key)) {
      _accessOrder.remove(key);
    }

    // 如果超过最大容量，移除最旧的
    while (_cache.length >= maxCacheSize) {
      final oldestKey = _accessOrder.first;
      _cache.remove(oldestKey);
      _accessOrder.removeAt(0);
    }

    // 添加新的缓存
    _cache[key] = _CachedWidget(widget: widget);
    _accessOrder.add(key);
  }

  /// 清除所有缓存
  void clear() {
    _cache.clear();
    _accessOrder.clear();
    _hits = 0;
    _misses = 0;
  }

  /// 清除过期的缓存
  void clearExpired() {
    final now = DateTime.now();
    final expiredKeys = <String>[];

    _cache.forEach((key, cached) {
      if (now.difference(cached.timestamp) > cacheExpiration) {
        expiredKeys.add(key);
      }
    });

    for (var key in expiredKeys) {
      _cache.remove(key);
      _accessOrder.remove(key);
    }
  }

  /// 获取缓存统计信息
  Map<String, dynamic> getStats() {
    final total = _hits + _misses;
    final hitRate = total > 0 ? (_hits / total * 100).toStringAsFixed(2) : '0.00';
    
    return {
      'size': _cache.length,
      'maxSize': maxCacheSize,
      'hits': _hits,
      'misses': _misses,
      'hitRate': '$hitRate%',
      'total': total,
    };
  }

  /// 获取缓存大小（估算，以字节为单位）
  int get cacheSize => _cache.length;

  /// 缓存命中率
  double get hitRate {
    final total = _hits + _misses;
    return total > 0 ? _hits / total : 0.0;
  }
}

/// 缓存的Widget包装
class _CachedWidget {
  final Widget widget;
  final DateTime timestamp;

  _CachedWidget({
    required this.widget,
  }) : timestamp = DateTime.now();
}

/// 带缓存的Widget包装器
class CachedWidget extends StatelessWidget {
  final String cacheKey;
  final Widget Function() builder;

  const CachedWidget({
    super.key,
    required this.cacheKey,
    required this.builder,
  });

  @override
  Widget build(BuildContext context) {
    final cache = RenderCache();
    
    // 尝试从缓存获取
    final cached = cache.get(cacheKey);
    if (cached != null) {
      return cached;
    }

    // 构建新的Widget
    final widget = builder();
    
    // 缓存
    cache.set(cacheKey, widget);
    
    return widget;
  }
}
