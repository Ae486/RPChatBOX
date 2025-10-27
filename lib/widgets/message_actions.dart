import 'package:flutter/material.dart';

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
      margin: const EdgeInsets.only(top: 4),
      child: Wrap(
        spacing: 8,
        children: [
          // 复制
          _buildActionButton(
            context,
            icon: Icons.copy,
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
            icon: Icons.edit,
            label: '编辑',
            onPressed: onEdit,
          ),
          
          // 导出（仅AI消息）
          if (onExport != null)
            _buildActionButton(
              context,
              icon: Icons.file_download,
              label: '导出',
              onPressed: onExport!,
            ),
          
          // 删除
          _buildActionButton(
            context,
            icon: Icons.delete_outline,
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
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(20),
        child: Padding(
          padding: const EdgeInsets.all(8),
          child: Icon(icon, size: 18, color: color),
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
      margin: const EdgeInsets.only(top: 8),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          // 取消
          TextButton.icon(
            onPressed: onCancel,
            icon: const Icon(Icons.close, size: 18),
            label: const Text('取消'),
            style: TextButton.styleFrom(
              foregroundColor: Colors.grey.shade600,
            ),
          ),
          const SizedBox(width: 8),
          
          // 保存
          ElevatedButton.icon(
            onPressed: onSave,
            icon: const Icon(Icons.save, size: 18),
            label: const Text('保存'),
          ),
          
          // 重新发送（仅用户消息）
          if (onResend != null) ...[
            const SizedBox(width: 8),
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

