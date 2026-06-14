/// INPUT: 图片 url + (可选) [Image #N] 序号
/// OUTPUT: OwuiImageViewer - 图片全屏查看器（翻转/旋转/缩放/重置/复制/下载）
/// POS: UI 层 / Markdown / Owui - 图片全屏查看器（lab 与生产共用）
///
/// 移植自 lab 验证场：对标基础全屏预览并增强工具栏。
/// 字节/解码/剪贴板逻辑复用 image_clipboard_win.dart。
library;

import 'dart:io' show File, Platform;
import 'dart:math' as math;

import 'package:cached_network_image/cached_network_image.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import 'image_clipboard_win.dart';

/// 统一圆角半径。
const double _kRadius = 10;

/// 图片全屏查看器：翻转/旋转/缩放/重置 + 复制(位图)/下载(file_picker)。
/// [index] > 0 时左上角显示 `[Image #N]`，0 则隐藏。
class OwuiImageViewer extends StatefulWidget {
  const OwuiImageViewer({
    super.key,
    required this.url,
    this.index = 0,
    this.caption,
  });

  final String url;
  final int index;

  /// 可选底部说明文字（如 AI 生成图的 revisedPrompt）。
  final String? caption;

  @override
  State<OwuiImageViewer> createState() => _OwuiImageViewerState();
}

class _OwuiImageViewerState extends State<OwuiImageViewer> {
  final TransformationController _tc = TransformationController();
  int _quarter = 0; // 顺时针 90° 步进(可负)
  bool _flipH = false;
  bool _flipV = false;

  @override
  void dispose() {
    _tc.dispose();
    super.dispose();
  }

  void _reset() => setState(() {
        _quarter = 0;
        _flipH = false;
        _flipV = false;
        _tc.value = Matrix4.identity();
      });

  // 缩放改 _tc.value 即触发 InteractiveViewer 重建(无需 setState)。
  void _zoom(double factor) =>
      _tc.value = _tc.value.clone()..scaleByDouble(factor, factor, factor, 1.0);

  void _toast(String msg) {
    final m = ScaffoldMessenger.maybeOf(context);
    m?.hideCurrentSnackBar();
    m?.showSnackBar(SnackBar(content: Text(msg)));
  }

  String _fileName() {
    final url = widget.url;
    if (url.startsWith('data:image')) {
      final ext =
          RegExp(r'data:image/(\w+)').firstMatch(url)?.group(1) ?? 'png';
      return 'image_${widget.index > 0 ? widget.index : 1}.$ext';
    }
    final file = resolveLocalImageFile(url);
    if (file != null) return file.uri.pathSegments.last;
    final seg = Uri.tryParse(url)?.pathSegments;
    if (seg != null && seg.isNotEmpty && seg.last.isNotEmpty) return seg.last;
    return 'image.png';
  }

  // 复制：dart:ui 解码图片→RGBA，转 BGRA 写入 Windows 剪贴板(CF_DIBV5)。
  // 直接调系统 API(win32 FFI)，无第三方剪贴板框架；仅 Windows 验证。
  Future<void> _copy() async {
    try {
      final bytes = await loadImageBytes(widget.url);
      if (bytes == null) {
        _toast('复制失败：无法读取图片');
        return;
      }
      if (!Platform.isWindows) {
        _toast('位图复制目前仅在 Windows 验证');
        return;
      }
      final decoded = await decodeImageRgba(bytes);
      if (decoded == null) {
        _toast('复制失败：图片解码失败');
        return;
      }
      final ok = setClipboardImageDibv5(decoded.$1, decoded.$2, decoded.$3);
      if (mounted) _toast(ok ? '已复制图片到剪贴板' : '复制失败：写入剪贴板失败');
    } catch (e) {
      if (mounted) _toast('复制失败：$e');
    }
  }

