import 'package:flutter/material.dart';

import '../chat_ui/owui/components/owui_card.dart';
import '../chat_ui/owui/owui_tokens_ext.dart';
import '../models/story_runtime.dart';

class StorySessionDrawer extends StatelessWidget {
  final List<RpStorySession> sessions;
  final String? currentSessionId;
  final ValueChanged<String> onSessionSelected;
  final VoidCallback onRefresh;

  const StorySessionDrawer({
    super.key,
    required this.sessions,
    required this.currentSessionId,
    required this.onSessionSelected,
    required this.onRefresh,
  });

  @override
  Widget build(BuildContext context) {
    final colors = context.owuiColors;
    final spacing = context.owuiSpacing;

    return Drawer(
      backgroundColor: colors.pageBg,
      child: Container(
        decoration: BoxDecoration(
          color: colors.pageBg,
          border: Border(right: BorderSide(color: colors.borderSubtle)),
        ),
        child: Column(
          children: [
            Padding(
              padding: EdgeInsets.fromLTRB(
                spacing.lg,
                MediaQuery.paddingOf(context).top + spacing.lg,
                spacing.lg,
                spacing.lg,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Longform Stories', style: Theme.of(context).textTheme.titleLarge),
                  SizedBox(height: spacing.xs),
                  Text(
                    '${sessions.length} 个 session',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: colors.textSecondary,
                        ),
                  ),
                ],
              ),
            ),
            Divider(height: 1, color: colors.borderSubtle),
            Expanded(
              child: ListView(
                padding: EdgeInsets.symmetric(vertical: spacing.sm),
                children: [
                  OwuiCard(
                    margin: EdgeInsets.symmetric(horizontal: spacing.md, vertical: spacing.xs),
                    child: ListTile(
                      leading: const Icon(Icons.refresh_outlined),
                      title: const Text('刷新列表'),
                      subtitle: const Text('从 backend 重新加载 story sessions'),
                      onTap: () {
                        Navigator.pop(context);
                        onRefresh();
                      },
                    ),
                  ),
                  if (sessions.isEmpty)
                    Padding(
                      padding: EdgeInsets.all(spacing.lg),
                      child: Text(
                        '当前还没有 active story session。先从 prestory setup 里 activate 一个 story。',
                        style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                              color: colors.textSecondary,
                            ),
                      ),
                    )
                  else
                    ...sessions.map((session) => _buildSessionTile(context, session)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSessionTile(BuildContext context, RpStorySession session) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    final isSelected = session.sessionId == currentSessionId;
    final selectedBg = Theme.of(context).colorScheme.primary.withValues(alpha: 0.10);

    return Container(
      margin: EdgeInsets.symmetric(horizontal: spacing.md, vertical: spacing.xs),
      decoration: BoxDecoration(
        color: isSelected ? selectedBg : Colors.transparent,
        borderRadius: BorderRadius.circular(context.owuiRadius.rLg),
      ),
      child: ListTile(
        leading: const Icon(Icons.menu_book_outlined),
        title: Text(
          session.storyId,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
              ),
        ),
        subtitle: Text(
          'Ch ${session.currentChapterIndex} · ${session.currentPhase}\n${session.sessionState}',
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: colors.textSecondary,
              ),
        ),
        trailing: isSelected ? const Icon(Icons.chevron_right) : null,
        onTap: () {
          onSessionSelected(session.sessionId);
          Navigator.pop(context);
        },
      ),
    );
  }
}
