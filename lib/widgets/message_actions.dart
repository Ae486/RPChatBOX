import 'package:flutter/material.dart';
import '../design_system/apple_icons.dart';
import '../design_system/design_tokens.dart';

/// 消息操作按钮组件
class MessageActions extends StatelessWidget {
  final bool isUser;
  final VoidCallback onCopy;
  final VoidCallback onRegenerate; // 现在总是有重新生成
  final VoidCallback onEdit;
  final VoidCallback? onExport;
  final VoidCallback onDelete;

  const MessageActions({
    super.key,
    required this.isUser,
    required this.onCopy,
    required this.onRegenerate,
    required this.onEdit,
    this.onExport,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: EdgeInsets.only(top: ChatBoxTokens.spacing.xs),
      child: Wrap(
        spacing: ChatBoxTokens.spacing.sm,
        children: [
          // 复制
          _buildActionButton(
            context,
            icon: AppleIcons.copy,
            label: '复制',
            onPressed: onCopy,
          ),
          
          // 重新生成（所有消息都有）
          _buildActionButton(
            context,
            icon: Icons.refresh,
            label: '重新生成',
            onPressed: onRegenerate,
          ),
          
          // 编辑
          _buildActionButton(
            context,
            icon: AppleIcons.edit,
            label: '编辑',
            onPressed: onEdit,
          ),
          
          // 导出（仅AI消息）
          if (onExport != null)
            _buildActionButton(
              context,
              icon: AppleIcons.download,
              label: '导出',
              onPressed: onExport!,
            ),
          
          // 删除
          _buildActionButton(
            context,
            icon: AppleIcons.delete,
            label: '删除',
            onPressed: onDelete,
          ),
        ],
      ),
    );
  }

  Widget _buildActionButton(
    BuildContext context, {
    required IconData icon,
    required String label,
    required VoidCallback onPressed,
  }) {
    final color = Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.6);

    return Tooltip(
      message: label,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onPressed,
          borderRadius: BorderRadius.circular(ChatBoxTokens.radius.small),
          child: Padding(
            padding: EdgeInsets.all(ChatBoxTokens.spacing.md),
            child: Icon(icon, size: 18, color: color), // 恢复原始大小
          ),
        ),
      ),
    );
  }
}

/// 编辑模式操作按钮
class EditModeActions extends StatelessWidget {
  final VoidCallback onCancel;
  final VoidCallback onSave;
  final VoidCallback? onResend; // 仅用户消息有重新发送

  const EditModeActions({
    super.key,
    required this.onCancel,
    required this.onSave,
    this.onResend,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: EdgeInsets.only(top: ChatBoxTokens.spacing.sm),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          // 取消
          TextButton.icon(
            onPressed: onCancel,
            icon: const Icon(AppleIcons.close, size: 18),
            label: const Text('取消'),
            style: TextButton.styleFrom(
              foregroundColor: Colors.grey.shade600,
            ),
          ),
          SizedBox(width: ChatBoxTokens.spacing.sm),
          
          // 保存
          ElevatedButton.icon(
            onPressed: onSave,
            icon: const Icon(Icons.save, size: 18),
            label: const Text('保存'),
          ),
          
          // 重新发送（仅用户消息）
          if (onResend != null) ...[
            SizedBox(width: ChatBoxTokens.spacing.sm),
            ElevatedButton.icon(
              onPressed: onResend,
              icon: const Icon(Icons.send, size: 18),
              label: const Text('重新发送'),
              style: ElevatedButton.styleFrom(
                backgroundColor: Theme.of(context).colorScheme.primary,
                foregroundColor: Theme.of(context).colorScheme.onPrimary,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