  Future<void> _download() async {
    try {
      final bytes = await loadImageBytes(widget.url);
      if (bytes == null) {
        _toast('下载失败：无法读取图片');
        return;
      }
      final path = await FilePicker.platform.saveFile(
        dialogTitle: '保存图片',
        fileName: _fileName(),
        bytes: bytes,
      );
      if (path == null) return; // 用户取消
      await File(path).writeAsBytes(bytes); // 桌面端兜底写入
      if (mounted) _toast('已保存到 $path');
    } catch (e) {
      if (mounted) _toast('下载失败：$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Stack(
          children: [
            Positioned.fill(
              child: InteractiveViewer(
                transformationController: _tc,
                minScale: 0.5,
                maxScale: 5,
                child: Center(
                  child: Transform(
                    alignment: Alignment.center,
                    transform: Matrix4.identity()
                      ..rotateZ(_quarter * math.pi / 2)
                      ..scaleByDouble(
                          _flipH ? -1.0 : 1.0, _flipV ? -1.0 : 1.0, 1.0, 1.0),
                    child: _fullImage(),
                  ),
                ),
              ),
            ),
            Positioned(
              top: 8,
              left: 12,
              right: 12,
              child: Row(
                children: [
                  if (widget.index > 0)
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 4),
                      decoration: BoxDecoration(
                        color: Colors.black54,
                        borderRadius: BorderRadius.circular(_kRadius),
                      ),
                      child: Text('[Image #${widget.index}]',
                          style: const TextStyle(
                              color: Colors.white, fontSize: 13)),
                    ),
                  const Spacer(),
                  _btn(Icons.close, '关闭', () => Navigator.of(context).pop()),
                ],
              ),
            ),
            if (widget.caption != null && widget.caption!.trim().isNotEmpty)
              Positioned(
                left: 12,
                right: 12,
                bottom: 72,
                child: Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.black.withValues(alpha: 0.7),
                    borderRadius: BorderRadius.circular(_kRadius),
                  ),
                  child: Text(
                    widget.caption!,
                    style: const TextStyle(color: Colors.white, fontSize: 12),
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ),
            Positioned(
              left: 0,
              right: 0,
              bottom: 16,
              child: Center(child: _toolbar()),
            ),
          ],
        ),
      ),
    );
  }

  Widget _fullImage() {
    final url = widget.url;
    final bytes = decodeImageDataUri(url);
    if (bytes != null) return Image.memory(bytes, fit: BoxFit.contain);
    if (url.toLowerCase().endsWith('.svg')) {
      if (url.startsWith('http://') || url.startsWith('https://')) {
        return SvgPicture.network(url, fit: BoxFit.contain);
      }
      final f = resolveLocalImageFile(url);
      if (f != null) return SvgPicture.file(f, fit: BoxFit.contain);
      return SvgPicture.asset(url, fit: BoxFit.contain);
    }
    final file = resolveLocalImageFile(url);
    if (file != null) return Image.file(file, fit: BoxFit.contain);
    if (url.startsWith('http://') || url.startsWith('https://')) {
      return CachedNetworkImage(imageUrl: url, fit: BoxFit.contain);
    }
    return Image.asset(url, fit: BoxFit.contain);
  }

  Widget _toolbar() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(_kRadius),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _btn(Icons.swap_vert, '垂直翻转',
              () => setState(() => _flipV = !_flipV)),
          _btn(Icons.swap_horiz, '水平翻转',
              () => setState(() => _flipH = !_flipH)),
          _btn(Icons.rotate_left, '逆时针 90°',
              () => setState(() => _quarter--)),
          _btn(Icons.rotate_right, '顺时针 90°',
              () => setState(() => _quarter++)),
          _btn(Icons.zoom_out, '缩小', () => _zoom(0.8)),
          _btn(Icons.zoom_in, '放大', () => _zoom(1.25)),
          _btn(Icons.restart_alt, '重置', _reset),
          _btn(Icons.content_copy, '复制', _copy),
          _btn(Icons.download, '下载', _download),
        ],
      ),
    );
  }

  Widget _btn(IconData icon, String tip, VoidCallback onTap) => IconButton(
        tooltip: tip,
        iconSize: 22,
        color: Colors.white,
        icon: Icon(icon),
        onPressed: onTap,
      );
}
