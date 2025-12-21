part of '../flyer_chat_demo_page.dart';

/// Admonition 类型
enum AdmonitionKind {
  note,
  info,
  tip,
  warning,
  danger,
  caution,
  error,
}

/// Admonition 配置
class AdmonitionConfig {
  final Color borderColor;
  final Color headerBgColor;
  final Color headerTextColor;
  final Color contentBgColor;
  final IconData icon;
  final String defaultTitle;

  const AdmonitionConfig({
    required this.borderColor,
    required this.headerBgColor,
    required this.headerTextColor,
    required this.contentBgColor,
    required this.icon,
    required this.defaultTitle,
  });
}

/// 获取 Admonition 配置
/// 参考 markstream-vue: src/components/AdmonitionNode/AdmonitionNode.vue
AdmonitionConfig _getAdmonitionConfig(AdmonitionKind kind, bool isDark) {
  switch (kind) {
    case AdmonitionKind.note:
    case AdmonitionKind.info:
      return AdmonitionConfig(
        borderColor: const Color(0xFF448AFF),
        headerBgColor: isDark 
            ? const Color(0xFF448AFF).withValues(alpha: 0.12)
            : const Color(0xFF448AFF).withValues(alpha: 0.06),
        headerTextColor: const Color(0xFF448AFF),
        contentBgColor: isDark ? const Color(0xFF0B1220) : const Color(0xFFF8F8F8),
        icon: Icons.info_outline_rounded,
        defaultTitle: kind == AdmonitionKind.note ? 'Note' : 'Info',
      );
    case AdmonitionKind.tip:
      return AdmonitionConfig(
        borderColor: const Color(0xFF00BFA5),
        headerBgColor: isDark 
            ? const Color(0xFF00BFA5).withValues(alpha: 0.12)
            : const Color(0xFF00BFA5).withValues(alpha: 0.06),
        headerTextColor: const Color(0xFF00BFA5),
        contentBgColor: isDark ? const Color(0xFF0B1220) : const Color(0xFFF8F8F8),
        icon: Icons.lightbulb_outline_rounded,
        defaultTitle: 'Tip',
      );
    case AdmonitionKind.warning:
    case AdmonitionKind.caution:
      return AdmonitionConfig(
        borderColor: const Color(0xFFFF9100),
        headerBgColor: isDark 
            ? const Color(0xFFFF9100).withValues(alpha: 0.12)
            : const Color(0xFFFF9100).withValues(alpha: 0.06),
        headerTextColor: const Color(0xFFFF9100),
        contentBgColor: isDark ? const Color(0xFF0B1220) : const Color(0xFFF8F8F8),
        icon: Icons.warning_amber_rounded,
        defaultTitle: kind == AdmonitionKind.warning ? 'Warning' : 'Caution',
      );
    case AdmonitionKind.danger:
    case AdmonitionKind.error:
      return AdmonitionConfig(
        borderColor: const Color(0xFFFF5252),
        headerBgColor: isDark 
            ? const Color(0xFFFF5252).withValues(alpha: 0.12)
            : const Color(0xFFFF5252).withValues(alpha: 0.06),
        headerTextColor: const Color(0xFFFF5252),
        contentBgColor: isDark ? const Color(0xFF0B1220) : const Color(0xFFF8F8F8),
        icon: Icons.error_outline_rounded,
        defaultTitle: kind == AdmonitionKind.danger ? 'Danger' : 'Error',
      );
  }
}

/// 解析 Admonition 类型
AdmonitionKind? _parseAdmonitionKind(String? kindStr) {
  if (kindStr == null || kindStr.isEmpty) return null;
  final lower = kindStr.toLowerCase().trim();
  switch (lower) {
    case 'note': return AdmonitionKind.note;
    case 'info': return AdmonitionKind.info;
    case 'tip': return AdmonitionKind.tip;
    case 'warning': return AdmonitionKind.warning;
    case 'danger': return AdmonitionKind.danger;
    case 'caution': return AdmonitionKind.caution;
    case 'error': return AdmonitionKind.error;
    default: return null;
  }
}

/// Admonition 提示框组件
/// 
/// 支持 note, info, tip, warning, danger, caution, error 类型
/// 支持可选的折叠功能
class _AdmonitionWidget extends StatefulWidget {
  final AdmonitionKind kind;
  final String? title;
  final Widget content;
  final bool isDark;
  final bool collapsible;
  final bool initiallyOpen;

  const _AdmonitionWidget({
    required this.kind,
    this.title,
    required this.content,
    required this.isDark,
    this.collapsible = false,
    this.initiallyOpen = true,
  });

  @override
  State<_AdmonitionWidget> createState() => _AdmonitionWidgetState();
}

class _AdmonitionWidgetState extends State<_AdmonitionWidget> {
  late bool _isOpen;

  @override
  void initState() {
    super.initState();
    _isOpen = widget.initiallyOpen;
  }

  @override
  Widget build(BuildContext context) {
    final config = _getAdmonitionConfig(widget.kind, widget.isDark);
    final displayTitle = widget.title?.isNotEmpty == true 
        ? widget.title! 
        : config.defaultTitle;

    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      decoration: BoxDecoration(
        color: config.contentBgColor,
        borderRadius: BorderRadius.circular(4),
        border: Border(
          left: BorderSide(
            color: config.borderColor,
            width: 4,
          ),
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Header
          GestureDetector(
            onTap: widget.collapsible ? () => setState(() => _isOpen = !_isOpen) : null,
            behavior: HitTestBehavior.opaque,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              color: config.headerBgColor,
              child: Row(
                children: [
                  Icon(
                    config.icon,
                    size: 18,
                    color: config.headerTextColor,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      displayTitle,
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                        color: config.headerTextColor,
                      ),
                    ),
                  ),
                  if (widget.collapsible)
                    Icon(
                      _isOpen ? Icons.expand_less : Icons.expand_more,
                      size: 20,
                      color: config.headerTextColor,
                    ),
                ],
              ),
            ),
          ),
          // Content
          if (_isOpen)
            Padding(
              padding: const EdgeInsets.all(12),
              child: widget.content,
            ),
        ],
      ),
    );
  }
}

/// 从 blockquote 内容检测 Admonition
/// 
/// 支持格式:
/// > [!NOTE]
/// > Content here
/// 
/// > [!TIP] Custom Title
/// > Content here
({AdmonitionKind? kind, String? title, String content})? _detectAdmonition(String text) {
  final lines = text.split('\n');
  if (lines.isEmpty) return null;
  
  final firstLine = lines.first.trim();
  
  // 匹配 [!TYPE] 或 [!TYPE] Title
  final match = RegExp(r'^\[!(\w+)\]\s*(.*)$').firstMatch(firstLine);
  if (match == null) return null;
  
  final kindStr = match.group(1);
  final title = match.group(2)?.trim();
  final kind = _parseAdmonitionKind(kindStr);
  
  if (kind == null) return null;
  
  // 剩余内容
  final content = lines.skip(1).join('\n').trim();
  
  return (kind: kind, title: title?.isEmpty == true ? null : title, content: content);
}
