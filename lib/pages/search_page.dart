import 'package:flutter/material.dart';
import 'package:flutter_spinkit/flutter_spinkit.dart';

import '../chat_ui/owui/components/owui_app_bar.dart';
import '../chat_ui/owui/components/owui_dialog.dart';
import '../chat_ui/owui/components/owui_scaffold.dart';
import '../chat_ui/owui/components/owui_text_field.dart';
import '../chat_ui/owui/owui_icons.dart';
import '../chat_ui/owui/owui_tokens_ext.dart';
import '../models/conversation.dart';
import '../models/message.dart';

/// 搜索页面
class SearchPage extends StatefulWidget {
  final List<Conversation> conversations;
  final Function(String conversationId, String? messageId) onResultTap;

  const SearchPage({
    super.key,
    required this.conversations,
    required this.onResultTap,
  });

  @override
  State<SearchPage> createState() => _SearchPageState();
}

class _SearchPageState extends State<SearchPage> {
  final _searchController = TextEditingController();
  List<SearchResult> _results = [];
  bool _isSearching = false;

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  /// 执行搜索
  void _performSearch(String query) {
    if (query.trim().isEmpty) {
      setState(() {
        _results = [];
        _isSearching = false;
      });
      return;
    }

    setState(() {
      _isSearching = true;
      _results = [];
    });

    final lowerQuery = query.toLowerCase();
    final results = <SearchResult>[];

    // 搜索所有会话
    for (var conversation in widget.conversations) {
      // 搜索会话标题
      if (conversation.title.toLowerCase().contains(lowerQuery)) {
        results.add(SearchResult(
          conversation: conversation,
          type: SearchResultType.conversationTitle,
          highlightText: conversation.title,
        ));
      }

      // 搜索消息内容
      for (var message in conversation.messages) {
        if (message.content.toLowerCase().contains(lowerQuery)) {
          results.add(SearchResult(
            conversation: conversation,
            message: message,
            type: SearchResultType.messageContent,
            highlightText: _getSnippet(message.content, lowerQuery),
          ));
        }
      }
    }

    setState(() {
      _results = results;
      _isSearching = false;
    });
  }

