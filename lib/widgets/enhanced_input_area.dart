import 'dart:io';
import '../design_system/apple_icons.dart';
import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart' as file_picker;
import '../models/attached_file.dart';
import '../models/model_config.dart';
import '../models/provider_config.dart';
import '../services/model_service_manager.dart';
import 'conversation_config_dialog.dart';
import '../models/conversation_settings.dart';
import '../utils/global_toast.dart';
import '../design_system/design_tokens.dart';

/// 增强的输入区域组件
/// 包含文件上传、网络开关、配置按钮、模型选择
class EnhancedInputArea extends StatefulWidget {
  final TextEditingController textController;
  final VoidCallback onSend;
  final VoidCallback? onStop;
  final bool isStreaming;
  final ModelServiceManager serviceManager;
  final ConversationSettings conversationSettings;
  final Function(ConversationSettings) onSettingsChanged;
  final bool attachmentBarVisible; // 🆕 附件栏可见性（由外部控制）

  const EnhancedInputArea({
    super.key,
    required this.textController,
    required this.onSend,
    this.onStop,
    required this.isStreaming,
    required this.serviceManager,
    required this.conversationSettings,
    required this.onSettingsChanged,
    this.attachmentBarVisible = true,
  });

  @override
  State<EnhancedInputArea> createState() => _EnhancedInputAreaState();
}

class _EnhancedInputAreaState extends State<EnhancedInputArea> {
  final FocusNode _focusNode = FocusNode();

  @override
  void initState() {
    super.initState();
    // 监听焦点变化以触发UI更新（边框动画）
    _focusNode.addListener(() {
      setState(() {});
    });
  }

  @override
  void dispose() {
    _focusNode.dispose();
    super.dispose();
  }

  Future<void> _pickFiles() async {
    try {
      // 支持更多文件类型，包括文档和代码文件
      final result = await file_picker.FilePicker.platform.pickFiles(
        allowMultiple: true,
        type: file_picker.FileType.custom,
        allowedExtensions: [
          // 图片文件
          'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg',
          // 文档文件
          'pdf', 'doc', 'docx', 'txt', 'md', 'rtf',
          // 代码文件
          'js', 'ts', 'dart', 'py', 'java', 'cpp', 'c', 'h', 'hpp',
          'cs', 'php', 'rb', 'go', 'rs', 'swift', 'kt',
          'html', 'htm', 'css', 'scss', 'less', 'sass',
          'json', 'xml', 'yaml', 'yml', 'toml', 'ini', 'cfg', 'conf',
          'sql', 'sh', 'bat', 'ps1', 'dockerfile',
          // 数据文件
          'csv', 'tsv', 'xls', 'xlsx',
          // 其他
          'log', 'gitignore', 'env', 'config'
        ],
      );

      if (result != null && result.files.isNotEmpty) {
        final attachedFiles = <AttachedFile>[];

        for (var platformFile in result.files) {
          if (platformFile.path != null) {
            final file = await AttachedFile.fromFile(
              File(platformFile.path!),
              widget.serviceManager.generateId(),
            );
            attachedFiles.add(file);
          }
        }

        if (attachedFiles.isNotEmpty) {
          var updatedSettings = widget.conversationSettings;
          for (var file in attachedFiles) {
            updatedSettings = updatedSettings.addFile(file);
          }
          widget.onSettingsChanged(updatedSettings);

          if (mounted) {
            // 🆕 使用全局提示框
            GlobalToast.showSuccess(
              context,
              '成功添加 ${attachedFiles.length} 个文件',
            );
          }
        }
      }
    } catch (e) {
      if (mounted) {
        // 🆕 使用全局提示框
        GlobalToast.showError(
          context,
          '❌ 文件添加失败\n${e.toString()}',
        );
      }
    }
  }

  void _showConfigDialog() {
    showDialog(
      context: context,
      builder: (context) => ConversationConfigDialog(
        settings: widget.conversationSettings,
        onSave: (updatedSettings) {
          widget.onSettingsChanged(updatedSettings);
        },
      ),
    );
  }

  void _showModelSelector() async {
    final modelWithProvider = _getCurrentModelWithProvider();

    await showModalBottomSheet(
      context: context,
      builder: (context) => _ModelSelectorSheet(
        serviceManager: widget.serviceManager,
        currentModelId: widget.conversationSettings.selectedModelId,
        onModelSelected: (providerId, modelId) {
          final updated = widget.conversationSettings.copyWith(
            selectedProviderId: providerId,
            selectedModelId: modelId,
          );
          widget.onSettingsChanged(updated);
          Navigator.pop(context);
        },
      ),
    );
  }

  ({ProviderConfig provider, ModelConfig model})? _getCurrentModelWithProvider() {
    final modelId = widget.conversationSettings.selectedModelId;
    if (modelId == null) return null;
    final result = widget.serviceManager.getModelWithProvider(modelId);
    if (result == null) return null;
    return (provider: result.provider, model: result.model);
  }

