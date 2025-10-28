import 'dart:io';
import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart' as file_picker;
import '../models/attached_file.dart';
import '../models/conversation_settings.dart';
import '../models/model_config.dart';
import '../models/provider_config.dart';
import '../services/model_service_manager.dart';

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

  const EnhancedInputArea({
    super.key,
    required this.textController,
    required this.onSend,
    this.onStop,
    required this.isStreaming,
    required this.serviceManager,
    required this.conversationSettings,
    required this.onSettingsChanged,
  });

  @override
  State<EnhancedInputArea> createState() => _EnhancedInputAreaState();
}

class _EnhancedInputAreaState extends State<EnhancedInputArea> {
  final FocusNode _focusNode = FocusNode();
  int _currentLines = 1;
  static const int _maxLines = 6;

  @override
  void dispose() {
    _focusNode.dispose();
    super.dispose();
  }

  Future<void> _pickFiles() async {
    try {
      final result = await file_picker.FilePicker.platform.pickFiles(
        allowMultiple: true,
        type: file_picker.FileType.custom,
        allowedExtensions: ['jpg', 'jpeg', 'png', 'gif', 'webp', 'pdf', 'txt', 'md', 'doc', 'docx'],
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
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(content: Text('已添加 ${attachedFiles.length} 个文件')),
            );
          }
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('文件选择失败: ${e.toString()}')),
        );
      }
    }
  }

  void _showConfigDialog() {
    // TODO: 显示对话配置面板
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('配置面板开发中...')),
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
            // 附件预览区
            if (hasFiles) _buildAttachedFilesPreview(),

            // 输入区域
            Padding(
              padding: const EdgeInsets.all(12),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  // 左侧按钮组
                  Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      // 文件上传按钮
                      IconButton(
                        icon: const Icon(Icons.attach_file),
                        onPressed: currentModel?.model.hasCapability(ModelCapability.vision) == true
                            ? _pickFiles
                            : null,
                        tooltip: '上传文件',
                        color: hasFiles ? Theme.of(context).colorScheme.primary : null,
                      ),

                      // 网络开关（预留）
                      IconButton(
                        icon: Icon(
                          widget.conversationSettings.enableNetwork
                              ? Icons.public
                              : Icons.public_off,
                        ),
                        onPressed: null, // 暂未实现
                        tooltip: '联网功能（开发中）',
                        color: widget.conversationSettings.enableNetwork
                            ? Theme.of(context).colorScheme.primary
                            : Colors.grey,
                      ),

                      // 配置按钮
                      IconButton(
                        icon: const Icon(Icons.settings),
                        onPressed: _showConfigDialog,
                        tooltip: '对话配置',
                      ),
                    ],
                  ),

                  const SizedBox(width: 8),

                  // 输入框
                  Expanded(
                    child: Container(
                      constraints: BoxConstraints(
                        minHeight: 48,
                        maxHeight: 48.0 * _maxLines,
                      ),
                      decoration: BoxDecoration(
                        color: isDark ? Colors.grey.shade900 : Colors.grey.shade100,
                        borderRadius: BorderRadius.circular(24),
                        border: Border.all(
                          color: isDark ? Colors.grey.shade700 : Colors.grey.shade300,
                        ),
                      ),
                      child: TextField(
                        controller: widget.textController,
                        focusNode: _focusNode,
                        maxLines: _maxLines,
                        minLines: 1,
                        decoration: const InputDecoration(
                          hintText: '输入消息...',
                          border: InputBorder.none,
                          contentPadding: EdgeInsets.symmetric(
                            horizontal: 20,
                            vertical: 14,
                          ),
                        ),
                        onChanged: (text) {
                          // 计算行数
                          final lines = '\n'.allMatches(text).length + 1;
                          if (lines != _currentLines) {
                            setState(() {
                              _currentLines = lines.clamp(1, _maxLines);
                            });
                          }
                        },
                        onSubmitted: (_) {
                          if (!widget.isStreaming) {
                            widget.onSend();
                          }
                        },
                      ),
                    ),
                  ),

                  const SizedBox(width: 8),

                  // 右侧按钮组
                  Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      // 模型选择按钮
                      Container(
                        margin: const EdgeInsets.only(bottom: 4),
                        child: Material(
                          color: Theme.of(context).colorScheme.secondaryContainer,
                          borderRadius: BorderRadius.circular(20),
                          child: InkWell(
                            onTap: _showModelSelector,
                            borderRadius: BorderRadius.circular(20),
                            child: Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Icon(
                                    Icons.psychology,
                                    size: 16,
                                    color: Theme.of(context).colorScheme.onSecondaryContainer,
                                  ),
                                  const SizedBox(width: 6),
                                  Text(
                                    currentModel?.model.displayName ?? '选择模型',
                                    style: TextStyle(
                                      fontSize: 12,
                                      color: Theme.of(context).colorScheme.onSecondaryContainer,
                                    ),
                                  ),
                                  const SizedBox(width: 4),
                                  Icon(
                                    Icons.arrow_drop_down,
                                    size: 16,
                                    color: Theme.of(context).colorScheme.onSecondaryContainer,
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                      ),

                      // 发送/停止按钮
                      FloatingActionButton(
                        mini: true,
                        onPressed: widget.isStreaming ? widget.onStop : widget.onSend,
                        child: Icon(
                          widget.isStreaming ? Icons.stop : Icons.send,
                        ),
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
      padding: const EdgeInsets.all(12),
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
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: widget.conversationSettings.attachedFiles.map((file) {
              return Chip(
                avatar: Icon(_getFileIcon(file.type), size: 18),
                label: Text(
                  file.name,
                  style: const TextStyle(fontSize: 12),
                ),
                deleteIcon: const Icon(Icons.close, size: 16),
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
        return Icons.image;
      case FileType.video:
        return Icons.videocam;
      case FileType.audio:
        return Icons.audiotrack;
      case FileType.document:
        return Icons.description;
      case FileType.code:
        return Icons.code;
      case FileType.other:
        return Icons.insert_drive_file;
      default:
        return Icons.insert_drive_file;
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
      padding: const EdgeInsets.all(20),
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
                icon: const Icon(Icons.close),
                onPressed: () => Navigator.pop(context),
              ),
            ],
          ),
          const SizedBox(height: 16),
          if (providers.isEmpty)
            const Center(
              child: Padding(
                padding: EdgeInsets.all(32),
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
                        padding: const EdgeInsets.symmetric(vertical: 8),
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
                              return Chip(
                                label: Text(cap.displayName),
                                visualDensity: VisualDensity.compact,
                                labelStyle: const TextStyle(fontSize: 10),
                              );
                            }).toList(),
                          ),
                          trailing: isSelected ? const Icon(Icons.check) : null,
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