  /// 获取搜索结果片段
  String _getSnippet(String content, String query) {
    final index = content.toLowerCase().indexOf(query.toLowerCase());
    if (index == -1) return content.substring(0, 100.clamp(0, content.length));

    final start = (index - 50).clamp(0, content.length);
    final end = (index + query.length + 50).clamp(0, content.length);

    String snippet = content.substring(start, end);
    if (start > 0) snippet = '...$snippet';
    if (end < content.length) snippet = '$snippet...';

    return snippet;
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.owuiColors;

    return OwuiScaffold(
      appBar: OwuiAppBar(
        title: OwuiSearchField(
          controller: _searchController,
          autofocus: true,
          hintText: '搜索会话和消息...',
          onChanged: _performSearch,
        ),
        actions: [
          if (_searchController.text.isNotEmpty)
            IconButton(
              tooltip: '清除',
              icon: Icon(
                OwuiIcons.close,
                color: colors.textSecondary,
              ),
              onPressed: () {
                _searchController.clear();
                _performSearch('');
              },
            ),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_searchController.text.trim().isEmpty) {
      return _buildEmptyState();
    }

    if (_isSearching) {
      return Center(
        child: SpinKitThreeBounce(
          color: Theme.of(context).colorScheme.primary,
          size: 30.0,
        ),
      );
    }

    if (_results.isEmpty) {
      return _buildNoResults();
    }

    return ListView.builder(
      itemCount: _results.length,
      itemBuilder: (context, index) {
        final result = _results[index];
        return _buildResultTile(result);
      },
    );
  }

  Widget _buildEmptyState() {
    final colors = context.owuiColors;
    final spacing = context.owuiSpacing;
    final theme = Theme.of(context);

    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            OwuiIcons.search,
            size: 80,
            color: colors.textSecondary.withValues(alpha: 0.35),
          ),
          SizedBox(height: spacing.lg),
          Text(
            '搜索会话和消息',
            style: (theme.textTheme.titleMedium ?? const TextStyle())
                .copyWith(color: colors.textSecondary),
          ),
        ],
      ),
    );
  }

  Widget _buildNoResults() {
    final colors = context.owuiColors;
    final spacing = context.owuiSpacing;
    final theme = Theme.of(context);

    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            OwuiIcons.searchOff,
            size: 80,
            color: colors.textSecondary.withValues(alpha: 0.35),
          ),
          SizedBox(height: spacing.lg),
          Text(
            '未找到匹配结果',
            style: (theme.textTheme.titleMedium ?? const TextStyle())
                .copyWith(color: colors.textSecondary),
          ),
        ],
      ),
    );
  }

  Widget _buildResultTile(SearchResult result) {
    final colors = context.owuiColors;
    final theme = Theme.of(context);

    // 格式化时间
    String timeText = '';
    if (result.message != null) {
      final time = result.message!.timestamp;
      timeText = '${time.year}-${_pad(time.month)}-${_pad(time.day)} '
          '${_pad(time.hour)}:${_pad(time.minute)}:${_pad(time.second)}';
    }

    return ListTile(
      leading: CircleAvatar(
        child: Icon(
          result.type == SearchResultType.conversationTitle
              ? Icons.chat_bubble_outline
              : (result.message?.isUser ?? false
                  ? OwuiIcons.person
                  : OwuiIcons.chatbot),
        ),
      ),
      title: Row(
        children: [
          Expanded(
            child: Text(
              result.conversation.title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          if (timeText.isNotEmpty)
            Text(
              timeText,
              style: (theme.textTheme.labelSmall ?? const TextStyle())
                  .copyWith(color: colors.textSecondary),
            ),
        ],
      ),
      subtitle: Text(
        result.highlightText,
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
      ),
      trailing: Icon(
        OwuiIcons.chevronRight,
        size: 18,
        color: colors.textSecondary,
      ),
      onTap: () => _showMessagePreview(result),
    );
  }

  /// 补零辅助函数
  String _pad(int n) => n.toString().padLeft(2, '0');

  /// 显示消息预览对话框
  void _showMessagePreview(SearchResult result) {
    if (result.message == null) {
      // 如果是会话标题搜索，直接跳转
      Navigator.pop(context);
      widget.onResultTap(result.conversation.id, null);
      return;
    }

    showDialog(
      context: context,
      builder: (context) {
        final colors = context.owuiColors;
        final spacing = context.owuiSpacing;
        final radius = context.owuiRadius;
        final theme = Theme.of(context);

        return OwuiDialog(
          title: Row(
            children: [
              Icon(
                result.message!.isUser ? OwuiIcons.person : OwuiIcons.chatbot,
                size: 20,
              ),
              SizedBox(width: spacing.sm),
              Expanded(
                child: Text(
                  result.message!.isUser ? '用户' : '助手',
                  style: theme.textTheme.titleMedium,
                ),
              ),
            ],
          ),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // 会话信息
                Container(
                  padding: EdgeInsets.all(spacing.sm),
                  decoration: BoxDecoration(
                    color: colors.surface2,
                    borderRadius: BorderRadius.circular(radius.rLg),
                    border: Border.all(color: colors.borderSubtle),
                  ),
                  child: Row(
                    children: [
                      Icon(
                        Icons.chat_bubble_outline,
                        size: 16,
                        color: colors.textSecondary,
                      ),
                      SizedBox(width: spacing.sm),
                      Expanded(
                        child: Text(
                          result.conversation.title,
                          style: theme.textTheme.bodyMedium,
                        ),
                      ),
                    ],
                  ),
                ),
                SizedBox(height: spacing.lg),
                // 消息内容（高亮关键词）
                _buildHighlightedText(
                  result.message!.content,
                  _searchController.text,
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('返回'),
            ),
            ElevatedButton.icon(
              onPressed: () {
                Navigator.pop(context); // 关闭预览
                Navigator.pop(context); // 关闭搜索页
                widget.onResultTap(
                  result.conversation.id,
                  result.message!.id,
                );
              },
              icon: const Icon(Icons.my_location),
              label: const Text('跳转到消息'),
            ),
          ],
        );
      },
    );
  }

  /// 构建高亮文本
  Widget _buildHighlightedText(String text, String keyword) {
    final colors = context.owuiColors;
    final theme = Theme.of(context);

    if (keyword.isEmpty) {
      return Text(text);
    }

    final lowerText = text.toLowerCase();
    final lowerKeyword = keyword.toLowerCase();
    final spans = <TextSpan>[];
    int currentIndex = 0;

    final highlightBg = theme.colorScheme.primary.withValues(alpha: 0.18);
    final highlightFg = theme.colorScheme.primary;

    while (currentIndex < text.length) {
      final index = lowerText.indexOf(lowerKeyword, currentIndex);

      if (index == -1) {
        // 没有更多匹配，添加剩余文本
        spans.add(TextSpan(text: text.substring(currentIndex)));
        break;
      }

      // 添加匹配前的文本
      if (index > currentIndex) {
        spans.add(TextSpan(text: text.substring(currentIndex, index)));
      }

      // 添加高亮的匹配文本
      spans.add(TextSpan(
        text: text.substring(index, index + keyword.length),
        style: TextStyle(
          backgroundColor: highlightBg,
          fontWeight: FontWeight.bold,
          color: highlightFg,
        ),
      ));

      currentIndex = index + keyword.length;
    }

    final baseStyle = theme.textTheme.bodyMedium ?? const TextStyle();

    return RichText(
      text: TextSpan(
        style: baseStyle.copyWith(color: colors.textPrimary),
        children: spans,
      ),
    );
  }
}

/// 搜索结果类型
enum SearchResultType {
  conversationTitle,
  messageContent,
}

/// 搜索结果
class SearchResult {
  final Conversation conversation;
  final Message? message;
  final SearchResultType type;
  final String highlightText;

  SearchResult({
    required this.conversation,
    this.message,
    required this.type,
    required this.highlightText,
  });
}