  void _removeFile(AttachedFile file) {
    final updated = widget.conversationSettings.removeFile(file.id);
    widget.onSettingsChanged(updated);
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final currentModel = _getCurrentModelWithProvider();
    final hasFiles = widget.conversationSettings.hasAttachedFiles;

    return Container(
      decoration: BoxDecoration(
        color: Theme.of(context).scaffoldBackgroundColor,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.05),
            blurRadius: 8,
            offset: const Offset(0, -2),
          ),
        ],
      ),
      child: SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // 附件预览区 - 使用外部传入的可见性控制
            if (hasFiles && widget.attachmentBarVisible) _buildAttachedFilesPreview(),

            // 🆕 两层布局结构
            Padding(
              padding: EdgeInsets.symmetric(
                horizontal: ChatBoxTokens.spacing.md,
                vertical: ChatBoxTokens.spacing.sm,
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  // 上层：多行文本输入框（Apple现代风格）
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    constraints: const BoxConstraints(
                      minHeight: 48,
                      maxHeight: 48 * 5, // 最大 5 行
                    ),
                    decoration: BoxDecoration(
                      color: isDark 
                        ? Colors.white.withValues(alpha: 0.05)
                        : Colors.black.withValues(alpha: 0.03),
                      borderRadius: BorderRadius.circular(12), // Apple风格圆角
                      border: Border.all(
                        color: _focusNode.hasFocus
                          ? Theme.of(context).colorScheme.primary
                          : (isDark ? Colors.grey.shade700 : Colors.grey.shade300),
                        width: _focusNode.hasFocus ? 2 : 1, // 聚焦时加粗边框
                      ),
                      boxShadow: _focusNode.hasFocus ? [
                        BoxShadow(
                          color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.2),
                          blurRadius: 8,
                          offset: const Offset(0, 2),
                        ),
                      ] : null, // 聚焦时添加阴影
                    ),
                    child: TextField(
                      controller: widget.textController,
                      focusNode: _focusNode,
                      maxLines: 5,
                      minLines: 1,
                      style: TextStyle(
                        fontSize: 15,
                        height: 1.5,
                        color: isDark ? Colors.white : Colors.black87,
                      ),
                      decoration: InputDecoration(
                        hintText: '请在这里输入你的问题...',
                        hintStyle: TextStyle(
                          color: isDark 
                            ? Colors.grey.shade500
                            : Colors.grey.shade600,
                          fontSize: 15,
                        ),
                        border: InputBorder.none,
                        contentPadding: const EdgeInsets.symmetric(
                          horizontal: 16,
                          vertical: 14,
                        ),
                      ),
                      onSubmitted: (_) {
                        if (!widget.isStreaming) {
                          widget.onSend();
                        }
                      },
                    ),
                  ),

                  SizedBox(height: ChatBoxTokens.spacing.sm),

                  // 下层：按钮行
                  Row(
                    children: [
                      // 左侧按钮组
                      IconButton(
                        icon: const Icon(AppleIcons.addCircle),
                        onPressed: _pickFiles,
                        tooltip: '上传文件',
                        color: hasFiles ? Theme.of(context).colorScheme.primary : null,
                      ),
                      IconButton(
                        icon: const Icon(Icons.language),
                        onPressed: null, // 暂未实现
                        tooltip: '联网功能（开发中）',
                        color: Colors.grey,
                      ),
                      IconButton(
                        icon: const Icon(Icons.tune),
                        onPressed: _showConfigDialog,
                        tooltip: '对话配置',
                      ),

                      // 中间弹性空间
                      const Spacer(),

                      // 模型选择器
                      InkWell(
                        onTap: _showModelSelector,
                        borderRadius: BorderRadius.circular(ChatBoxTokens.spacing.lg + 4),
                        child: Container(
                          padding: EdgeInsets.symmetric(
                            horizontal: ChatBoxTokens.spacing.md,
                            vertical: ChatBoxTokens.spacing.sm,
                          ),
                          decoration: BoxDecoration(
                            color: Theme.of(context).colorScheme.primary,
                            borderRadius: BorderRadius.circular(ChatBoxTokens.spacing.lg + 4),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(
                                Icons.psychology,
                                size: 18,
                                color: Colors.white,
                              ),
                              SizedBox(width: ChatBoxTokens.spacing.xs + 2),
                              ConstrainedBox(
                                constraints: const BoxConstraints(maxWidth: 100),
                                child: Text(
                                  currentModel?.model.displayName ?? '选择模型',
                                  style: const TextStyle(
                                    fontSize: 13,
                                    color: Colors.white,
                                    fontWeight: FontWeight.w500,
                                  ),
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                              SizedBox(width: ChatBoxTokens.spacing.xs),
                              const Icon(
                                Icons.arrow_drop_down,
                                size: 20,
                                color: Colors.white,
                              ),
                            ],
                          ),
                        ),
                      ),

                      const SizedBox(width: 8),

                      // 发送/停止按钮
                      IconButton(
                        icon: Icon(
                          widget.isStreaming ? Icons.stop_circle : Icons.arrow_upward,
                        ),
                        onPressed: widget.isStreaming ? widget.onStop : widget.onSend,
                        iconSize: 28,
                        color: Theme.of(context).colorScheme.primary,
                        tooltip: widget.isStreaming ? '停止' : '发送',
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAttachedFilesPreview() {
    return Container(
      width: double.infinity, // 固定为全屏宽度
      padding: EdgeInsets.all(ChatBoxTokens.spacing.md),
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(color: Colors.grey.shade300),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '附件 (${widget.conversationSettings.attachedFiles.length})',
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: Colors.grey.shade700,
                ),
          ),
          SizedBox(height: ChatBoxTokens.spacing.sm),
          Wrap(
            spacing: ChatBoxTokens.spacing.sm,
            runSpacing: ChatBoxTokens.spacing.sm,
            children: widget.conversationSettings.attachedFiles.map((file) {
              return Chip(
                avatar: Icon(_getFileIcon(file.type), size: 18),
                label: ConstrainedBox(
                  constraints: BoxConstraints(
                    maxWidth: MediaQuery.of(context).size.width - 150, // 限制最大宽度
                  ),
                  child: Text(
                    file.name,
                    style: const TextStyle(fontSize: 12),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                deleteIcon: const Icon(AppleIcons.close, size: 16),
                onDeleted: () => _removeFile(file),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }

  IconData _getFileIcon(FileType type) {
    switch (type) {
      case FileType.image:
        return AppleIcons.image;
      case FileType.video:
        return AppleIcons.video;
      case FileType.audio:
        return AppleIcons.audio;
      case FileType.document:
        return AppleIcons.document;
      case FileType.code:
        return AppleIcons.code;
      case FileType.other:
        return AppleIcons.file;
      default:
        return AppleIcons.file;
    }
  }
}

/// 模型选择器底部面板
class _ModelSelectorSheet extends StatelessWidget {
  final ModelServiceManager serviceManager;
  final String? currentModelId;
  final Function(String providerId, String modelId) onModelSelected;

  const _ModelSelectorSheet({
    required this.serviceManager,
    required this.currentModelId,
    required this.onModelSelected,
  });

  @override
  Widget build(BuildContext context) {
    final providers = serviceManager.getEnabledProviders();

    return Container(
      padding: EdgeInsets.all(ChatBoxTokens.spacing.lg + 4),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                '选择模型',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const Spacer(),
              IconButton(
                icon: const Icon(AppleIcons.close),
                onPressed: () => Navigator.pop(context),
              ),
            ],
          ),
          SizedBox(height: ChatBoxTokens.spacing.lg),
          if (providers.isEmpty)
            Center(
              child: Padding(
                padding: EdgeInsets.all(ChatBoxTokens.spacing.xxl),
                child: Text('暂无可用模型服务\n请先在设置中添加'),
              ),
            )
          else
            Expanded(
              child: ListView.builder(
                shrinkWrap: true,
                itemCount: providers.length,
                itemBuilder: (context, index) {
                  final provider = providers[index];
                  final models = serviceManager
                      .getModelsByProvider(provider.id)
                      .where((m) => m.isEnabled)
                      .toList();

                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Padding(
                        padding: EdgeInsets.symmetric(vertical: ChatBoxTokens.spacing.sm),
                        child: Text(
                          provider.name,
                          style: Theme.of(context).textTheme.titleSmall?.copyWith(
                                color: Colors.grey.shade700,
                              ),
                        ),
                      ),
                      ...models.map((model) {
                        final isSelected = model.id == currentModelId;
                        return ListTile(
                          selected: isSelected,
                          leading: Icon(
                            Icons.psychology,
                            color: isSelected ? Theme.of(context).colorScheme.primary : null,
                          ),
                          title: Text(model.displayName),
                          subtitle: Wrap(
                            spacing: 6,
                            children: model.capabilities.map((cap) {
                              return Tooltip(
                                message: cap.displayName,
                                child: Container(
                                  padding: EdgeInsets.all(ChatBoxTokens.spacing.xs),
                                  decoration: BoxDecoration(
                                    color: cap.color.withValues(alpha: 0.1),
                                    borderRadius: BorderRadius.circular(ChatBoxTokens.radius.xs),
                                  ),
                                  child: Icon(
                                    cap.icon,
                                    size: 14,
                                    color: cap.color,
                                  ),
                                ),
                              );
                            }).toList(),
                          ),
                          trailing: isSelected ? const Icon(AppleIcons.check) : null,
                          onTap: () => onModelSelected(provider.id, model.id),
                        );
                      }),
                      if (index < providers.length - 1) const Divider(),
                    ],
                  );
                },
              ),
            ),
        ],
      ),
    );
  }
}
