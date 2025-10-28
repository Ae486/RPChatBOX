import 'package:flutter/material.dart';
import '../models/provider_config.dart';
import '../models/model_config.dart';
import '../services/model_service_manager.dart';
import '../widgets/add_provider_dialog.dart';
import '../widgets/provider_card.dart';

/// 模型服务管理页面
/// 参照cherrybox界面设计，管理AI服务提供商和模型
class ModelServicesPage extends StatefulWidget {
  final ModelServiceManager serviceManager;

  const ModelServicesPage({
    super.key,
    required this.serviceManager,
  });

  @override
  State<ModelServicesPage> createState() => _ModelServicesPageState();
}

class _ModelServicesPageState extends State<ModelServicesPage> {
  List<ProviderConfig> _providers = [];
  Map<String, List<ModelConfig>> _providerModels = {};
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    setState(() => _isLoading = true);

    try {
      final providers = widget.serviceManager.getProviders();
      final models = <String, List<ModelConfig>>{};

      for (var provider in providers) {
        models[provider.id] = widget.serviceManager.getModelsByProvider(provider.id);
      }

      setState(() {
        _providers = providers;
        _providerModels = models;
        _isLoading = false;
      });
    } catch (e) {
      setState(() => _isLoading = false);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('加载失败: ${e.toString()}')),
        );
      }
    }
  }

  Future<void> _showAddProviderDialog() async {
    final result = await showDialog<ProviderConfig>(
      context: context,
      builder: (context) => AddProviderDialog(
        serviceManager: widget.serviceManager,
      ),
    );

    if (result != null) {
      await _loadData();
    }
  }

  Future<void> _toggleProvider(ProviderConfig provider) async {
    final updated = provider.copyWith(isEnabled: !provider.isEnabled);
    await widget.serviceManager.updateProvider(updated);
    await _loadData();
  }

  Future<void> _editProvider(ProviderConfig provider) async {
    final result = await showDialog<ProviderConfig>(
      context: context,
      builder: (context) => AddProviderDialog(
        serviceManager: widget.serviceManager,
        existingProvider: provider,
      ),
    );

    if (result != null) {
      await _loadData();
    }
  }

  Future<void> _deleteProvider(ProviderConfig provider) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('确认删除'),
        content: Text('确定要删除 "${provider.name}" 吗？\n这将同时删除该Provider下的所有模型。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            style: TextButton.styleFrom(foregroundColor: Colors.red),
            child: const Text('删除'),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      await widget.serviceManager.deleteProvider(provider.id);
      await _loadData();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('已删除 "${provider.name}"')),
        );
      }
    }
  }

  Future<void> _toggleModel(ModelConfig model) async {
    final updated = model.copyWith(isEnabled: !model.isEnabled);
    await widget.serviceManager.updateModel(updated);
    await _loadData();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('模型服务'),
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _buildBody(),
      bottomNavigationBar: _buildBottomBar(),
    );
  }

  Widget _buildBody() {
    if (_providers.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.cloud_off,
              size: 64,
              color: Colors.grey.shade400,
            ),
            const SizedBox(height: 16),
            Text(
              '暂无AI服务',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    color: Colors.grey.shade600,
                  ),
            ),
            const SizedBox(height: 8),
            Text(
              '点击下方"添加"按钮创建第一个服务',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Colors.grey.shade500,
                  ),
            ),
          ],
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: _providers.length,
      itemBuilder: (context, index) {
        final provider = _providers[index];
        final models = _providerModels[provider.id] ?? [];

        return ProviderCard(
          provider: provider,
          models: models,
          onToggle: () => _toggleProvider(provider),
          onEdit: () => _editProvider(provider),
          onDelete: () => _deleteProvider(provider),
          onToggleModel: _toggleModel,
          serviceManager: widget.serviceManager,
        );
      },
    );
  }

  Widget _buildBottomBar() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Theme.of(context).scaffoldBackgroundColor,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.05),
            blurRadius: 4,
            offset: const Offset(0, -2),
          ),
        ],
      ),
      child: SafeArea(
        child: Row(
          children: [
            Expanded(
              child: OutlinedButton.icon(
                onPressed: () {
                  // TODO: 打开管理界面（批量操作等）
                },
                icon: const Icon(Icons.settings),
                label: const Text('管理'),
                style: OutlinedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 14),
                ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: ElevatedButton.icon(
                onPressed: _showAddProviderDialog,
                icon: const Icon(Icons.add),
                label: const Text('添加'),
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 14),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
