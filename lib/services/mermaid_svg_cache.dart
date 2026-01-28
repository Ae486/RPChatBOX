/// INPUT: Mermaid 代码 + 渲染配置
/// OUTPUT: MermaidSvgCache - SVG 缓存服务（存储渲染后的 SVG 字符串 + 尺寸）
/// POS: Services 层 - Mermaid SVG 缓存管理

/// Mermaid SVG 渲染数据
class MermaidSvgData {
  final String svgString;
  final double width;
  final double height;
  final DateTime createdAt;

  const MermaidSvgData({
    required this.svgString,
    required this.width,
    required this.height,
    required this.createdAt,
  });

  Map<String, dynamic> toJson() => {
        'svgString': svgString,
        'width': width,
        'height': height,
        'createdAt': createdAt.toIso8601String(),
      };

  factory MermaidSvgData.fromJson(Map<String, dynamic> json) => MermaidSvgData(
        svgString: json['svgString'] as String,
        width: (json['width'] as num).toDouble(),
        height: (json['height'] as num).toDouble(),
        createdAt: DateTime.parse(json['createdAt'] as String),
      );
}

/// Mermaid SVG 缓存服务
///
/// 使用 LRU 策略缓存渲染后的 SVG 数据，避免重复渲染。
/// 当 ListView 中的 MermaidRenderer 重建时，可直接使用缓存的 SVG
/// 进行原生 Flutter 渲染，避免 WebView 重建导致的高度跳变。
class MermaidSvgCache {
  MermaidSvgCache._();
  static final instance = MermaidSvgCache._();

  final _cache = <int, MermaidSvgData>{};
  static const _maxSize = 100;

  /// 生成缓存 key（基于 Mermaid 代码 + 主题）
  int _cacheKey(String code, bool isDark) {
    return Object.hash(code.hashCode, isDark);
  }

  /// 获取缓存的 SVG 数据
  MermaidSvgData? get(String mermaidCode, {bool isDark = false}) {
    final key = _cacheKey(mermaidCode, isDark);
    final data = _cache[key];
    if (data != null) {
      // LRU: 移动到末尾
      _cache.remove(key);
      _cache[key] = data;
    }
    return data;
  }

  /// 存储 SVG 数据到缓存
  void put(String mermaidCode, MermaidSvgData data, {bool isDark = false}) {
    final key = _cacheKey(mermaidCode, isDark);

    // LRU: 超出限制时移除最早的条目
    if (_cache.length >= _maxSize && !_cache.containsKey(key)) {
      _cache.remove(_cache.keys.first);
    }

    _cache[key] = data;
  }

  /// 检查是否有缓存
  bool has(String mermaidCode, {bool isDark = false}) {
    return _cache.containsKey(_cacheKey(mermaidCode, isDark));
  }

  /// 清除所有缓存
  void clear() {
    _cache.clear();
  }

  /// 获取缓存大小
  int get size => _cache.length;
}
