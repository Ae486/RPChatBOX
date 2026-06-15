// owui_smooth_image.dart —— 图片渲染（part of owui_smooth_markdown）
part of 'owui_smooth_markdown.dart';

/// 按出现顺序提取 markdown 图片 url(供 [Image #N] 序号；含重复)。
List<String> _extractImageUrls(String md) {
  final re = RegExp(r'!\[[^\]]*\]\(\s*([^\s)]+)');
  return re.allMatches(md).map((m) => m.group(1) ?? '').toList();
}

/// 图片渲染：补齐框架 imageBuilder 默认缺失的「本地文件 / data URI」。
/// 来源顺序：data URI → SVG → 本地文件 → 网络 → asset。点击进入 OwuiImageViewer 全屏。
/// 字节/解码/剪贴板与全屏查看器复用 owui 共享实现(image_clipboard_win / owui_image_viewer)。
class _SmoothImage extends StatelessWidget {
  const _SmoothImage({required this.url, this.alt, this.index = 0});

  final String url;
  final String? alt;
  final int index;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: MouseRegion(
        cursor: SystemMouseCursors.click,
        child: GestureDetector(
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute<void>(
              fullscreenDialog: true,
              builder: (_) => OwuiImageViewer(url: url, index: index),
            ),
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(_kRadius),
            child: ConstrainedBox(
              constraints:
                  const BoxConstraints(maxWidth: 480, maxHeight: 400),
              child: _content(context),
            ),
          ),
        ),
      ),
    );
  }

  Widget _content(BuildContext context) {
    // 1) data URI: data:image/...;base64,xxx → Image.memory(框架默认缺失)
    final bytes = decodeImageDataUri(url);
    if (bytes != null) {
      return Image.memory(bytes,
          fit: BoxFit.contain, errorBuilder: (_, __, ___) => _error(context));
    }
    // 2) SVG(网络/本地/asset) → flutter_svg(框架同款依赖)
    if (url.toLowerCase().endsWith('.svg')) return _svg(context);
    // 3) 本地文件(file:// / Windows 盘符 / UNC / 无 scheme) → Image.file(框架默认缺失)
    final file = resolveLocalImageFile(url);
    if (file != null) {
      return Image.file(file,
          fit: BoxFit.contain, errorBuilder: (_, __, ___) => _error(context));
    }
    // 4) 网络位图 → CachedNetworkImage(框架同款依赖，带缓存)
    if (url.startsWith('http://') || url.startsWith('https://')) {
      return CachedNetworkImage(
        imageUrl: url,
        fit: BoxFit.contain,
        placeholder: (_, __) => _placeholder(),
        errorWidget: (_, __, ___) => _error(context),
      );
    }
    // 5) 兜底 asset
    return Image.asset(url,
        fit: BoxFit.contain, errorBuilder: (_, __, ___) => _error(context));
  }

  Widget _svg(BuildContext context) {
    if (url.startsWith('http://') || url.startsWith('https://')) {
      return SvgPicture.network(url, placeholderBuilder: (_) => _placeholder());
    }
    final file = resolveLocalImageFile(url);
    if (file != null) {
      return SvgPicture.file(file, placeholderBuilder: (_) => _placeholder());
    }
    return SvgPicture.asset(url, placeholderBuilder: (_) => _placeholder());
  }

  Widget _placeholder() => const SizedBox(
        width: 120,
        height: 90,
        child: Center(
          child: SizedBox(
            width: 22,
            height: 22,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
        ),
      );

  Widget _error(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final bg = dark ? Colors.white10 : Colors.black12;
    final fg = dark ? Colors.white54 : Colors.black45;
    final label = (alt ?? '').trim();
    return Container(
      width: 160,
      padding: const EdgeInsets.all(12),
      color: bg,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.broken_image_outlined, size: 28, color: fg),
          if (label.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(label,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 12, color: fg)),
          ],
        ],
      ),
    );
  }
}
