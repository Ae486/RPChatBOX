import 'dart:io';
import '../chat_ui/owui/owui_icons.dart';
import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter_spinkit/flutter_spinkit.dart';

/// 缓存图片组件
///
/// 支持本地文件和网络图片显示，自动缓存以提升性能
class CachedImageWidget extends StatelessWidget {
  final String path;
  final BoxFit? fit;
  final double? width;
  final double? height;
  final Widget Function(BuildContext, Object, StackTrace?)? errorBuilder;
  final Widget? placeholder;

  const CachedImageWidget({
    super.key,
    required this.path,
    this.fit,
    this.width,
    this.height,
    this.errorBuilder,
    this.placeholder,
  });

  @override
  Widget build(BuildContext context) {
    // 判断是网络图片还是本地文件
    if (path.startsWith('http://') || path.startsWith('https://')) {
      // 网络图片：使用 CachedNetworkImage
      return CachedNetworkImage(
        imageUrl: path,
        width: width,
        height: height,
        fit: fit ?? BoxFit.cover,
        placeholder: placeholder != null 
            ? (context, url) => placeholder!
            : (context, url) => Container(
                color: Colors.grey.shade200,
                child: Center(
                  child: SpinKitFadingCircle(
                    color: Colors.grey.shade400,
                    size: 40.0,
                  ),
                ),
              ),
        errorWidget: errorBuilder != null
            ? (context, url, error) => errorBuilder!(context, error, null)
            : (context, url, error) => Container(
                color: Colors.grey.shade300,
                child: const Icon(
                  OwuiIcons.imageOff,
                  color: Colors.grey,
                  size: 48,
                ),
              ),
      );
    } else {
      // 本地文件：使用 Image.file（Flutter 已有内存缓存）
      // 这里只需要补充错误处理
      final file = File(path);
      
      return Image.file(
        file,
        width: width,
        height: height,
        fit: fit ?? BoxFit.cover,
        // 使用缓存策略
        cacheWidth: width?.toInt(),
        cacheHeight: height?.toInt(),
        errorBuilder: errorBuilder ??
            (context, error, stackTrace) => Container(
                  width: width,
                  height: height,
                  color: Colors.grey.shade300,
                  child: const Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        OwuiIcons.imageOff,
                        color: Colors.grey,
                        size: 48,
                      ),
                      SizedBox(height: 8),
                      Text(
                        '图片加载失败',
                        style: TextStyle(
                          color: Colors.grey,
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ),
                ),
      );
    }
  }
}


