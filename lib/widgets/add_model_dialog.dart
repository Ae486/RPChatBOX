import 'package:flutter/material.dart';
import '../models/provider_config.dart';
import '../adapters/ai_provider.dart';

/// 添加模型对话框
/// 支持手动输入模型ID或从检测到的模型列表中选择
class AddModelDialog extends StatefulWidget {
  final ProviderConfig provider;

  const AddModelDialog({
    super.key,
    required this.provider,
  });

  @override
  State<AddModelDialog> createState() => _AddModelDialogState();
}

class _AddModelDialogState extends State<AddModelDialog> {
  final _formKey = GlobalKey<FormState>();
  final _modelIdController = TextEditingController();
  
  bool _isDetecting = false;
  List<String> _availableModels = [];
  List<String> _selectedModels = []; // 🆕 已选择的模型列表
  String? _errorMessage;

  @override
  void dispose() {
    _modelIdController.dispose();
    super.dispose();
  }

  void _submit() {
    // 🆕 支持批量添加：优先添加已选择的模型，其次是输入框中的模型
    if (_selectedModels.isNotEmpty) {
      // 返回多个模型ID（用逗号分隔）
      Navigator.pop(context, _selectedModels.join(','));
      return;
    }
    
    // 如果没有选择模型，则验证输入框
    if (_formKey.currentState!.validate()) {
      Navigator.pop(context, _modelIdController.text.trim());
    }
  }

  /// 检测可用模型
  Future<void> _detectModels() async {
    setState(() {
      _isDetecting = true;
      _errorMessage = null;
    });

    try {
      final aiProvider = ProviderFactory.createProvider(widget.provider);
      final models = await aiProvider.listAvailableModels();
      
      setState(() {
        _availableModels = models;
        _isDetecting = false;
        if (models.isEmpty) {
          _errorMessage = '未检测到可用模型';
        }
      });
    } catch (e) {
      setState(() {
        _isDetecting = false;
        _errorMessage = '检测失败: ${e.toString()}';
      });
    }
  }

  /// 🆕 切换模型选择状态
  void _toggleModel(String modelId) {
    setState(() {
      if (_selectedModels.contains(modelId)) {
        _selectedModels.remove(modelId);
      } else {
        _selectedModels.add(modelId);
      }
    });
  }

  /// 🆕 移除已选择的模型
  void _removeSelectedModel(String modelId) {
    setState(() {
      _selectedModels.remove(modelId);
    });
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('添加模型'),
      content: SizedBox(
        width: 500,
        // 🔧 限制最大高度，超出后可滚动
        child: ConstrainedBox(
          constraints: BoxConstraints(
            maxHeight: MediaQuery.of(context).size.height * 0.7, // 最多占据屏幕70%高度
          ),
          child: Form(
            key: _formKey,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
              // 模型ID输入框
              TextFormField(
                controller: _modelIdController,
                decoration: const InputDecoration(
                  labelText: '模型 ID',
                  hintText: '例如: gpt-4, gemini-2.5-pro',
                  border: OutlineInputBorder(),
                ),
                autofocus: true,
                validator: (value) {
                  // 🔧 如果已选择模型，则不验证输入框
                  if (_selectedModels.isNotEmpty) {
                    return null;
                  }
                  if (value == null || value.trim().isEmpty) {
                    return '请输入模型ID或从列表中选择';
                  }
                  return null;
                },
                onFieldSubmitted: (_) => _submit(),
              ),
              
              // 🆕 已选择的模型卡片列表
              if (_selectedModels.isNotEmpty) ...[
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: _selectedModels.map((modelId) {
                    return Chip(
                      label: Text(modelId),
                      deleteIcon: const Icon(Icons.close, size: 18),
                      onDeleted: () => _removeSelectedModel(modelId),
                      backgroundColor: Theme.of(context).colorScheme.primaryContainer,
                      labelStyle: TextStyle(
                        fontSize: 13,
                        color: Theme.of(context).colorScheme.onPrimaryContainer,
                      ),
                    );
                  }).toList(),
                ),
              ],
              
              const SizedBox(height: 16),
              
              // 检测按钮
              OutlinedButton.icon(
                onPressed: _isDetecting ? null : _detectModels,
                icon: _isDetecting
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.search),
                label: Text(_isDetecting ? '检测中...' : '检测可用模型'),
              ),
              
              // 错误信息
              if (_errorMessage != null) ...[
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.errorContainer.withOpacity(0.3),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(
                      color: Theme.of(context).colorScheme.error.withOpacity(0.3),
                    ),
                  ),
                  child: Row(
                    children: [
                      Icon(
                        Icons.error_outline,
                        size: 18,
                        color: Theme.of(context).colorScheme.error,
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          _errorMessage!,
                          style: TextStyle(
                            fontSize: 12,
                            color: Theme.of(context).colorScheme.error,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
              
              // 模型列表
              if (_availableModels.isNotEmpty) ...[
                const SizedBox(height: 16),
                Text(
                  '可用模型 (${_availableModels.length})',
                  style: Theme.of(context).textTheme.titleSmall,
                ),
                const SizedBox(height: 8),
                Container(
                  constraints: const BoxConstraints(maxHeight: 300),
                  decoration: BoxDecoration(
                    border: Border.all(
                      color: Theme.of(context).colorScheme.outline.withOpacity(0.3),
                    ),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: ListView.separated(
                    shrinkWrap: true,
                    itemCount: _availableModels.length,
                    separatorBuilder: (context, index) => Divider(
                      height: 1,
                      color: Theme.of(context).colorScheme.outline.withOpacity(0.2),
                    ),
                    itemBuilder: (context, index) {
                      final modelId = _availableModels[index];
                      final isSelected = _selectedModels.contains(modelId);
                      
                      return ListTile(
                        dense: true,
                        selected: isSelected,
                        selectedTileColor: Theme.of(context).colorScheme.primaryContainer.withOpacity(0.3),
                        onTap: () => _toggleModel(modelId), // 🔧 点击整个条目
                        title: Text(
                          modelId,
                          style: const TextStyle(fontSize: 13),
                        ),
                        trailing: Icon(
                          isSelected ? Icons.check_circle : Icons.add_circle_outline,
                          size: 20,
                          color: isSelected 
                              ? Theme.of(context).colorScheme.primary 
                              : null,
                        ),
                      );
                    },
                  ),
                ),
              ],
              
              const SizedBox(height: 12),
              
              // 提示信息
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.surfaceContainerHighest.withOpacity(0.5),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Row(
                  children: [
                    Icon(
                      Icons.info_outline,
                      size: 18,
                      color: Theme.of(context).colorScheme.primary,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        '💡 支持多选：点击模型列表批量选择，模型能力将自动识别',
                        style: TextStyle(
                          fontSize: 12,
                          color: Theme.of(context).colorScheme.onSurface.withOpacity(0.7),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
                ],
              ),
            ),
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('取消'),
        ),
        ElevatedButton(
          onPressed: _submit,
          child: const Text('添加'),
        ),
      ],
    );
  }
}
