import 'package:flutter/material.dart';
import '../design_system/apple_icons.dart';
import 'package:flutter_spinkit/flutter_spinkit.dart';
import '../models/conversation.dart';
import '../models/message.dart';
import '../design_system/design_tokens.dart';

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
    return Scaffold(
      appBar: AppBar(
        title: TextField(
          controller: _searchController,
          autofocus: true,
          decoration: const InputDecoration(
            hintText: '搜索会话和消息...',
            border: InputBorder.none,
            hintStyle: TextStyle(color: Colors.grey),
          ),
          style: const TextStyle(fontSize: 18),
          onChanged: _performSearch,
        ),
        actions: [
          if (_searchController.text.isNotEmpty)
            IconButton(
              icon: const Icon(AppleIcons.close),
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
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(AppleIcons.search, size: 80, color: Colors.grey.shade300),
          SizedBox(height: ChatBoxTokens.spacing.lg),
          Text(
            '搜索会话和消息',
            style: TextStyle(fontSize: 18, color: Colors.grey.shade600),
          ),
        ],
      ),
    );
  }

  Widget _buildNoResults() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(AppleIcons.searchOff, size: 80, color: Colors.grey.shade300),
          SizedBox(height: ChatBoxTokens.spacing.lg),
          Text(
            '未找到匹配结果',
            style: TextStyle(fontSize: 18, color: Colors.grey.shade600),
          ),
        ],
      ),
    );
  }

  Widget _buildResultTile(SearchResult result) {
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
                  ? AppleIcons.person
                  : AppleIcons.chatbot),
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
              style: TextStyle(
                fontSize: 11,
                color: Colors.grey.shade600,
                fontWeight: FontWeight.normal,
              ),
            ),
        ],
      ),
      subtitle: Text(
        result.highlightText,
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
      ),
      trailing: const Icon(Icons.arrow_forward_ios, size: 16),
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
      builder: (context) => AlertDialog(
        title: Row(
          children: [
            Icon(
              result.message!.isUser ? AppleIcons.person : AppleIcons.chatbot,
              size: 20,
            ),
            SizedBox(width: ChatBoxTokens.spacing.sm),
            Expanded(
              child: Text(
                result.message!.isUser ? '用户' : '助手',
                style: const TextStyle(fontSize: 18),
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
                padding: EdgeInsets.all(ChatBoxTokens.spacing.sm),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(ChatBoxTokens.radius.small),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.chat_bubble_outline, size: 16),
                    SizedBox(width: ChatBoxTokens.spacing.sm),
                    Expanded(
                      child: Text(
                        result.conversation.title,
                        style: const TextStyle(fontSize: 14),
                      ),
                    ),
                  ],
                ),
              ),
              SizedBox(height: ChatBoxTokens.spacing.lg),
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
      ),
    );
  }

  /// 构建高亮文本
  Widget _buildHighlightedText(String text, String keyword) {
    if (keyword.isEmpty) {
      return Text(text);
    }

    final lowerText = text.toLowerCase();
    final lowerKeyword = keyword.toLowerCase();
    final spans = <TextSpan>[];
    int currentIndex = 0;

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
          backgroundColor: Colors.yellow.shade300,
          fontWeight: FontWeight.bold,
          color: Colors.black,
        ),
      ));

      currentIndex = index + keyword.length;
    }

    return RichText(
      text: TextSpan(
        style: TextStyle(
          fontSize: 15,
          color: Theme.of(context).colorScheme.onSurface,
        ),
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

