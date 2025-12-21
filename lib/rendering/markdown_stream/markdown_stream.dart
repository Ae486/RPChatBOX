/// MarkStream Flutter - 流式 Markdown 渲染库
/// 
/// 提供高性能的流式 Markdown 渲染能力，专为 AI 聊天场景优化。
/// 
/// ## 核心组件
/// 
/// - [StablePrefixParser]: 稳定前缀解析器
/// - [StreamMarkdownConfig]: 渲染配置
/// 
/// ## 使用示例
/// 
/// ```dart
/// import 'package:chatboxapp/rendering/markdown_stream/markdown_stream.dart';
/// 
/// final parser = StablePrefixParser();
/// final result = parser.split(markdownText);
/// // result.stable - 可安全渲染的部分
/// // result.tail - 可能未闭合的尾部
/// ```
library;

export 'stable_prefix_parser.dart';
export 'stream_markdown_config.dart';
export 'batch_render_controller.dart';
export 'viewport_priority.dart';
export 'language_utils.dart';
