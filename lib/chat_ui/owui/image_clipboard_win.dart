/// INPUT: 图片 url/字节（dataURI / 本地路径 / 网络）
/// OUTPUT: 图片字节加载、RGBA 解码、Windows 位图剪贴板写入
/// POS: UI 层 / Markdown / Owui - 图片字节与剪贴板工具（lab 与生产共用）
///
/// 纯系统 API(win32 FFI) 实现位图复制，无第三方剪贴板框架。
/// 来源解析与 markdown.dart 内联图分支保持一致(dataURI / 本地文件 / 网络)。
library;

import 'dart:convert' show base64Decode;
import 'dart:ffi' hide Size;
import 'dart:io' show File;
import 'dart:typed_data' show Uint8List;
import 'dart:ui' as ui;

import 'package:http/http.dart' as http;
import 'package:win32/win32.dart'
    show
        GlobalAlloc,
        GlobalLock,
        GlobalUnlock,
        GlobalFree,
        OpenClipboard,
        EmptyClipboard,
        SetClipboardData,
        CloseClipboard,
        BITMAPV5HEADER,
        CF_DIBV5,
        BI_BITFIELDS,
        GMEM_MOVEABLE,
        GMEM_ZEROINIT;

/// 解析 data URI(image)；非 base64 image 返回 null。
Uint8List? decodeImageDataUri(String raw) {
  if (!raw.startsWith('data:image')) return null;
  final comma = raw.indexOf(',');
  if (comma == -1) return null;
  if (!raw.substring(0, comma).contains(';base64')) return null;
  try {
    return base64Decode(raw.substring(comma + 1));
  } catch (_) {
    return null;
  }
}

/// 解析本地文件路径(file:// / Windows 盘符 / UNC / 无 scheme)；网络/其他 scheme 返回 null。
File? resolveLocalImageFile(String raw) {
  final uri = Uri.tryParse(raw);
  if (uri != null && uri.scheme == 'file') {
    try {
      return File.fromUri(uri);
    } catch (_) {
      return null;
    }
  }
  if (raw.startsWith('http://') || raw.startsWith('https://')) return null;
  if (RegExp(r'^[a-zA-Z]:[\\/]').hasMatch(raw)) return File(raw); // C:\ 或 C:/
  if (raw.startsWith(r'\\')) return File(raw); // UNC
  if (uri != null && uri.hasScheme) return null; // 其他 scheme 不当本地
  return File(raw); // 无 scheme 的相对/绝对路径
}

/// 读取图片字节(供复制/下载)：dataURI→decode；本地→readAsBytes；网络→http get。
Future<Uint8List?> loadImageBytes(String url) async {
  final data = decodeImageDataUri(url);
  if (data != null) return data;
  final file = resolveLocalImageFile(url);
  if (file != null) {
    try {
      if (await file.exists()) return await file.readAsBytes();
    } catch (_) {}
    return null;
  }
  if (url.startsWith('http://') || url.startsWith('https://')) {
    try {
      final resp = await http.get(Uri.parse(url));
      if (resp.statusCode == 200) return resp.bodyBytes;
    } catch (_) {}
  }
  return null;
}

/// 解码图片字节为 RGBA 像素 + 宽高(dart:ui，无第三方解码器)。
Future<(Uint8List, int, int)?> decodeImageRgba(Uint8List bytes) async {
  try {
    final codec = await ui.instantiateImageCodec(bytes);
    final frame = await codec.getNextFrame();
    final image = frame.image;
    final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
    final w = image.width;
    final h = image.height;
    image.dispose();
    codec.dispose();
    if (data == null) return null;
    return (data.buffer.asUint8List(), w, h);
  } catch (_) {
    return null;
  }
}

/// 把 RGBA 像素写入 Windows 剪贴板(CF_DIBV5)。仅 Windows，直接调 Win32 API，无第三方框架。
/// 正确点(对比 image_clipboard 的缺陷)：用设备无关位图 DIBV5(非 DDB)、像素 BGRA、
/// bottom-up 行序、句柄交给系统后不释放。
/// 注：dart:ui rawRgba 为预乘 alpha，对不透明图无影响(半透明 png 颜色略偏，可接受)。
bool setClipboardImageDibv5(Uint8List rgba, int width, int height) {
  final headerSize = sizeOf<BITMAPV5HEADER>(); // 124
  final pixelSize = width * height * 4;
  final hGlobal =
      GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, headerSize + pixelSize);
  if (hGlobal == nullptr) return false;
  final ptr = GlobalLock(hGlobal);
  if (ptr == nullptr) {
    GlobalFree(hGlobal);
    return false;
  }
  try {
    final header = ptr.cast<BITMAPV5HEADER>().ref;
    header.bV5Size = headerSize;
    header.bV5Width = width;
    header.bV5Height = height; // 正值 = bottom-up(兼容性最好)
    header.bV5Planes = 1;
    header.bV5BitCount = 32;
    header.bV5Compression = BI_BITFIELDS;
    header.bV5SizeImage = pixelSize;
    header.bV5RedMask = 0x00FF0000;
    header.bV5GreenMask = 0x0000FF00;
    header.bV5BlueMask = 0x000000FF;
    header.bV5AlphaMask = 0xFF000000;
    header.bV5CSType = 0x73524742; // 'sRGB'，令系统忽略 Endpoints/Gamma
    // RGBA(top-down) → BGRA(bottom-up)
    final dst = (ptr.cast<Uint8>() + headerSize).asTypedList(pixelSize);
    for (var y = 0; y < height; y++) {
      final srcRow = (height - 1 - y) * width * 4;
      final dstRow = y * width * 4;
      for (var x = 0; x < width; x++) {
        final s = srcRow + x * 4;
        final d = dstRow + x * 4;
        dst[d] = rgba[s + 2]; // B
        dst[d + 1] = rgba[s + 1]; // G
        dst[d + 2] = rgba[s]; // R
        dst[d + 3] = rgba[s + 3]; // A
      }
    }
  } finally {
    GlobalUnlock(hGlobal);
  }
  if (OpenClipboard(0) == 0) {
    GlobalFree(hGlobal);
    return false;
  }
  EmptyClipboard();
  final ok = SetClipboardData(CF_DIBV5, hGlobal.address);
  CloseClipboard();
  if (ok == 0) {
    GlobalFree(hGlobal); // 系统未接管，释放
    return false;
  }
  return true; // 成功后所有权归系统，不释放
}
