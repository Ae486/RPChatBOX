import 'package:flutter/material.dart';

import '../adapters/ai_provider.dart';
import '../chat_ui/owui/components/owui_app_bar.dart';
import '../chat_ui/owui/components/owui_card.dart';
import '../chat_ui/owui/components/owui_scaffold.dart';
import '../chat_ui/owui/components/owui_snack_bar.dart';
import '../chat_ui/owui/owui_icons.dart';
import '../chat_ui/owui/owui_tokens_ext.dart';
import '../pages/longform_story_page.dart';
import '../pages/rp_model_config_page.dart';
import '../main.dart';
import '../models/model_config.dart';
import '../models/provider_config.dart';
import '../models/rp_retrieval.dart';
import '../models/rp_setup.dart';
import '../services/backend_rp_retrieval_service.dart';
import '../services/backend_rp_setup_service.dart';
import '../services/backend_story_service.dart';

class PrestorySetupPage extends StatefulWidget {
  const PrestorySetupPage({super.key});

  @override
  State<PrestorySetupPage> createState() => _PrestorySetupPageState();
}

class _PrestorySetupPageState extends State<PrestorySetupPage> {
  static const int _memoryGraphMaxDepth = 1;
  static const int _memoryGraphMaxNodes = 30;
  static const int _memoryGraphMaxEdges = 50;

  final _service = BackendRpSetupService();
  final _retrievalService = BackendRpRetrievalService();
  final _storyService = BackendStoryService();
  final _messageController = TextEditingController();
  final Map<String, List<_SetupChatEntry>> _dialogues = {};

  List<RpSetupWorkspace> _workspaces = const [];
  RpSetupWorkspace? _currentWorkspace;
  RpActivationCheckResult? _lastActivationCheck;
  RpRetrievalStoryMaintenanceSnapshot? _retrievalMaintenance;
  RpMemoryGraphMaintenanceSnapshot? _memoryGraphMaintenance;
  RpMemoryGraphNeighborhoodResponse? _memoryGraphNeighborhood;
  _SetupWizardStage _selectedStage = _SetupWizardStage.worldBackground;
  String? _selectedProviderId;
  String? _selectedModelId;
  String? _selectedRetrievalEmbeddingProviderId;
  String? _selectedRetrievalEmbeddingModelId;
  String? _selectedRetrievalRerankProviderId;
  String? _selectedRetrievalRerankModelId;
  String? _selectedGraphExtractionProviderId;
  String? _selectedGraphExtractionModelId;
  String? _retrievalMaintenanceError;
  String? _memoryGraphMaintenanceError;
  String? _memoryGraphNeighborhoodError;
  String? _selectedMemoryGraphNodeId;
  String? _selectedMemoryGraphEdgeId;
  String? _retrievalMaintenanceActionLabel;
  bool _isLoading = true;
  bool _isLoadingRetrievalMaintenance = false;
  bool _isLoadingMemoryGraphMaintenance = false;
  bool _isLoadingMemoryGraphNeighborhood = false;
  bool _isRunningRetrievalMaintenanceAction = false;
  bool _isSending = false;
  int _retrievalMaintenanceRequestToken = 0;
  int _memoryGraphMaintenanceRequestToken = 0;
  int _memoryGraphNeighborhoodRequestToken = 0;

  @override
  void initState() {
    super.initState();
    final defaultPair = globalModelServiceManager.getDefaultProviderModel();
    _selectedProviderId = defaultPair.provider?.id;
    _selectedModelId = defaultPair.model?.id;
    _load();
  }

  @override
  void dispose() {
    _messageController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _isLoading = true);
    try {
      final workspaces = await _service.listWorkspaces();
      if (!mounted) return;
      setState(() {
        _workspaces = workspaces;
        _currentWorkspace = workspaces.isNotEmpty ? workspaces.first : null;
        _isLoading = false;
      });
      if (_currentWorkspace == null) {
        setState(() {
          _retrievalMaintenance = null;
          _retrievalMaintenanceError = null;
          _memoryGraphMaintenance = null;
          _memoryGraphNeighborhood = null;
          _memoryGraphMaintenanceError = null;
          _memoryGraphNeighborhoodError = null;
          _selectedMemoryGraphNodeId = null;
          _selectedMemoryGraphEdgeId = null;
          _selectedRetrievalEmbeddingProviderId = null;
          _selectedRetrievalEmbeddingModelId = null;
          _selectedRetrievalRerankProviderId = null;
          _selectedRetrievalRerankModelId = null;
          _selectedGraphExtractionProviderId = null;
          _selectedGraphExtractionModelId = null;
        });
      }
      _syncSelectedStage(force: true);
      _syncSelectedProviderAndModel();
      _syncRetrievalModelSelections();
      if (_currentWorkspace != null) {
        await _refreshWorkspace(
          _currentWorkspace!.workspaceId,
          preserveStage: false,
        );
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _isLoading = false);
      OwuiSnackBars.error(context, message: '加载 prestory setup 失败: $e');
    }
  }

  Future<void> _refreshWorkspace(
    String workspaceId, {
    bool preserveStage = true,
  }) async {
    final workspace = await _service.getWorkspace(workspaceId);
    if (!mounted) return;
    final workspaceChanged =
        _currentWorkspace?.workspaceId != workspace.workspaceId;
    setState(() {
      _workspaces = [
        workspace,
        ..._workspaces.where(
          (item) => item.workspaceId != workspace.workspaceId,
        ),
      ];
      _currentWorkspace = workspace;
      if (workspaceChanged) {
        _retrievalMaintenance = null;
        _retrievalMaintenanceError = null;
        _memoryGraphMaintenance = null;
        _memoryGraphNeighborhood = null;
        _memoryGraphMaintenanceError = null;
        _memoryGraphNeighborhoodError = null;
        _selectedMemoryGraphNodeId = null;
        _selectedMemoryGraphEdgeId = null;
      }
    });
    if (!preserveStage || workspaceChanged) {
      _syncSelectedStage(force: true);
    }
    _syncSelectedProviderAndModel();
    _syncRetrievalModelSelections();
    await _refreshRetrievalMaintenance(workspace.storyId, silent: true);
  }

  void _syncSelectedStage({bool force = false}) {
    final workspace = _currentWorkspace;
    if (workspace == null) {
      if (!mounted) return;
      setState(() {
        _selectedStage = _SetupWizardStage.worldBackground;
      });
      return;
    }

    final nextStage = _preferredStageForWorkspace(workspace);
    if (!mounted) return;
    if (!force && !_isSelectedStageOutOfPlan(workspace)) {
      return;
    }
    setState(() {
      _selectedStage = nextStage;
    });
  }

  void _syncSelectedProviderAndModel() {
    final providers = _agentProviders();
    if (providers.isEmpty) {
      if (!mounted) return;
      setState(() {
        _selectedProviderId = null;
        _selectedModelId = null;
      });
      return;
    }

    final providerId = providers.any((item) => item.id == _selectedProviderId)
        ? _selectedProviderId!
        : providers.first.id;
    final models = _agentModelsForProvider(providerId);
    final modelId = models.any((item) => item.id == _selectedModelId)
        ? _selectedModelId
        : (models.isNotEmpty ? models.first.id : null);

    if (!mounted) return;
    setState(() {
      _selectedProviderId = providerId;
      _selectedModelId = modelId;
    });
  }

  List<ProviderConfig> _agentProviders() {
    return globalModelServiceManager
        .getEnabledProviders()
        .where((provider) => _agentModelsForProvider(provider.id).isNotEmpty)
        .toList();
  }

  List<ModelConfig> _agentModelsForProvider(String providerId) {
    return globalModelServiceManager
        .getModelsByProvider(providerId)
        .where((item) => item.isEnabled)
        .where((item) => item.isAgentCapable)
        .toList();
  }

  void _updateAgentSelection({
    required String? providerId,
    required String? modelId,
  }) {
    if (!mounted) return;
    setState(() {
      _selectedProviderId = providerId;
      _selectedModelId = modelId;
    });
  }

  void _syncRetrievalModelSelections() {
    final workspace = _currentWorkspace;
    if (workspace == null) {
      if (!mounted) return;
      setState(() {
        _selectedRetrievalEmbeddingProviderId = null;
        _selectedRetrievalEmbeddingModelId = null;
        _selectedRetrievalRerankProviderId = null;
        _selectedRetrievalRerankModelId = null;
        _selectedGraphExtractionProviderId = null;
        _selectedGraphExtractionModelId = null;
      });
      return;
    }

    final config = workspace.storyConfigDraft ?? const <String, dynamic>{};
    final embeddingSelection = _normalizeRetrievalSelection(
      providerId: config['retrieval_embedding_provider_id']?.toString(),
      modelId: config['retrieval_embedding_model_id']?.toString(),
      providerCandidates: _retrievalEmbeddingProviders(),
      modelCandidatesForProvider: _retrievalEmbeddingModelsForProvider,
    );
    final rerankSelection = _normalizeRetrievalSelection(
      providerId: config['retrieval_rerank_provider_id']?.toString(),
      modelId: config['retrieval_rerank_model_id']?.toString(),
      providerCandidates: _retrievalRerankProviders(),
      modelCandidatesForProvider: _retrievalRerankModelsForProvider,
    );
    final graphSelection = _normalizeRetrievalSelection(
      providerId: config['graph_extraction_provider_id']?.toString(),
      modelId: config['graph_extraction_model_id']?.toString(),
      providerCandidates: _graphExtractionProviders(),
      modelCandidatesForProvider: _graphExtractionModelsForProvider,
    );

    if (!mounted) return;
    setState(() {
      _selectedRetrievalEmbeddingProviderId = embeddingSelection.providerId;
      _selectedRetrievalEmbeddingModelId = embeddingSelection.modelId;
      _selectedRetrievalRerankProviderId = rerankSelection.providerId;
      _selectedRetrievalRerankModelId = rerankSelection.modelId;
      _selectedGraphExtractionProviderId = graphSelection.providerId;
      _selectedGraphExtractionModelId = graphSelection.modelId;
    });
  }

  ({String? providerId, String? modelId}) _normalizeRetrievalSelection({
    required String? providerId,
    required String? modelId,
    required List<String> providerCandidates,
    required List<ModelConfig> Function(String providerId)
    modelCandidatesForProvider,
  }) {
    String? normalizedProviderId = providerId;
    String? normalizedModelId = modelId;

    if (normalizedModelId != null) {
      final modelWithProvider = globalModelServiceManager.getModelWithProvider(
        normalizedModelId,
      );
      if (modelWithProvider == null || !modelWithProvider.model.isEnabled) {
        normalizedProviderId = null;
        normalizedModelId = null;
      } else {
        normalizedProviderId = modelWithProvider.provider.id;
      }
    }

    if (normalizedProviderId != null &&
        !providerCandidates.contains(normalizedProviderId)) {
      normalizedProviderId = null;
      normalizedModelId = null;
    }

    if (normalizedProviderId != null && normalizedModelId != null) {
      final models = modelCandidatesForProvider(normalizedProviderId);
      if (!models.any((item) => item.id == normalizedModelId)) {
        normalizedModelId = null;
      }
    }

    return (providerId: normalizedProviderId, modelId: normalizedModelId);
  }

  Future<void> _createWorkspace() async {
    final controller = TextEditingController(
      text: 'story_${DateTime.now().millisecondsSinceEpoch}',
    );
    final storyId = await showDialog<String>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('创建 prestory workspace'),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(
            labelText: 'Story ID',
            hintText: 'story_longform_001',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () =>
                Navigator.pop(dialogContext, controller.text.trim()),
            child: const Text('创建'),
          ),
        ],
      ),
    );
    if (storyId == null || storyId.isEmpty) return;
    try {
      final workspace = await _service.createWorkspace(storyId: storyId);
      if (!mounted) return;
      setState(() {
        _workspaces = [workspace, ..._workspaces];
        _currentWorkspace = workspace;
        _retrievalMaintenance = null;
        _retrievalMaintenanceError = null;
        _memoryGraphMaintenance = null;
        _memoryGraphNeighborhood = null;
        _memoryGraphMaintenanceError = null;
        _memoryGraphNeighborhoodError = null;
        _selectedMemoryGraphNodeId = null;
        _selectedMemoryGraphEdgeId = null;
      });
      _syncSelectedStage(force: true);
      _syncRetrievalModelSelections();
      await _refreshRetrievalMaintenance(workspace.storyId, silent: true);
      if (!mounted) return;
      OwuiSnackBars.success(context, message: '已创建 prestory workspace');
    } catch (e) {
      if (!mounted) return;
      OwuiSnackBars.error(context, message: '创建 workspace 失败: $e');
    }
  }

  List<String> _retrievalEmbeddingProviders() {
    return globalModelServiceManager
        .getEnabledProviders()
        .where(
          (provider) =>
              _retrievalEmbeddingModelsForProvider(provider.id).isNotEmpty,
        )
        .map((provider) => provider.id)
        .toList();
  }

  List<ModelConfig> _retrievalEmbeddingModelsForProvider(String providerId) {
    return globalModelServiceManager
        .getModelsByProvider(providerId)
        .where((item) => item.isEnabled)
        .where(_isEmbeddingCandidateModel)
        .toList();
  }

  List<String> _retrievalRerankProviders() {
    return globalModelServiceManager
        .getEnabledProviders()
        .where(
          (provider) =>
              _retrievalRerankModelsForProvider(provider.id).isNotEmpty,
        )
        .map((provider) => provider.id)
        .toList();
  }

  List<ModelConfig> _retrievalRerankModelsForProvider(String providerId) {
    return globalModelServiceManager
        .getModelsByProvider(providerId)
        .where((item) => item.isEnabled)
        .where(_isRerankCandidateModel)
        .toList();
  }

  List<String> _graphExtractionProviders() {
    return globalModelServiceManager
        .getEnabledProviders()
        .where(
          (provider) =>
              _graphExtractionModelsForProvider(provider.id).isNotEmpty,
        )
        .map((provider) => provider.id)
        .toList();
  }

  List<ModelConfig> _graphExtractionModelsForProvider(String providerId) {
    return globalModelServiceManager
        .getModelsByProvider(providerId)
        .where((item) => item.isEnabled)
        .where(_isGraphExtractionCandidateModel)
        .toList();
  }

  bool _isEmbeddingCandidateModel(ModelConfig model) {
    final lowerName = model.modelName.toLowerCase();
    return model.isEmbeddingModel ||
        lowerName.startsWith('bge-') ||
        lowerName.startsWith('e5-') ||
        lowerName.startsWith('gte-');
  }

  bool _isRerankCandidateModel(ModelConfig model) {
    return model.isRerankModel || model.isCrossEncoderRerankModel;
  }

  bool _isGraphExtractionCandidateModel(ModelConfig model) {
    if (model.isEmbeddingModel ||
        model.isRerankModel ||
        model.isCrossEncoderRerankModel) {
      return false;
    }
    final mode = model.resolvedMode;
    return mode == null || mode == 'chat' || mode == 'responses';
  }

  Future<void> _persistRetrievalStoryConfig({
    required String? embeddingProviderId,
    required String? embeddingModelId,
    required String? rerankProviderId,
    required String? rerankModelId,
    required String? graphExtractionProviderId,
    required String? graphExtractionModelId,
  }) async {
    final workspace = _currentWorkspace;
    if (workspace == null) return;

    final current = Map<String, dynamic>.from(
      workspace.storyConfigDraft ?? const <String, dynamic>{},
    );
    final nextPatch = {
      ...current,
      'retrieval_embedding_provider_id': embeddingProviderId,
      'retrieval_embedding_model_id': embeddingModelId,
      'retrieval_rerank_provider_id': rerankProviderId,
      'retrieval_rerank_model_id': rerankModelId,
      'graph_extraction_provider_id': graphExtractionProviderId,
      'graph_extraction_model_id': graphExtractionModelId,
    };

    if (current['retrieval_embedding_provider_id']?.toString() ==
            embeddingProviderId &&
        current['retrieval_embedding_model_id']?.toString() ==
            embeddingModelId &&
        current['retrieval_rerank_provider_id']?.toString() ==
            rerankProviderId &&
        current['retrieval_rerank_model_id']?.toString() == rerankModelId &&
        current['graph_extraction_provider_id']?.toString() ==
            graphExtractionProviderId &&
        current['graph_extraction_model_id']?.toString() ==
            graphExtractionModelId) {
      return;
    }

    await _service.patchStoryConfig(
      workspaceId: workspace.workspaceId,
      patch: nextPatch,
    );
    await _refreshWorkspace(workspace.workspaceId);
  }

  Future<void> _openModelConfigPage() async {
    final workspace = _currentWorkspace;
    if (workspace == null) return;
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => RpModelConfigPage(
          title: 'Prestory Setup · 模型配置',
          subtitle:
              '将 SetupAgent 对话模型和 retrieval 外部模型移到独立页面，避免在 setup 主界面占据过多空间。',
          agentSectionTitle: 'SetupAgent 模型',
          agentSectionDescription:
              '这里选择当前 setup 讨论轮次使用的 agent 模型，只影响前端当前工作区的对话发送。',
          retrievalSectionTitle: 'Retrieval 外部模型',
          retrievalSectionDescription:
              'Embedding 影响入库向量化，Rerank 影响检索重排，Graph Extraction 影响异步关系抽取；修改后会写入当前 workspace 的 story_config。',
          agentProviders: _agentProviders(),
          agentModelsForProvider: _agentModelsForProvider,
          initialAgentProviderId: _selectedProviderId,
          initialAgentModelId: _selectedModelId,
          onAgentSelectionChanged: _updateAgentSelection,
          agentEmptyHint:
              '当前没有识别到可用于 SetupAgent 的模型。需要模型具备 LiteLLM 模板解析出的 function calling/tool_choice 能力。',
          retrievalEmbeddingProviderIds: _retrievalEmbeddingProviders(),
          retrievalEmbeddingModelsForProvider:
              _retrievalEmbeddingModelsForProvider,
          retrievalRerankProviderIds: _retrievalRerankProviders(),
          retrievalRerankModelsForProvider: _retrievalRerankModelsForProvider,
          retrievalGraphExtractionProviderIds: _graphExtractionProviders(),
          retrievalGraphExtractionModelsForProvider:
              _graphExtractionModelsForProvider,
          initialRetrievalEmbeddingProviderId:
              _selectedRetrievalEmbeddingProviderId,
          initialRetrievalEmbeddingModelId: _selectedRetrievalEmbeddingModelId,
          initialRetrievalRerankProviderId: _selectedRetrievalRerankProviderId,
          initialRetrievalRerankModelId: _selectedRetrievalRerankModelId,
          initialRetrievalGraphExtractionProviderId:
              _selectedGraphExtractionProviderId,
          initialRetrievalGraphExtractionModelId:
              _selectedGraphExtractionModelId,
          onPersistRetrievalConfig: _persistRetrievalStoryConfig,
          embeddingEmptyHint:
              '当前没有识别到 embedding 模型。可在模型管理页给模型添加 embedding 能力，或使用名称包含 embedding / bge / e5 / gte 的模型。',
          rerankEmptyHint:
              '当前没有识别到 rerank 模型。可在模型管理页给模型添加 rerank / cross_encoder_rerank 能力。',
          graphExtractionEmptyHint:
              '当前没有识别到可用于 graph extraction 的文本模型。需要启用一个非 embedding / rerank 的 chat 或 responses 模型。',
        ),
      ),
    );
  }

  Future<void> _refreshCurrentRetrievalMaintenance({
    bool silent = false,
  }) async {
    final workspace = _currentWorkspace;
    if (workspace == null) return;
    await _refreshRetrievalMaintenance(workspace.storyId, silent: silent);
  }

  Future<void> _refreshRetrievalMaintenance(
    String storyId, {
    bool silent = false,
  }) async {
    final token = ++_retrievalMaintenanceRequestToken;
    if (mounted) {
      setState(() {
        _isLoadingRetrievalMaintenance = true;
        if (_retrievalMaintenance?.storyId != storyId) {
          _retrievalMaintenance = null;
        }
        _retrievalMaintenanceError = null;
      });
    }

    try {
      final snapshot = await _retrievalService.getStoryMaintenance(storyId);
      if (!mounted || token != _retrievalMaintenanceRequestToken) return;
      setState(() {
        _retrievalMaintenance = snapshot;
        _retrievalMaintenanceError = null;
      });
    } catch (e) {
      if (!mounted || token != _retrievalMaintenanceRequestToken) return;
      setState(() {
        _retrievalMaintenanceError = e.toString();
      });
      if (!silent) {
        OwuiSnackBars.error(
          context,
          message: '加载 retrieval maintenance 失败: $e',
        );
      }
    } finally {
      if (mounted && token == _retrievalMaintenanceRequestToken) {
        setState(() {
          _isLoadingRetrievalMaintenance = false;
        });
      }
    }

    await _refreshMemoryGraphMaintenance(storyId, silent: true);
  }

  Future<void> _refreshMemoryGraphMaintenance(
    String storyId, {
    bool silent = false,
  }) async {
    final token = ++_memoryGraphMaintenanceRequestToken;
    if (mounted) {
      setState(() {
        _isLoadingMemoryGraphMaintenance = true;
        if (_memoryGraphMaintenance?.storyId != storyId) {
          _memoryGraphMaintenance = null;
        }
        _memoryGraphMaintenanceError = null;
      });
    }

    try {
      final snapshot = await _retrievalService.getGraphMaintenance(storyId);
      if (!mounted || token != _memoryGraphMaintenanceRequestToken) return;
      setState(() {
        _memoryGraphMaintenance = snapshot;
        _memoryGraphMaintenanceError = null;
      });
    } catch (e) {
      if (!mounted || token != _memoryGraphMaintenanceRequestToken) return;
      setState(() {
        _memoryGraphMaintenanceError = e.toString();
      });
      if (!silent) {
        OwuiSnackBars.error(
          context,
          message: '加载 memory graph maintenance 失败: $e',
        );
      }
    } finally {
      if (mounted && token == _memoryGraphMaintenanceRequestToken) {
        setState(() {
          _isLoadingMemoryGraphMaintenance = false;
        });
      }
    }
  }

  Future<void> _refreshMemoryGraphNeighborhood({
    String? nodeId,
    bool silent = false,
  }) async {
    final workspace = _currentWorkspace;
    if (workspace == null) return;
    final token = ++_memoryGraphNeighborhoodRequestToken;
    if (mounted) {
      setState(() {
        _isLoadingMemoryGraphNeighborhood = true;
        _memoryGraphNeighborhoodError = null;
      });
    }

    try {
      final response = await _retrievalService.getGraphNeighborhood(
        workspace.storyId,
        nodeId: nodeId,
        maxDepth: _memoryGraphMaxDepth,
        maxNodes: _memoryGraphMaxNodes,
        maxEdges: _memoryGraphMaxEdges,
      );
      if (!mounted || token != _memoryGraphNeighborhoodRequestToken) return;
      setState(() {
        _memoryGraphNeighborhood = response;
        _memoryGraphNeighborhoodError = null;
        if (nodeId != null && nodeId.isNotEmpty) {
          _selectedMemoryGraphNodeId = nodeId;
          _selectedMemoryGraphEdgeId = null;
        } else if (response.nodes.every(
          (node) => node.id != _selectedMemoryGraphNodeId,
        )) {
          _selectedMemoryGraphNodeId = null;
          _selectedMemoryGraphEdgeId = null;
        }
      });
    } catch (e) {
      if (!mounted || token != _memoryGraphNeighborhoodRequestToken) return;
      setState(() {
        _memoryGraphNeighborhoodError = e.toString();
      });
      if (!silent) {
        OwuiSnackBars.error(
          context,
          message: '加载 memory graph neighborhood 失败: $e',
        );
      }
    } finally {
      if (mounted && token == _memoryGraphNeighborhoodRequestToken) {
        setState(() {
          _isLoadingMemoryGraphNeighborhood = false;
        });
      }
    }
  }

  Future<void> _runRetrievalMaintenanceAction({
    required String actionLabel,
    required Future<String> Function() action,
  }) async {
    if (_isRunningRetrievalMaintenanceAction) return;
    final workspace = _currentWorkspace;
    if (workspace == null) return;

    setState(() {
      _isRunningRetrievalMaintenanceAction = true;
      _retrievalMaintenanceActionLabel = actionLabel;
    });

    try {
      final successMessage = await action();
      if (!mounted) return;
      OwuiSnackBars.success(context, message: successMessage);
      await _refreshRetrievalMaintenance(workspace.storyId, silent: true);
    } catch (e) {
      if (!mounted) return;
      OwuiSnackBars.error(context, message: '$actionLabel 失败: $e');
    } finally {
      if (mounted) {
        setState(() {
          _isRunningRetrievalMaintenanceAction = false;
          _retrievalMaintenanceActionLabel = null;
        });
      }
    }
  }

  Future<void> _reindexRetrievalStory() async {
    final workspace = _currentWorkspace;
    if (workspace == null) return;
    await _runRetrievalMaintenanceAction(
      actionLabel: '提交 story reindex',
      action: () async {
        final jobs = await _retrievalService.reindexStory(workspace.storyId);
        if (jobs.isEmpty) return '没有可重建的 retrieval 资产';
        return '已提交 ${jobs.length} 个 story reindex job';
      },
    );
  }

  Future<void> _backfillRetrievalStory() async {
    final workspace = _currentWorkspace;
    if (workspace == null) return;
    await _runRetrievalMaintenanceAction(
      actionLabel: '提交 story backfill',
      action: () async {
        final jobs = await _retrievalService.backfillStoryEmbeddings(
          workspace.storyId,
        );
        if (jobs.isEmpty) return '当前没有需要 backfill 的 embedding';
        return '已提交 ${jobs.length} 个 story backfill job';
      },
    );
  }

  Future<void> _retryFailedRetrievalStoryJobs() async {
    final workspace = _currentWorkspace;
    if (workspace == null) return;
    await _runRetrievalMaintenanceAction(
      actionLabel: '重试 story failed jobs',
      action: () async {
        final result = await _retrievalService.retryFailedStoryJobs(
          workspace.storyId,
        );
        if (result.retriedJobs.isEmpty) return '当前没有可重试的 failed jobs';
        return '已重试 ${result.retriedJobs.length} 个 story failed job';
      },
    );
  }

  Future<void> _reindexRetrievalCollection(
    RpRetrievalCollectionMaintenanceSnapshot snapshot,
  ) async {
    await _runRetrievalMaintenanceAction(
      actionLabel: '提交 collection reindex',
      action: () async {
        final jobs = await _retrievalService.reindexCollection(
          snapshot.collectionId,
        );
        if (jobs.isEmpty) {
          return 'Collection ${snapshot.collectionKind} 当前没有可重建资产';
        }
        return 'Collection ${snapshot.collectionKind} 已提交 ${jobs.length} 个 reindex job';
      },
    );
  }

  Future<void> _backfillRetrievalCollection(
    RpRetrievalCollectionMaintenanceSnapshot snapshot,
  ) async {
    await _runRetrievalMaintenanceAction(
      actionLabel: '提交 collection backfill',
      action: () async {
        final jobs = await _retrievalService.backfillCollectionEmbeddings(
          snapshot.collectionId,
        );
        if (jobs.isEmpty) {
          return 'Collection ${snapshot.collectionKind} 当前没有需要 backfill 的 embedding';
        }
        return 'Collection ${snapshot.collectionKind} 已提交 ${jobs.length} 个 backfill job';
      },
    );
  }

  Future<void> _retryFailedRetrievalCollectionJobs(
    RpRetrievalCollectionMaintenanceSnapshot snapshot,
  ) async {
    await _runRetrievalMaintenanceAction(
      actionLabel: '重试 collection failed jobs',
      action: () async {
        final result = await _retrievalService.retryFailedCollectionJobs(
          snapshot.collectionId,
        );
        if (result.retriedJobs.isEmpty) {
          return 'Collection ${snapshot.collectionKind} 当前没有可重试的 failed jobs';
        }
        return 'Collection ${snapshot.collectionKind} 已重试 ${result.retriedJobs.length} 个 failed job';
      },
    );
  }

  Future<void> _retryRetrievalJob(RpRetrievalIndexJob job) async {
    await _runRetrievalMaintenanceAction(
      actionLabel: '重试单个 retrieval job',
      action: () async {
        final retried = await _retrievalService.retryJob(job.jobId);
        return '已重试 ${retried.jobKind} job ${retried.jobId}';
      },
    );
  }

  Future<void> _sendTurn() async {
    final workspace = _currentWorkspace;
    final modelId = _selectedModelId;
    final userPrompt = _messageController.text.trim();
    if (workspace == null ||
        modelId == null ||
        userPrompt.isEmpty ||
        _isSending) {
      return;
    }
    final modelWithProvider = globalModelServiceManager.getModelWithProvider(
      modelId,
    );
    if (modelWithProvider == null) {
      OwuiSnackBars.warning(context, message: '请先选择可用模型');
      return;
    }

    final entries = _dialogues.putIfAbsent(workspace.workspaceId, () => []);
    final userEntry = _SetupChatEntry.user(userPrompt);
    final assistantEntry = _SetupChatEntry.assistantStreaming();
    final history = _historyFor(entries);
    setState(() {
      _isSending = true;
      entries.add(userEntry);
      entries.add(assistantEntry);
      _messageController.clear();
    });

    try {
      await for (final event in _service.streamTurn(
        workspaceId: workspace.workspaceId,
        modelId: modelId,
        providerId: modelWithProvider.provider.id,
        targetStep: _targetStepForSelectedStage(workspace),
        history: history,
        userPrompt: userPrompt,
      )) {
        if (!mounted) return;
        setState(() {
          switch (event.type) {
            case AIStreamEventType.thinking:
              assistantEntry.thinking += event.text ?? '';
              break;
            case AIStreamEventType.text:
              assistantEntry.content += event.text ?? '';
              break;
            case AIStreamEventType.toolCall:
              final toolNames = (event.toolCalls ?? const [])
                  .map((item) => item['function']?['name']?.toString() ?? '')
                  .where((name) => name.isNotEmpty)
                  .join(', ');
              if (toolNames.isNotEmpty) {
                assistantEntry.toolEvents.add('Tool call: $toolNames');
              }
              break;
            case AIStreamEventType.toolStarted:
              assistantEntry.toolEvents.add(
                'Tool started: ${event.toolName ?? event.callId ?? 'unknown'}',
              );
              break;
            case AIStreamEventType.toolResult:
              assistantEntry.toolEvents.add(
                'Tool result: ${event.toolName ?? event.callId ?? 'unknown'}',
              );
              break;
            case AIStreamEventType.toolError:
              assistantEntry.toolEvents.add(
                'Tool error: ${event.toolName ?? event.callId ?? 'unknown'}',
              );
              break;
            case AIStreamEventType.usage:
              break;
          }
        });
      }
    } catch (e) {
      assistantEntry.content = assistantEntry.content.isEmpty
          ? '执行失败: $e'
          : assistantEntry.content;
      if (mounted) {
        OwuiSnackBars.error(context, message: 'SetupAgent 执行失败: $e');
      }
    } finally {
      if (mounted) {
        assistantEntry.isStreaming = false;
        await _refreshWorkspace(workspace.workspaceId);
        setState(() {
          _isSending = false;
        });
      }
    }
  }

  Future<void> _acceptProposal(String proposalId) async {
    final workspace = _currentWorkspace;
    if (workspace == null) return;
    try {
      await _service.acceptCommitProposal(
        workspaceId: workspace.workspaceId,
        proposalId: proposalId,
      );
      _appendSystemNote('已接受 commit proposal');
      await _refreshWorkspace(workspace.workspaceId);
      if (!mounted) return;
      OwuiSnackBars.success(context, message: '已接受 review / commit');
    } catch (e) {
      if (!mounted) return;
      OwuiSnackBars.error(context, message: '接受 commit 失败: $e');
    }
  }

  Future<void> _rejectProposal(String proposalId) async {
    final workspace = _currentWorkspace;
    if (workspace == null) return;
    try {
      await _service.rejectCommitProposal(
        workspaceId: workspace.workspaceId,
        proposalId: proposalId,
      );
      _appendSystemNote('已退回到 discussing，继续 refinement');
      await _refreshWorkspace(workspace.workspaceId);
      if (!mounted) return;
      OwuiSnackBars.success(context, message: '已拒绝 review / commit');
    } catch (e) {
      if (!mounted) return;
      OwuiSnackBars.error(context, message: '拒绝 commit 失败: $e');
    }
  }

  Future<void> _runActivationCheck() async {
    final workspace = _currentWorkspace;
    if (workspace == null) return;
    try {
      final result = await _service.runActivationCheck(workspace.workspaceId);
      if (!mounted) return;
      setState(() {
        _lastActivationCheck = result;
      });
      await _refreshWorkspace(workspace.workspaceId);
    } catch (e) {
      if (!mounted) return;
      OwuiSnackBars.error(context, message: 'Activation check 失败: $e');
    }
  }

  Future<void> _activateStory() async {
    final workspace = _currentWorkspace;
    if (workspace == null) return;
    try {
      final result = await _storyService.activateWorkspace(
        workspace.workspaceId,
      );
      await _refreshWorkspace(workspace.workspaceId);
      if (!mounted) return;
      await Navigator.push(
        context,
        MaterialPageRoute(
          builder: (context) => LongformStoryPage(sessionId: result.sessionId),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      OwuiSnackBars.error(context, message: '激活 story 失败: $e');
    }
  }

  Future<void> _openMobileSidebar() async {
    final workspace = _currentWorkspace;
    if (workspace == null) return;
    final spacing = context.owuiSpacing;
    await showGeneralDialog<void>(
      context: context,
      barrierDismissible: true,
      barrierLabel: 'Prestory sidebar',
      barrierColor: Colors.black.withValues(alpha: 0.28),
      transitionDuration: const Duration(milliseconds: 220),
      pageBuilder: (dialogContext, _, __) {
        final screenWidth = MediaQuery.of(dialogContext).size.width;
        final panelWidth = (screenWidth * 0.82).clamp(320.0, 460.0);
        return SafeArea(
          child: Align(
            alignment: Alignment.centerRight,
            child: Container(
              width: panelWidth,
              height: double.infinity,
              margin: EdgeInsets.fromLTRB(
                spacing.md,
                spacing.lg,
                spacing.md,
                spacing.lg,
              ),
              child: Material(
                color: dialogContext.owuiColors.surfaceCard,
                elevation: 10,
                borderRadius: BorderRadius.circular(
                  dialogContext.owuiRadius.r3xl,
                ),
                clipBehavior: Clip.antiAlias,
                child: _buildSidebarContent(
                  isModal: true,
                  onClose: () => Navigator.pop(dialogContext),
                ),
              ),
            ),
          ),
        );
      },
      transitionBuilder: (_, animation, __, child) {
        final curved = CurvedAnimation(
          parent: animation,
          curve: Curves.easeOutCubic,
        );
        return SlideTransition(
          position: Tween<Offset>(
            begin: const Offset(1, 0),
            end: Offset.zero,
          ).animate(curved),
          child: FadeTransition(opacity: curved, child: child),
        );
      },
    );
  }

  void _appendSystemNote(String text) {
    final workspace = _currentWorkspace;
    if (workspace == null) return;
    final entries = _dialogues.putIfAbsent(workspace.workspaceId, () => []);
    setState(() {
      entries.add(_SetupChatEntry.system(text));
    });
  }

  List<SetupDialogueMessage> _historyFor(List<_SetupChatEntry> entries) {
    return entries
        .where(
          (entry) =>
              entry.kind == _SetupChatEntryKind.user ||
              entry.kind == _SetupChatEntryKind.assistant,
        )
        .where((entry) => entry.content.trim().isNotEmpty)
        .map(
          (entry) => SetupDialogueMessage(
            role: entry.kind == _SetupChatEntryKind.user ? 'user' : 'assistant',
            content: entry.content,
          ),
        )
        .toList();
  }

  @override
  Widget build(BuildContext context) {
    final spacing = context.owuiSpacing;
    if (_isLoading) {
      return OwuiScaffold(
        appBar: const OwuiAppBar(title: Text('Prestory Setup')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    final isWide = MediaQuery.of(context).size.width >= 1100;

    return OwuiScaffold(
      appBar: OwuiAppBar(
        title: const Text('Prestory Setup'),
        actions: [
          IconButton(
            onPressed: _createWorkspace,
            tooltip: '新建 workspace',
            icon: const Icon(Icons.add_circle_outline),
          ),
        ],
      ),
      body: Padding(
        padding: EdgeInsets.all(spacing.lg),
        child: isWide
            ? Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(flex: 5, child: _buildDiscussionPanel()),
                  SizedBox(width: spacing.lg),
                  SizedBox(width: 420, child: _buildSidebarShell()),
                ],
              )
            : Stack(
                children: [
                  Positioned.fill(child: _buildDiscussionPanel()),
                  Positioned(
                    right: 0,
                    top: 0,
                    bottom: 0,
                    child: Center(child: _buildSidebarHandle()),
                  ),
                ],
              ),
      ),
    );
  }

  Widget _buildDiscussionPanel() {
    final workspace = _currentWorkspace;
    final entries = workspace == null
        ? const <_SetupChatEntry>[]
        : (_dialogues[workspace.workspaceId] ?? const <_SetupChatEntry>[]);
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;

    return Container(
      decoration: BoxDecoration(
        color: colors.surfaceCard,
        borderRadius: BorderRadius.circular(context.owuiRadius.r3xl),
        border: Border.all(color: colors.borderSubtle),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(
              spacing.lg,
              spacing.lg,
              spacing.lg,
              spacing.md,
            ),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'SetupAgent 讨论区',
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                      SizedBox(height: spacing.xs),
                      Text(
                        workspace == null
                            ? '先创建一个 prestory workspace'
                            : '当前阶段: ${_currentStageLabel(workspace)} · 选中视图: ${_selectedStage.label} · workspace state: ${workspace.workspaceState}',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: colors.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
                if (workspace != null)
                  Chip(label: Text('v${workspace.version}')),
              ],
            ),
          ),
          Divider(height: 1, color: colors.borderSubtle),
          Expanded(
            child: Padding(
              padding: EdgeInsets.fromLTRB(
                spacing.lg,
                spacing.lg,
                spacing.lg,
                spacing.md,
              ),
              child: workspace == null
                  ? Center(
                      child: Text(
                        '点击右上角创建 workspace 后，再开始和 SetupAgent 讨论。',
                        style: Theme.of(context).textTheme.bodyLarge,
                        textAlign: TextAlign.center,
                      ),
                    )
                  : entries.isEmpty
                  ? Center(
                      child: Text(
                        '当前还没有对话。发送第一条指令开始收敛 ${_currentStageLabel(workspace)}。',
                        style: Theme.of(context).textTheme.bodyMedium,
                        textAlign: TextAlign.center,
                      ),
                    )
                  : ListView.separated(
                      itemCount: entries.length,
                      separatorBuilder: (_, __) => SizedBox(height: spacing.md),
                      itemBuilder: (context, index) =>
                          _buildMessage(entries[index]),
                    ),
            ),
          ),
          Padding(
            padding: EdgeInsets.fromLTRB(
              spacing.lg,
              spacing.sm,
              spacing.lg,
              spacing.lg,
            ),
            child: Container(
              padding: EdgeInsets.all(spacing.sm),
              decoration: BoxDecoration(
                color: colors.surface2,
                borderRadius: BorderRadius.circular(context.owuiRadius.r3xl),
                border: Border.all(color: colors.borderSubtle),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (workspace != null) ...[
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            'Story: ${workspace.storyId}',
                            style: Theme.of(context).textTheme.bodySmall
                                ?.copyWith(color: colors.textSecondary),
                          ),
                        ),
                        Text(
                          'Mode: ${workspace.mode}',
                          style: Theme.of(context).textTheme.bodySmall
                              ?.copyWith(color: colors.textSecondary),
                        ),
                      ],
                    ),
                    SizedBox(height: spacing.sm),
                  ],
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Expanded(
                        child: TextField(
                          controller: _messageController,
                          minLines: 2,
                          maxLines: 6,
                          decoration: InputDecoration(
                            labelText: '给 SetupAgent 的当前阶段指令',
                            hintText: _stagePromptHintForWorkspace(workspace!),
                            suffixIcon: _isSending
                                ? const Padding(
                                    padding: EdgeInsets.all(12),
                                    child: SizedBox(
                                      width: 16,
                                      height: 16,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                      ),
                                    ),
                                  )
                                : null,
                          ),
                        ),
                      ),
                      SizedBox(width: spacing.md),
                      FilledButton.icon(
                        onPressed: _isSending ? null : _sendTurn,
                        icon: const Icon(Icons.send),
                        label: const Text('发送'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSidebarHandle() {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    return Padding(
      padding: EdgeInsets.only(right: spacing.xs),
      child: Material(
        color: colors.surfaceCard,
        borderRadius: BorderRadius.horizontal(
          left: Radius.circular(context.owuiRadius.rXl),
        ),
        child: InkWell(
          onTap: _openMobileSidebar,
          borderRadius: BorderRadius.horizontal(
            left: Radius.circular(context.owuiRadius.rXl),
          ),
          child: Container(
            width: 42,
            height: 160,
            decoration: BoxDecoration(
              border: Border.all(color: colors.borderSubtle),
              borderRadius: BorderRadius.horizontal(
                left: Radius.circular(context.owuiRadius.rXl),
              ),
            ),
            child: RotatedBox(
              quarterTurns: 3,
              child: Center(
                child: Text(
                  '拉出边栏',
                  style: Theme.of(context).textTheme.labelMedium,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildSidebarShell() {
    final colors = context.owuiColors;
    return Container(
      decoration: BoxDecoration(
        color: colors.surfaceCard,
        borderRadius: BorderRadius.circular(context.owuiRadius.r3xl),
        border: Border.all(color: colors.borderSubtle),
      ),
      child: _buildSidebarContent(isModal: false),
    );
  }

  Widget _buildSidebarContent({required bool isModal, VoidCallback? onClose}) {
    final workspace = _currentWorkspace;
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    final embeddingProviderIds = _retrievalEmbeddingProviders();
    final rerankProviderIds = _retrievalRerankProviders();
    final graphExtractionProviderIds = _graphExtractionProviders();

    return Column(
      children: [
        Padding(
          padding: EdgeInsets.fromLTRB(
            spacing.lg,
            spacing.lg,
            spacing.lg,
            spacing.md,
          ),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Draft 预览与配置',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    SizedBox(height: spacing.xs),
                    Text(
                      workspace == null
                          ? '暂无 workspace'
                          : '右侧按创作流程逐步收敛当前步骤，不再一次性堆出全部 draft。',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: colors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              if (isModal)
                IconButton(onPressed: onClose, icon: const Icon(Icons.close)),
            ],
          ),
        ),
        Divider(height: 1, color: colors.borderSubtle),
        Expanded(
          child: ListView(
            padding: EdgeInsets.all(spacing.lg),
            children: [
              OwuiCard(
                padding: EdgeInsets.all(spacing.md),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '入口与模型',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    SizedBox(height: spacing.md),
                    DropdownButtonFormField<String>(
                      initialValue: workspace?.workspaceId,
                      decoration: const InputDecoration(labelText: 'Workspace'),
                      items: _workspaces
                          .map(
                            (item) => DropdownMenuItem<String>(
                              value: item.workspaceId,
                              child: Text(
                                '${item.storyId} · ${item.currentStage ?? item.currentStep} · ${item.workspaceState}',
                              ),
                            ),
                          )
                          .toList(),
                      onChanged: (value) async {
                        if (value == null) return;
                        await _refreshWorkspace(value, preserveStage: false);
                      },
                    ),
                    SizedBox(height: spacing.md),
                    Text(
                      '模型配置已移到独立页面。',
                      style: Theme.of(context).textTheme.titleSmall,
                    ),
                    SizedBox(height: spacing.xs),
                    Text(
                      '保留摘要和入口，避免在右侧边栏堆积大块表单。',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: colors.textSecondary,
                      ),
                    ),
                    SizedBox(height: spacing.md),
                    Text(
                      'SetupAgent: ${_formatAgentSelectionSummary(providerId: _selectedProviderId, modelId: _selectedModelId) ?? '未选择'}',
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                    SizedBox(height: spacing.xs),
                    Text(
                      'Embedding: ${_formatRetrievalSelectionSummary(providerId: _selectedRetrievalEmbeddingProviderId, modelId: _selectedRetrievalEmbeddingModelId) ?? '未设置'}',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: colors.textSecondary,
                      ),
                    ),
                    SizedBox(height: spacing.xs),
                    Text(
                      'Rerank: ${_formatRetrievalSelectionSummary(providerId: _selectedRetrievalRerankProviderId, modelId: _selectedRetrievalRerankModelId) ?? '未设置'}',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: colors.textSecondary,
                      ),
                    ),
                    SizedBox(height: spacing.xs),
                    Text(
                      'Graph Extraction: ${_formatRetrievalSelectionSummary(providerId: _selectedGraphExtractionProviderId, modelId: _selectedGraphExtractionModelId) ?? '未设置'}',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: colors.textSecondary,
                      ),
                    ),
                    SizedBox(height: spacing.md),
                    OutlinedButton.icon(
                      onPressed: workspace == null
                          ? null
                          : _openModelConfigPage,
                      icon: const Icon(Icons.tune),
                      label: const Text('打开模型配置页'),
                    ),
                    if (_agentProviders().isEmpty) ...[
                      SizedBox(height: spacing.sm),
                      Text(
                        '当前没有识别到可用于 SetupAgent 的模型。需要模型具备 LiteLLM 模板解析出的 function calling/tool_choice 能力。',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: colors.textSecondary,
                        ),
                      ),
                    ],
                    if (embeddingProviderIds.isEmpty) ...[
                      SizedBox(height: spacing.sm),
                      Text(
                        '当前没有识别到 embedding 模型。可在模型管理页给模型添加 embedding 能力，或使用名称包含 embedding / bge / e5 / gte 的模型。',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: colors.textSecondary,
                        ),
                      ),
                    ],
                    if (rerankProviderIds.isEmpty) ...[
                      SizedBox(height: spacing.sm),
                      Text(
                        '当前没有识别到 rerank 模型。可在模型管理页给模型添加 rerank / cross_encoder_rerank 能力。',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: colors.textSecondary,
                        ),
                      ),
                    ],
                    if (graphExtractionProviderIds.isEmpty) ...[
                      SizedBox(height: spacing.sm),
                      Text(
                        '当前没有识别到可用于 graph extraction 的文本模型。需要启用一个非 embedding / rerank 的 chat 或 responses 模型。',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: colors.textSecondary,
                        ),
                      ),
                    ],
                    if (workspace != null) ...[
                      SizedBox(height: spacing.md),
                      Text(
                        '当前聚焦：${_currentStageLabel(workspace)}',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: colors.textSecondary,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              SizedBox(height: spacing.lg),
              if (workspace != null) ...[
                _buildWorkspaceOverviewCard(workspace),
                SizedBox(height: spacing.lg),
                _buildStageRailCard(workspace),
                SizedBox(height: spacing.lg),
                _buildStageInspectorCard(workspace),
              ] else
                OwuiCard(
                  padding: EdgeInsets.all(spacing.lg),
                  child: const Center(child: Text('暂无 workspace')),
                ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildMessage(_SetupChatEntry entry) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    final isUser = entry.kind == _SetupChatEntryKind.user;
    final isSystem = entry.kind == _SetupChatEntryKind.system;
    final bgColor = isUser
        ? Theme.of(context).colorScheme.primary.withValues(alpha: 0.08)
        : (isSystem ? colors.surface2 : colors.surfaceCard);
    final borderColor = isUser
        ? Theme.of(context).colorScheme.primary.withValues(alpha: 0.2)
        : colors.borderSubtle;

    return Container(
      padding: EdgeInsets.all(spacing.md),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(context.owuiRadius.rXl),
        border: Border.all(color: borderColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(switch (entry.kind) {
            _SetupChatEntryKind.user => 'You',
            _SetupChatEntryKind.assistant => 'SetupAgent',
            _SetupChatEntryKind.system => 'System',
          }, style: Theme.of(context).textTheme.titleSmall),
          if (entry.thinking.isNotEmpty) ...[
            SizedBox(height: spacing.sm),
            Text(
              entry.thinking,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: colors.textSecondary,
                fontStyle: FontStyle.italic,
              ),
            ),
          ],
          if (entry.content.isNotEmpty) ...[
            SizedBox(height: spacing.sm),
            SelectableText(entry.content),
          ],
          if (entry.toolEvents.isNotEmpty) ...[
            SizedBox(height: spacing.sm),
            ...entry.toolEvents.map(
              (event) => Padding(
                padding: EdgeInsets.only(top: spacing.xs),
                child: Text(
                  event,
                  style: Theme.of(
                    context,
                  ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
                ),
              ),
            ),
          ],
          if (entry.isStreaming) ...[
            SizedBox(height: spacing.sm),
            const LinearProgressIndicator(minHeight: 2),
          ],
        ],
      ),
    );
  }

  Widget _buildProposalCard(RpSetupCommitProposal proposal) {
    final spacing = context.owuiSpacing;
    return Container(
      margin: EdgeInsets.only(bottom: spacing.md),
      padding: EdgeInsets.all(spacing.md),
      decoration: BoxDecoration(
        border: Border.all(color: context.owuiColors.borderSubtle),
        borderRadius: BorderRadius.circular(context.owuiRadius.rLg),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            proposal.reviewMessage,
            style: Theme.of(context).textTheme.titleSmall,
          ),
          SizedBox(height: spacing.sm),
          Text('Step: ${proposal.stepId}'),
          if ((proposal.reason ?? '').isNotEmpty)
            Text('Reason: ${proposal.reason}'),
          if (proposal.unresolvedWarnings.isNotEmpty)
            ...proposal.unresolvedWarnings.map(
              (warning) => Text('Warning: $warning'),
            ),
          SizedBox(height: spacing.md),
          Row(
            children: [
              FilledButton(
                onPressed: () => _acceptProposal(proposal.proposalId),
                child: const Text('Accept'),
              ),
              SizedBox(width: spacing.sm),
              OutlinedButton(
                onPressed: () => _rejectProposal(proposal.proposalId),
                child: const Text('Reject'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildSidebarSectionCard({
    required String title,
    required String subtitle,
    required List<Widget> children,
  }) {
    final spacing = context.owuiSpacing;
    return OwuiCard(
      padding: EdgeInsets.all(spacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          SizedBox(height: spacing.xs),
          Text(
            subtitle,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: context.owuiColors.textSecondary,
            ),
          ),
          SizedBox(height: spacing.md),
          ...children,
        ],
      ),
    );
  }

  Widget _buildWorkspaceOverviewCard(RpSetupWorkspace workspace) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    final stageId = _workspaceCurrentStageId(workspace);
    return OwuiCard(
      padding: EdgeInsets.all(spacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Workspace Overview',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    SizedBox(height: spacing.xs),
                    Text(
                      '后端返回的 stage plan、stage state 和 draft blocks 直接驱动页面，不再写死在前端。',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: colors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              Chip(label: Text(_currentStageLabel(workspace))),
            ],
          ),
          SizedBox(height: spacing.md),
          Wrap(
            spacing: spacing.sm,
            runSpacing: spacing.sm,
            children: [
              _buildMetricChip('Steps', workspace.stepStates.length),
              _buildMetricChip('Stages', _stagePlanFor(workspace).length),
              _buildMetricChip(
                'Draft Blocks',
                workspace.stageDraftBlocks.length,
              ),
              _buildMetricChip('Accepted', workspace.acceptedCommits.length),
              _buildMetricChip(
                'Proposals',
                workspace.pendingCommitProposals.length,
              ),
              if (stageId != null)
                Chip(
                  label: Text('Stage ${_stageDisplayLabel(stageId)}'),
                  visualDensity: VisualDensity.compact,
                ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildStageRailCard(RpSetupWorkspace workspace) {
    final spacing = context.owuiSpacing;
    final stages = _stagePlanFor(workspace);
    return _buildSidebarSectionCard(
      title: 'Stage Plan',
      subtitle:
          '从 workspace 的 stage_plan 读取顺序，卡片状态来自 stage_states 和 draft_blocks。',
      children: [
        if (stages.isEmpty)
          const Text('当前 workspace 没有 stage plan。')
        else
          SizedBox(
            height: 124,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: stages.length,
              separatorBuilder: (_, __) => SizedBox(width: spacing.sm),
              itemBuilder: (context, index) {
                final stageId = stages[index];
                return _buildStageRailItem(
                  workspace: workspace,
                  stageId: stageId,
                  index: index,
                );
              },
            ),
          ),
      ],
    );
  }

  Widget _buildStageRailItem({
    required RpSetupWorkspace workspace,
    required String stageId,
    required int index,
  }) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    final selected = _stageIdFor(_selectedStage) == stageId;
    final meta = _stageMetaFor(stageId);
    final state = _stageStateLabel(workspace, stageId);
    final bgColor = selected
        ? Theme.of(context).colorScheme.primary.withValues(alpha: 0.09)
        : colors.surfaceCard;
    final borderColor = selected
        ? Theme.of(context).colorScheme.primary.withValues(alpha: 0.28)
        : colors.borderSubtle;

    return SizedBox(
      width: 184,
      child: Material(
        color: bgColor,
        borderRadius: BorderRadius.circular(context.owuiRadius.rLg),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: () {
            final nextStage = _stageForId(stageId);
            if (nextStage == null) return;
            setState(() {
              _selectedStage = nextStage;
            });
          },
          child: Container(
            padding: EdgeInsets.all(spacing.sm),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(context.owuiRadius.rLg),
              border: Border.all(color: borderColor),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      width: 30,
                      height: 30,
                      decoration: BoxDecoration(
                        color: Theme.of(context).colorScheme.primary.withValues(
                          alpha: selected ? 0.14 : 0.08,
                        ),
                        borderRadius: BorderRadius.circular(
                          context.owuiRadius.rLg,
                        ),
                      ),
                      child: Icon(
                        meta.icon,
                        size: 16,
                        color: Theme.of(context).colorScheme.primary,
                      ),
                    ),
                    SizedBox(width: spacing.sm),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            meta.title,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: Theme.of(context).textTheme.titleSmall,
                          ),
                          SizedBox(height: spacing.xs),
                          Text(
                            '#${index + 1} · ${_stageDisplayLabel(stageId)}',
                            style: Theme.of(context).textTheme.bodySmall
                                ?.copyWith(color: colors.textSecondary),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                SizedBox(height: spacing.sm),
                Align(
                  alignment: Alignment.centerLeft,
                  child: Chip(
                    label: Text(state),
                    visualDensity: VisualDensity.compact,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildStageInspectorCard(RpSetupWorkspace workspace) {
    final stageId = _stageIdFor(_selectedStage);
    final meta = _stageMetaFor(stageId);
    final block = _stageBlockFor(workspace, stageId);
    final spacing = context.owuiSpacing;
    final stageBody = _buildStageBody(workspace, stageId, block);

    return _buildSidebarSectionCard(
      title: meta.title,
      subtitle: meta.description,
      children: [
        Wrap(
          spacing: spacing.sm,
          runSpacing: spacing.sm,
          children: [
            Chip(
              label: Text(_stageStateLabel(workspace, stageId)),
              visualDensity: VisualDensity.compact,
            ),
            _buildMetricChip('Entries', block?.entries.length ?? 0),
            _buildMetricChip(
              'Sections',
              block?.entries.fold<int>(
                    0,
                    (count, entry) => count + entry.sections.length,
                  ) ??
                  0,
            ),
            Chip(label: Text(stageId), visualDensity: VisualDensity.compact),
          ],
        ),
        SizedBox(height: spacing.md),
        ...stageBody,
      ],
    );
  }

  List<Widget> _buildStageBody(
    RpSetupWorkspace workspace,
    String stageId,
    RpSetupStageDraftBlock? block,
  ) {
    final spacing = context.owuiSpacing;
    final stage = _stageForId(stageId);
    switch (stage) {
      case _SetupWizardStage.worldBackground:
        if (block != null && block.entries.isNotEmpty) {
          return _buildStageDraftBlockWidgets(block);
        }
        return _buildFoundationEntryWidgets(
          _worldFoundationEntries(workspace),
          emptyText: '还没有世界观背景条目。',
        );
      case _SetupWizardStage.characterDesign:
        if (block != null && block.entries.isNotEmpty) {
          return _buildStageDraftBlockWidgets(block);
        }
        return _buildFoundationEntryWidgets(
          _characterFoundationEntries(workspace),
          emptyText: '还没有角色设定条目。',
        );
      case _SetupWizardStage.plotBlueprint:
        if (block != null && block.entries.isNotEmpty) {
          return _buildStageDraftBlockWidgets(block);
        }
        return _buildBlueprintWidgets(workspace);
      case _SetupWizardStage.writerConfig:
        if (block != null && block.entries.isNotEmpty) {
          return _buildStageDraftBlockWidgets(block);
        }
        return _buildWritingContractWidgets(workspace);
      case _SetupWizardStage.workerConfig:
        if (block != null && block.entries.isNotEmpty) {
          return _buildStageDraftBlockWidgets(block);
        }
        return _buildStoryConfigWidgets(workspace);
      case _SetupWizardStage.overview:
        return [
          ..._buildOverviewWidgets(workspace),
          SizedBox(height: spacing.md),
          Text(
            '待 Review / Commit',
            style: Theme.of(context).textTheme.titleSmall,
          ),
          SizedBox(height: spacing.sm),
          if (workspace.pendingCommitProposals.isEmpty)
            const Text('当前没有待 review proposal')
          else
            ...workspace.pendingCommitProposals.map(_buildProposalCard),
          SizedBox(height: spacing.md),
          _buildRetrievalMaintenancePanel(workspace),
          SizedBox(height: spacing.md),
          Text(
            'Retrieval Ingestion',
            style: Theme.of(context).textTheme.titleSmall,
          ),
          SizedBox(height: spacing.sm),
          ..._buildRetrievalOverviewWidgets(workspace),
        ];
      case _SetupWizardStage.activate:
        return [
          Row(
            children: [
              OutlinedButton.icon(
                onPressed: _runActivationCheck,
                icon: const Icon(Icons.play_arrow),
                label: const Text('Run Check'),
              ),
              SizedBox(width: spacing.sm),
              if (_lastActivationCheck?.ready ?? false)
                FilledButton.icon(
                  onPressed: _activateStory,
                  icon: const Icon(Icons.launch_outlined),
                  label: const Text('Activate Story'),
                ),
            ],
          ),
          SizedBox(height: spacing.md),
          if (_lastActivationCheck == null)
            const Text('尚未执行 activation check')
          else ...[
            Text(
              _lastActivationCheck!.ready ? '当前已满足激活前提。' : '当前还不能激活，需要先处理阻塞项。',
            ),
            if (_lastActivationCheck!.blockingIssues.isNotEmpty) ...[
              SizedBox(height: spacing.sm),
              ..._lastActivationCheck!.blockingIssues.map(
                (issue) => Text('Blocking: $issue'),
              ),
            ],
            if (_lastActivationCheck!.warnings.isNotEmpty) ...[
              SizedBox(height: spacing.sm),
              ..._lastActivationCheck!.warnings.map(
                (item) => Text('Warning: $item'),
              ),
            ],
          ],
        ];
      default:
        if (block != null && block.entries.isNotEmpty) {
          return _buildStageDraftBlockWidgets(block);
        }
        return const [Text('当前 stage 还没有可展示的内容。')];
    }
  }

  List<Widget> _buildStageDraftBlockWidgets(RpSetupStageDraftBlock block) {
    final spacing = context.owuiSpacing;
    final widgets = <Widget>[];
    if (block.notes != null && block.notes!.trim().isNotEmpty) {
      widgets.add(
        Container(
          width: double.infinity,
          padding: EdgeInsets.all(spacing.md),
          decoration: BoxDecoration(
            color: context.owuiColors.surface2,
            borderRadius: BorderRadius.circular(context.owuiRadius.rLg),
            border: Border.all(color: context.owuiColors.borderSubtle),
          ),
          child: Text(block.notes!),
        ),
      );
      widgets.add(SizedBox(height: spacing.md));
    }

    if (block.entries.isEmpty) {
      widgets.add(const Text('当前 stage block 还没有条目。'));
      return widgets;
    }

    for (final entry in block.entries) {
      widgets.add(_buildDraftEntryCard(entry));
      widgets.add(SizedBox(height: spacing.md));
    }
    widgets.removeLast();
    return widgets;
  }

  Widget _buildDraftEntryCard(RpSetupDraftEntry entry) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    return Container(
      width: double.infinity,
      margin: EdgeInsets.only(bottom: spacing.sm),
      padding: EdgeInsets.all(spacing.md),
      decoration: BoxDecoration(
        color: colors.surfaceCard,
        borderRadius: BorderRadius.circular(context.owuiRadius.rLg),
        border: Border.all(color: colors.borderSubtle),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      entry.title,
                      style: Theme.of(context).textTheme.titleSmall,
                    ),
                    SizedBox(height: spacing.xs),
                    Text(
                      entry.displayLabel ?? entry.semanticPath,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: colors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              Chip(
                label: Text(entry.entryType),
                visualDensity: VisualDensity.compact,
              ),
            ],
          ),
          if (entry.summary != null && entry.summary!.trim().isNotEmpty) ...[
            SizedBox(height: spacing.sm),
            Text(entry.summary!),
          ],
          if (entry.aliases.isNotEmpty || entry.tags.isNotEmpty) ...[
            SizedBox(height: spacing.sm),
            Wrap(
              spacing: spacing.xs,
              runSpacing: spacing.xs,
              children: [
                ...entry.aliases.map(
                  (alias) => Chip(
                    label: Text(alias),
                    visualDensity: VisualDensity.compact,
                  ),
                ),
                ...entry.tags.map(
                  (tag) => Chip(
                    label: Text(tag),
                    visualDensity: VisualDensity.compact,
                  ),
                ),
              ],
            ),
          ],
          if (entry.sections.isNotEmpty) ...[
            SizedBox(height: spacing.md),
            ...entry.sections.map((section) => _buildDraftSectionCard(section)),
          ],
        ],
      ),
    );
  }

  Widget _buildDraftSectionCard(RpSetupDraftSection section) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    return Container(
      width: double.infinity,
      margin: EdgeInsets.only(bottom: spacing.sm),
      padding: EdgeInsets.all(spacing.sm),
      decoration: BoxDecoration(
        color: colors.surface2,
        borderRadius: BorderRadius.circular(context.owuiRadius.rLg),
        border: Border.all(color: colors.borderSubtle),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  section.title,
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ),
              Chip(
                label: Text(section.retrievalRole),
                visualDensity: VisualDensity.compact,
              ),
            ],
          ),
          if (section.tags.isNotEmpty) ...[
            SizedBox(height: spacing.xs),
            Wrap(
              spacing: spacing.xs,
              runSpacing: spacing.xs,
              children: section.tags
                  .map(
                    (tag) => Chip(
                      label: Text(tag),
                      visualDensity: VisualDensity.compact,
                    ),
                  )
                  .toList(),
            ),
          ],
          SizedBox(height: spacing.sm),
          _buildSectionContent(section),
        ],
      ),
    );
  }

  Widget _buildSectionContent(RpSetupDraftSection section) {
    final content = section.content;
    final spacing = context.owuiSpacing;
    switch (section.kind) {
      case 'text':
        final text = content['text']?.toString().trim() ?? '';
        return Text(text.isEmpty ? '暂无内容' : text);
      case 'list':
        final items = (content['items'] as List? ?? const [])
            .map((item) => item.toString())
            .toList();
        if (items.isEmpty) {
          return const Text('暂无条目');
        }
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: items
              .map(
                (item) => Padding(
                  padding: EdgeInsets.only(bottom: spacing.xs),
                  child: Text('• $item'),
                ),
              )
              .toList(),
        );
      case 'key_value':
        final values = content['values'];
        if (values is! Map || values.isEmpty) {
          return const Text('暂无键值内容');
        }
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: values.entries
              .map(
                (entry) => Padding(
                  padding: EdgeInsets.only(bottom: spacing.xs),
                  child: Text('${entry.key}: ${entry.value}'),
                ),
              )
              .toList(),
        );
      default:
        return Text(content.toString());
    }
  }

  _SetupWizardStage _preferredStageForWorkspace(RpSetupWorkspace workspace) {
    if (workspace.workspaceState == 'activated') {
      return _SetupWizardStage.activate;
    }
    final currentStageId = workspace.currentStage;
    if (currentStageId != null) {
      final stage = _stageForId(currentStageId);
      if (stage != null) {
        return stage;
      }
    }
    switch (workspace.currentStep) {
      case 'foundation':
        return _characterFoundationEntries(workspace).isEmpty
            ? _SetupWizardStage.worldBackground
            : _SetupWizardStage.characterDesign;
      case 'longform_blueprint':
        return _SetupWizardStage.plotBlueprint;
      case 'writing_contract':
        return _SetupWizardStage.writerConfig;
      case 'story_config':
        return _SetupWizardStage.workerConfig;
      default:
        return _SetupWizardStage.worldBackground;
    }
  }

  bool _isSelectedStageOutOfPlan(RpSetupWorkspace workspace) {
    final currentStageId = _stageIdFor(_selectedStage);
    final plan = _stagePlanFor(workspace);
    if (plan.isEmpty) return true;
    return !plan.contains(currentStageId);
  }

  String? _targetStepForSelectedStage(RpSetupWorkspace workspace) {
    final stageId = _stageIdFor(_selectedStage);
    if (workspace.currentStage == stageId) {
      return null;
    }
    return _stageMetaFor(stageId).legacyStepId ?? workspace.currentStep;
  }

  List<Map<String, dynamic>> _foundationEntries(RpSetupWorkspace workspace) {
    final foundation = workspace.foundationDraft;
    if (foundation == null) return const [];
    final entries = foundation['entries'] as List? ?? const [];
    return entries
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
  }

  List<Map<String, dynamic>> _worldFoundationEntries(
    RpSetupWorkspace workspace,
  ) {
    return _foundationEntries(workspace)
        .where((item) => (item['domain']?.toString() ?? '') != 'character')
        .toList();
  }

  List<Map<String, dynamic>> _characterFoundationEntries(
    RpSetupWorkspace workspace,
  ) {
    return _foundationEntries(workspace)
        .where((item) => (item['domain']?.toString() ?? '') == 'character')
        .toList();
  }

  List<Widget> _buildFoundationEntryWidgets(
    List<Map<String, dynamic>> entries, {
    required String emptyText,
  }) {
    final spacing = context.owuiSpacing;
    if (entries.isEmpty) return [Text(emptyText)];
    return entries
        .map(
          (entry) => Container(
            margin: EdgeInsets.only(bottom: spacing.md),
            padding: EdgeInsets.all(spacing.md),
            decoration: BoxDecoration(
              color: context.owuiColors.surface2,
              borderRadius: BorderRadius.circular(context.owuiRadius.rLg),
              border: Border.all(color: context.owuiColors.borderSubtle),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  entry['title']?.toString().isNotEmpty == true
                      ? entry['title'].toString()
                      : (entry['path']?.toString() ??
                            entry['entry_id']?.toString() ??
                            '未命名条目'),
                  style: Theme.of(context).textTheme.titleSmall,
                ),
                SizedBox(height: spacing.xs),
                Text(
                  '${entry['domain'] ?? 'foundation'} · ${entry['path'] ?? entry['entry_id'] ?? ''}',
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: context.owuiColors.textSecondary,
                  ),
                ),
                SizedBox(height: spacing.sm),
                Text(_entrySummary(entry)),
              ],
            ),
          ),
        )
        .toList();
  }

  String _entrySummary(Map<String, dynamic> entry) {
    final content = entry['content'];
    if (content is Map && content['summary'] != null) {
      return content['summary'].toString();
    }
    if (content is String && content.trim().isNotEmpty) {
      return content.trim();
    }
    return content?.toString() ?? '暂无摘要';
  }

  List<Widget> _buildBlueprintWidgets(RpSetupWorkspace workspace) {
    final blueprint = workspace.longformBlueprintDraft;
    if (blueprint == null) {
      return const [Text('还没有剧情与伏笔设计。')];
    }
    final spacing = context.owuiSpacing;
    final widgets = <Widget>[
      ..._buildTextBlock(
        label: 'Premise',
        value: blueprint['premise']?.toString(),
      ),
      ..._buildTextBlock(
        label: 'Central Conflict',
        value: blueprint['central_conflict']?.toString(),
      ),
      ..._buildTextBlock(
        label: 'Protagonist Arc',
        value: blueprint['protagonist_arc']?.toString(),
      ),
      ..._buildTextBlock(
        label: 'Chapter Strategy',
        value: blueprint['chapter_strategy']?.toString(),
      ),
      ..._buildTextBlock(
        label: 'Ending Direction',
        value: blueprint['ending_direction']?.toString(),
      ),
    ];
    final chapterBlueprints =
        (blueprint['chapter_blueprints'] as List? ?? const [])
            .whereType<Map>()
            .map((item) => Map<String, dynamic>.from(item))
            .toList();
    if (chapterBlueprints.isNotEmpty) {
      widgets.add(SizedBox(height: spacing.sm));
      widgets.add(Text('章节蓝图', style: Theme.of(context).textTheme.titleSmall));
      widgets.add(SizedBox(height: spacing.sm));
      widgets.addAll(
        chapterBlueprints.map(
          (entry) => Padding(
            padding: EdgeInsets.only(bottom: spacing.sm),
            child: Text(
              '• ${entry['title'] ?? entry['chapter_id'] ?? '章节'}'
              '${(entry['purpose']?.toString().isNotEmpty ?? false) ? '：${entry['purpose']}' : ''}',
            ),
          ),
        ),
      );
    }
    return widgets.isEmpty ? const [Text('剧情设计尚为空。')] : widgets;
  }

  List<Widget> _buildWritingContractWidgets(RpSetupWorkspace workspace) {
    final contract = workspace.writingContractDraft;
    if (contract == null) {
      return const [Text('还没有作家配置。')];
    }
    return [
      _buildTagBlock('POV Rules', contract['pov_rules']),
      _buildTagBlock('Style Rules', contract['style_rules']),
      _buildTagBlock('Writing Constraints', contract['writing_constraints']),
      _buildTagBlock('Task Writing Rules', contract['task_writing_rules']),
    ];
  }

  List<Widget> _buildStoryConfigWidgets(RpSetupWorkspace workspace) {
    final config = workspace.storyConfigDraft;
    if (config == null) {
      return const [Text('还没有 worker 配置。')];
    }
    return [
      ..._buildTextBlock(
        label: 'Model Profile',
        value: config['model_profile_ref']?.toString(),
      ),
      ..._buildTextBlock(
        label: 'Worker Profile',
        value: config['worker_profile_ref']?.toString(),
      ),
      ..._buildTextBlock(
        label: 'Post Write Preset',
        value: config['post_write_policy_preset']?.toString(),
      ),
      ..._buildTextBlock(
        label: 'Retrieval Embedding',
        value: _formatRetrievalSelectionSummary(
          providerId: config['retrieval_embedding_provider_id']?.toString(),
          modelId: config['retrieval_embedding_model_id']?.toString(),
        ),
      ),
      ..._buildTextBlock(
        label: 'Retrieval Rerank',
        value: _formatRetrievalSelectionSummary(
          providerId: config['retrieval_rerank_provider_id']?.toString(),
          modelId: config['retrieval_rerank_model_id']?.toString(),
        ),
      ),
      ..._buildTextBlock(
        label: 'Graph Extraction',
        value: _formatRetrievalSelectionSummary(
          providerId: config['graph_extraction_provider_id']?.toString(),
          modelId: config['graph_extraction_model_id']?.toString(),
        ),
      ),
      ..._buildTextBlock(label: 'Notes', value: config['notes']?.toString()),
    ];
  }

  List<Widget> _buildOverviewWidgets(RpSetupWorkspace workspace) {
    final spacing = context.owuiSpacing;
    return [
      Text('Story: ${workspace.storyId}'),
      Text('Mode: ${workspace.mode}'),
      Text('Workspace State: ${workspace.workspaceState}'),
      Text('Current Stage: ${workspace.currentStage ?? 'n/a'}'),
      Text('Current Step: ${workspace.currentStep}'),
      Text('Version: ${workspace.version}'),
      if (workspace.activatedStorySessionId != null)
        Text('Active Session: ${workspace.activatedStorySessionId}'),
      SizedBox(height: spacing.md),
      Wrap(
        spacing: spacing.sm,
        runSpacing: spacing.sm,
        children: workspace.stepStates
            .map((step) => Chip(label: Text('${step.stepId} · ${step.state}')))
            .toList(),
      ),
      if (workspace.stageStates.isNotEmpty) ...[
        SizedBox(height: spacing.md),
        Wrap(
          spacing: spacing.sm,
          runSpacing: spacing.sm,
          children: workspace.stageStates
              .map(
                (stage) => Chip(
                  label: Text('${stage.stageId} · ${stage.state}'),
                  visualDensity: VisualDensity.compact,
                ),
              )
              .toList(),
        ),
      ],
      if (workspace.stagePlan.isNotEmpty) ...[
        SizedBox(height: spacing.md),
        Text(
          'Stage Plan: ${workspace.stagePlan.map(_stageDisplayLabel).join(' → ')}',
          style: Theme.of(context).textTheme.bodySmall,
        ),
      ],
      SizedBox(height: spacing.md),
      Text('Accepted Commits', style: Theme.of(context).textTheme.titleSmall),
      SizedBox(height: spacing.sm),
      if (workspace.acceptedCommits.isEmpty)
        const Text('当前还没有 accepted commit。')
      else
        ...workspace.acceptedCommits.map(
          (commit) => Padding(
            padding: EdgeInsets.only(bottom: spacing.xs),
            child: Text(
              '• ${commit.stepId} · ${commit.summaryTier1 ?? commit.summaryTier0 ?? commit.commitId}',
            ),
          ),
        ),
    ];
  }

  Widget _buildRetrievalMaintenancePanel(RpSetupWorkspace workspace) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    final snapshot = _retrievalMaintenance?.storyId == workspace.storyId
        ? _retrievalMaintenance
        : null;

    return OwuiCard(
      padding: EdgeInsets.all(spacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Retrieval Maintenance',
                      style: Theme.of(context).textTheme.titleSmall,
                    ),
                    SizedBox(height: spacing.xs),
                    Text(
                      '基于 story 维度查看 collection / chunk / embedding / failed job 状态，并触发 reindex、backfill、retry。',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: colors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              IconButton(
                tooltip: '刷新 maintenance snapshot',
                onPressed:
                    _isLoadingRetrievalMaintenance ||
                        _isRunningRetrievalMaintenanceAction
                    ? null
                    : () => _refreshCurrentRetrievalMaintenance(),
                icon: _isLoadingRetrievalMaintenance
                    ? SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.refresh),
              ),
            ],
          ),
          SizedBox(height: spacing.md),
          if (_retrievalMaintenanceActionLabel != null) ...[
            Text(
              '执行中: $_retrievalMaintenanceActionLabel',
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
            ),
            SizedBox(height: spacing.sm),
          ],
          if (snapshot == null && _retrievalMaintenanceError != null)
            Text(
              '加载失败: $_retrievalMaintenanceError',
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            )
          else if (snapshot == null)
            Text(
              '暂无 maintenance snapshot。',
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
            )
          else ...[
            Wrap(
              spacing: spacing.sm,
              runSpacing: spacing.sm,
              children: [
                _buildMetricChip('Collections', snapshot.collectionCount),
                _buildMetricChip('Assets', snapshot.assetCount),
                _buildMetricChip('Chunks', snapshot.activeChunkCount),
                _buildMetricChip('Embeddings', snapshot.activeEmbeddingCount),
                _buildMetricChip(
                  'Backfill',
                  snapshot.backfillCandidateAssetIds.length,
                ),
                _buildMetricChip('Failed', snapshot.failedJobCount),
                _buildMetricChip('Retryable', snapshot.retryableJobIds.length),
              ],
            ),
            SizedBox(height: spacing.md),
            Wrap(
              spacing: spacing.sm,
              runSpacing: spacing.sm,
              children: [
                OutlinedButton.icon(
                  onPressed: _isRunningRetrievalMaintenanceAction
                      ? null
                      : _reindexRetrievalStory,
                  icon: const Icon(Icons.replay_circle_filled_outlined),
                  label: const Text('Story Reindex'),
                ),
                OutlinedButton.icon(
                  onPressed: _isRunningRetrievalMaintenanceAction
                      ? null
                      : _backfillRetrievalStory,
                  icon: const Icon(Icons.data_object_outlined),
                  label: const Text('Story Backfill'),
                ),
                FilledButton.icon(
                  onPressed: _isRunningRetrievalMaintenanceAction
                      ? null
                      : _retryFailedRetrievalStoryJobs,
                  icon: const Icon(Icons.restart_alt),
                  label: const Text('Retry Failed'),
                ),
              ],
            ),
            if (snapshot.backfillCandidateAssetIds.isNotEmpty) ...[
              SizedBox(height: spacing.md),
              Text(
                'Backfill Candidates',
                style: Theme.of(context).textTheme.titleSmall,
              ),
              SizedBox(height: spacing.xs),
              _buildStringChipWrap(
                snapshot.backfillCandidateAssetIds,
                emptyLabel: '暂无 backfill candidate',
              ),
            ],
            SizedBox(height: spacing.md),
            Text('Collections', style: Theme.of(context).textTheme.titleSmall),
            SizedBox(height: spacing.sm),
            if (snapshot.collections.isEmpty)
              Text(
                '当前 story 还没有 retrieval collection。',
                style: Theme.of(
                  context,
                ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
              )
            else
              ...snapshot.collections.map(_buildRetrievalCollectionCard),
            SizedBox(height: spacing.md),
            Text('Recent Jobs', style: Theme.of(context).textTheme.titleSmall),
            SizedBox(height: spacing.sm),
            if (snapshot.recentJobs.isEmpty)
              Text(
                '暂无 recent jobs。',
                style: Theme.of(
                  context,
                ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
              )
            else
              ...snapshot.recentJobs.map(_buildRetrievalJobCard),
          ],
          SizedBox(height: spacing.lg),
          _buildMemoryGraphInspectionSection(workspace),
        ],
      ),
    );
  }

  Widget _buildMemoryGraphInspectionSection(RpSetupWorkspace workspace) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    final maintenance = _memoryGraphMaintenance?.storyId == workspace.storyId
        ? _memoryGraphMaintenance
        : null;
    final neighborhood = _memoryGraphNeighborhood?.storyId == workspace.storyId
        ? _memoryGraphNeighborhood
        : null;

    return Container(
      padding: EdgeInsets.all(spacing.md),
      decoration: BoxDecoration(
        color: colors.surface2,
        borderRadius: BorderRadius.circular(context.owuiRadius.rXl),
        border: Border.all(color: colors.borderSubtle),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Memory Graph Inspection',
                      style: Theme.of(context).textTheme.titleSmall,
                    ),
                    SizedBox(height: spacing.xs),
                    Text(
                      '只读验证视图：查看 graph health、配置、job 状态，并按 bounded neighborhood 展示节点、边和 evidence。',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: colors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              IconButton(
                tooltip: '刷新 graph maintenance',
                onPressed: _isLoadingMemoryGraphMaintenance
                    ? null
                    : () => _refreshMemoryGraphMaintenance(workspace.storyId),
                icon: _isLoadingMemoryGraphMaintenance
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.refresh),
              ),
            ],
          ),
          if (_isLoadingMemoryGraphMaintenance ||
              _isLoadingMemoryGraphNeighborhood) ...[
            SizedBox(height: spacing.md),
            const LinearProgressIndicator(minHeight: 2),
          ],
          SizedBox(height: spacing.md),
          if (_memoryGraphMaintenanceError != null && maintenance == null)
            Text(
              'Graph maintenance 加载失败: $_memoryGraphMaintenanceError',
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            )
          else if (maintenance == null)
            Text(
              '暂无 graph maintenance snapshot。',
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
            )
          else ...[
            Wrap(
              spacing: spacing.sm,
              runSpacing: spacing.sm,
              children: [
                Chip(
                  label: Text(
                    maintenance.graphExtractionEnabled ? 'Enabled' : 'Disabled',
                  ),
                  visualDensity: VisualDensity.compact,
                ),
                Chip(
                  label: Text(
                    maintenance.graphExtractionConfigured
                        ? 'Configured'
                        : 'Config Missing',
                  ),
                  visualDensity: VisualDensity.compact,
                ),
                _buildMetricChip('Nodes', maintenance.nodeCount),
                _buildMetricChip('Edges', maintenance.edgeCount),
                _buildMetricChip('Evidence', maintenance.evidenceCount),
                _buildMetricChip('Jobs', maintenance.jobCount),
                _buildMetricChip('Failed', maintenance.failedJobCount),
                _buildMetricChip(
                  'Retryable',
                  maintenance.retryableJobIds.length,
                ),
              ],
            ),
            SizedBox(height: spacing.sm),
            Text(
              'Backend: ${maintenance.graphBackend} · Model: ${_formatRetrievalSelectionSummary(providerId: maintenance.graphExtractionProviderId, modelId: maintenance.graphExtractionModelId) ?? '未设置'}',
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
            ),
            if (maintenance.sourceLayers.isNotEmpty) ...[
              SizedBox(height: spacing.sm),
              _buildStringChipWrap(
                maintenance.sourceLayers,
                emptyLabel: '暂无 source layer',
              ),
            ],
            if (maintenance.maintenanceWarnings.isNotEmpty) ...[
              SizedBox(height: spacing.sm),
              Text(
                'Warnings: ${maintenance.maintenanceWarnings.join(' | ')}',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: Theme.of(context).colorScheme.error,
                ),
              ),
            ],
            if (maintenance.errorCodeCounts.isNotEmpty ||
                maintenance.warningCodeCounts.isNotEmpty) ...[
              SizedBox(height: spacing.sm),
              Text(
                'Issue counts: ${_formatCountMap(maintenance.errorCodeCounts)} ${_formatCountMap(maintenance.warningCodeCounts)}',
                style: Theme.of(
                  context,
                ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
              ),
            ],
            if (maintenance.recentJobs.isNotEmpty) ...[
              SizedBox(height: spacing.md),
              Text('Graph Jobs', style: Theme.of(context).textTheme.titleSmall),
              SizedBox(height: spacing.xs),
              ...maintenance.recentJobs.take(3).map(_buildMemoryGraphJobRow),
            ],
          ],
          SizedBox(height: spacing.md),
          Wrap(
            spacing: spacing.sm,
            runSpacing: spacing.sm,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              OutlinedButton.icon(
                onPressed: _isLoadingMemoryGraphNeighborhood
                    ? null
                    : () => _refreshMemoryGraphNeighborhood(),
                icon: const Icon(Icons.account_tree_outlined),
                label: const Text('刷新 bounded neighborhood'),
              ),
              if (_selectedMemoryGraphNodeId != null)
                OutlinedButton.icon(
                  onPressed: _isLoadingMemoryGraphNeighborhood
                      ? null
                      : () => _refreshMemoryGraphNeighborhood(
                          nodeId: _selectedMemoryGraphNodeId,
                        ),
                  icon: const Icon(Icons.hub_outlined),
                  label: const Text('按选中节点刷新'),
                ),
              Chip(
                label: const Text('max_depth 1 · max_nodes 30 · max_edges 50'),
                visualDensity: VisualDensity.compact,
              ),
            ],
          ),
          if (_memoryGraphNeighborhoodError != null) ...[
            SizedBox(height: spacing.sm),
            Text(
              'Neighborhood 加载失败: $_memoryGraphNeighborhoodError',
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ],
          SizedBox(height: spacing.md),
          _buildMemoryGraphNeighborhoodView(neighborhood),
        ],
      ),
    );
  }

  Widget _buildMemoryGraphJobRow(RpMemoryGraphExtractionJob job) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    final scheme = Theme.of(context).colorScheme;
    final stateColor = job.isFailed
        ? scheme.error
        : (job.isCompleted ? scheme.secondary : scheme.tertiary);
    return Padding(
      padding: EdgeInsets.only(bottom: spacing.xs),
      child: Row(
        children: [
          Expanded(
            child: Text(
              '${job.sourceLayer} · ${job.sourceAssetId ?? job.chunkId ?? job.graphJobId}',
              overflow: TextOverflow.ellipsis,
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
            ),
          ),
          SizedBox(width: spacing.sm),
          Chip(
            label: Text(job.status),
            backgroundColor: stateColor.withValues(alpha: 0.12),
            side: BorderSide(color: stateColor.withValues(alpha: 0.28)),
            visualDensity: VisualDensity.compact,
          ),
        ],
      ),
    );
  }

  Widget _buildMemoryGraphNeighborhoodView(
    RpMemoryGraphNeighborhoodResponse? neighborhood,
  ) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    if (neighborhood == null) {
      return Text(
        '点击刷新后加载 bounded neighborhood；不会浏览全图，也不会触发 generation 或 mutation。',
        style: Theme.of(
          context,
        ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
      );
    }

    final selectedNode = _findMemoryGraphNode(
      neighborhood,
      _selectedMemoryGraphNodeId,
    );
    final selectedEdge = _findMemoryGraphEdge(
      neighborhood,
      _selectedMemoryGraphEdgeId,
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: spacing.sm,
          runSpacing: spacing.sm,
          children: [
            _buildMetricChip('Nodes', neighborhood.nodes.length),
            _buildMetricChip('Edges', neighborhood.edges.length),
            _buildMetricChip('Evidence', neighborhood.evidence.length),
            if (neighborhood.truncated)
              const Chip(
                label: Text('Truncated'),
                visualDensity: VisualDensity.compact,
              ),
          ],
        ),
        if (neighborhood.warnings.isNotEmpty) ...[
          SizedBox(height: spacing.sm),
          Text(
            'Warnings: ${neighborhood.warnings.join(' | ')}',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: Theme.of(context).colorScheme.error,
            ),
          ),
        ],
        SizedBox(height: spacing.md),
        Text('Nodes', style: Theme.of(context).textTheme.titleSmall),
        SizedBox(height: spacing.xs),
        if (neighborhood.nodes.isEmpty)
          Text(
            '暂无 graph nodes。',
            style: Theme.of(
              context,
            ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
          )
        else
          Wrap(
            spacing: spacing.sm,
            runSpacing: spacing.sm,
            children: neighborhood.nodes
                .map(
                  (node) => ChoiceChip(
                    label: Text('${node.label} · ${node.type}'),
                    selected: node.id == _selectedMemoryGraphNodeId,
                    onSelected: (_) {
                      setState(() {
                        _selectedMemoryGraphNodeId = node.id;
                        _selectedMemoryGraphEdgeId = null;
                      });
                    },
                  ),
                )
                .toList(),
          ),
        SizedBox(height: spacing.md),
        Text('Edges', style: Theme.of(context).textTheme.titleSmall),
        SizedBox(height: spacing.xs),
        if (neighborhood.edges.isEmpty)
          Text(
            '暂无 graph edges。',
            style: Theme.of(
              context,
            ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
          )
        else
          ...neighborhood.edges.map(_buildMemoryGraphEdgeTile),
        SizedBox(height: spacing.md),
        _buildMemoryGraphDetailsPanel(
          neighborhood: neighborhood,
          selectedNode: selectedNode,
          selectedEdge: selectedEdge,
        ),
      ],
    );
  }

  Widget _buildMemoryGraphEdgeTile(RpMemoryGraphEdge edge) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    final scheme = Theme.of(context).colorScheme;
    final selected = edge.id == _selectedMemoryGraphEdgeId;
    return Padding(
      padding: EdgeInsets.only(bottom: spacing.xs),
      child: InkWell(
        borderRadius: BorderRadius.circular(context.owuiRadius.rLg),
        onTap: () {
          setState(() {
            _selectedMemoryGraphEdgeId = edge.id;
            _selectedMemoryGraphNodeId = null;
          });
        },
        child: Container(
          padding: EdgeInsets.all(spacing.sm),
          decoration: BoxDecoration(
            color: selected
                ? scheme.primaryContainer.withValues(alpha: 0.24)
                : colors.surfaceCard,
            borderRadius: BorderRadius.circular(context.owuiRadius.rLg),
            border: Border.all(color: colors.borderSubtle),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '${edge.sourceEntityName ?? edge.source} --${edge.label}--> ${edge.targetEntityName ?? edge.target}',
                style: Theme.of(context).textTheme.bodyMedium,
              ),
              SizedBox(height: spacing.xs),
              Text(
                'Evidence ${edge.evidenceCount} · ${edge.sourceStatus} · ${_formatConfidence(edge.confidence)}',
                style: Theme.of(
                  context,
                ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildMemoryGraphDetailsPanel({
    required RpMemoryGraphNeighborhoodResponse neighborhood,
    required RpMemoryGraphNode? selectedNode,
    required RpMemoryGraphEdge? selectedEdge,
  }) {
    final colors = context.owuiColors;
    if (selectedEdge != null) {
      final evidence = neighborhood.evidenceForEdge(selectedEdge.id);
      return _buildMemoryGraphDetailBox(
        title: 'Edge Details',
        lines: [
          '${selectedEdge.sourceEntityName ?? selectedEdge.source} -> ${selectedEdge.targetEntityName ?? selectedEdge.target}',
          'Relation: ${selectedEdge.label} · ${selectedEdge.relationFamily}',
          'Raw: ${selectedEdge.rawRelationText ?? 'n/a'}',
          'Canon: ${selectedEdge.canonStatus} · Source: ${selectedEdge.sourceLayer}/${selectedEdge.sourceStatus}',
          'Metadata: ${_formatMapPreview(selectedEdge.metadata)}',
        ],
        evidence: evidence,
      );
    }

    if (selectedNode != null) {
      final evidence = neighborhood.evidenceForNode(selectedNode.id);
      final connectedEdges = neighborhood.edges
          .where(
            (edge) =>
                edge.source == selectedNode.id ||
                edge.target == selectedNode.id,
          )
          .map((edge) => edge.label)
          .toList();
      return _buildMemoryGraphDetailBox(
        title: 'Node Details',
        lines: [
          '${selectedNode.label} · ${selectedNode.type}',
          'Aliases: ${selectedNode.aliases.isEmpty ? 'n/a' : selectedNode.aliases.join(', ')}',
          'Source: ${selectedNode.sourceLayer}/${selectedNode.sourceStatus} · ${_formatConfidence(selectedNode.confidence)}',
          if (selectedNode.description != null)
            'Description: ${selectedNode.description}',
          'Connected: ${connectedEdges.isEmpty ? 'n/a' : connectedEdges.join(', ')}',
          'Metadata: ${_formatMapPreview(selectedNode.metadata)}',
        ],
        evidence: evidence,
      );
    }

    return Text(
      '选择 node 或 edge 后在这里查看 evidence 与 metadata。',
      style: Theme.of(
        context,
      ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
    );
  }

  Widget _buildMemoryGraphDetailBox({
    required String title,
    required List<String> lines,
    required List<RpMemoryGraphEvidence> evidence,
  }) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(spacing.md),
      decoration: BoxDecoration(
        color: colors.surfaceCard,
        borderRadius: BorderRadius.circular(context.owuiRadius.rLg),
        border: Border.all(color: colors.borderSubtle),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleSmall),
          SizedBox(height: spacing.sm),
          ...lines
              .where((line) => line.trim().isNotEmpty)
              .map(
                (line) => Padding(
                  padding: EdgeInsets.only(bottom: spacing.xs),
                  child: Text(
                    line,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: colors.textSecondary,
                    ),
                  ),
                ),
              ),
          SizedBox(height: spacing.sm),
          Text('Evidence', style: Theme.of(context).textTheme.titleSmall),
          SizedBox(height: spacing.xs),
          if (evidence.isEmpty)
            Text(
              '暂无 evidence。',
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
            )
          else
            ...evidence.map(_buildMemoryGraphEvidenceRow),
        ],
      ),
    );
  }

  Widget _buildMemoryGraphEvidenceRow(RpMemoryGraphEvidence evidence) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    return Padding(
      padding: EdgeInsets.only(bottom: spacing.sm),
      child: Container(
        width: double.infinity,
        padding: EdgeInsets.all(spacing.sm),
        decoration: BoxDecoration(
          color: colors.surface2,
          borderRadius: BorderRadius.circular(context.owuiRadius.rLg),
          border: Border.all(color: colors.borderSubtle),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              evidence.excerpt?.trim().isNotEmpty == true
                  ? evidence.excerpt!
                  : '无 excerpt',
            ),
            SizedBox(height: spacing.xs),
            Text(
              [
                    evidence.sourceRef,
                    evidence.sourceType,
                    evidence.chunkId,
                    evidence.sectionId,
                  ]
                  .whereType<String>()
                  .where((item) => item.isNotEmpty)
                  .join(' · '),
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildRetrievalCollectionCard(
    RpRetrievalCollectionMaintenanceSnapshot snapshot,
  ) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    return OwuiCard(
      margin: EdgeInsets.only(bottom: spacing.sm),
      padding: EdgeInsets.all(spacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '${snapshot.collectionKind} · ${_truncateMiddle(snapshot.collectionId)}',
            style: Theme.of(context).textTheme.titleSmall,
          ),
          SizedBox(height: spacing.xs),
          Wrap(
            spacing: spacing.sm,
            runSpacing: spacing.sm,
            children: [
              _buildMetricChip('Assets', snapshot.assetCount),
              _buildMetricChip('Chunks', snapshot.activeChunkCount),
              _buildMetricChip('Embeddings', snapshot.activeEmbeddingCount),
              _buildMetricChip(
                'Backfill',
                snapshot.backfillCandidateAssetIds.length,
              ),
              _buildMetricChip('Failed', snapshot.failedJobCount),
            ],
          ),
          SizedBox(height: spacing.md),
          Wrap(
            spacing: spacing.sm,
            runSpacing: spacing.sm,
            children: [
              OutlinedButton.icon(
                onPressed: _isRunningRetrievalMaintenanceAction
                    ? null
                    : () => _reindexRetrievalCollection(snapshot),
                icon: const Icon(Icons.replay_outlined),
                label: const Text('Reindex'),
              ),
              OutlinedButton.icon(
                onPressed: _isRunningRetrievalMaintenanceAction
                    ? null
                    : () => _backfillRetrievalCollection(snapshot),
                icon: const Icon(Icons.dataset_linked_outlined),
                label: const Text('Backfill'),
              ),
              FilledButton.icon(
                onPressed: _isRunningRetrievalMaintenanceAction
                    ? null
                    : () => _retryFailedRetrievalCollectionJobs(snapshot),
                icon: const Icon(Icons.restart_alt),
                label: const Text('Retry Failed'),
              ),
            ],
          ),
          SizedBox(height: spacing.md),
          Text(
            'Asset IDs',
            style: Theme.of(
              context,
            ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
          ),
          SizedBox(height: spacing.xs),
          _buildStringChipWrap(
            snapshot.assetIds,
            emptyLabel: '暂无资产',
            maxItems: 8,
          ),
          if (snapshot.backfillCandidateAssetIds.isNotEmpty) ...[
            SizedBox(height: spacing.sm),
            Text(
              'Backfill Candidates',
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
            ),
            SizedBox(height: spacing.xs),
            _buildStringChipWrap(
              snapshot.backfillCandidateAssetIds,
              emptyLabel: '暂无 backfill candidate',
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildRetrievalJobCard(RpRetrievalIndexJob job) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    final scheme = Theme.of(context).colorScheme;
    final stateColor = job.isFailed
        ? scheme.error
        : (job.isCompleted ? scheme.secondary : scheme.tertiary);
    return OwuiCard(
      margin: EdgeInsets.only(bottom: spacing.sm),
      padding: EdgeInsets.all(spacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  '${job.jobKind} · ${job.assetId ?? job.collectionId ?? job.storyId}',
                  style: Theme.of(context).textTheme.titleSmall,
                ),
              ),
              Chip(
                label: Text(job.jobState),
                backgroundColor: stateColor.withValues(alpha: 0.12),
                side: BorderSide(color: stateColor.withValues(alpha: 0.28)),
                visualDensity: VisualDensity.compact,
              ),
            ],
          ),
          SizedBox(height: spacing.xs),
          Text(
            'Job: ${_truncateMiddle(job.jobId)} · Updated: ${_formatDateTime(job.updatedAt)}',
            style: Theme.of(
              context,
            ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
          ),
          if (job.errorMessage != null &&
              job.errorMessage!.trim().isNotEmpty) ...[
            SizedBox(height: spacing.sm),
            Text(job.errorMessage!, style: TextStyle(color: scheme.error)),
          ],
          if (job.warnings.isNotEmpty) ...[
            SizedBox(height: spacing.sm),
            Text(
              'Warnings: ${job.warnings.take(3).join(' | ')}',
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
            ),
          ],
          if (job.isFailed) ...[
            SizedBox(height: spacing.sm),
            OutlinedButton.icon(
              onPressed: _isRunningRetrievalMaintenanceAction
                  ? null
                  : () => _retryRetrievalJob(job),
              icon: const Icon(Icons.restart_alt),
              label: const Text('Retry This Job'),
            ),
          ],
        ],
      ),
    );
  }

  RpMemoryGraphNode? _findMemoryGraphNode(
    RpMemoryGraphNeighborhoodResponse neighborhood,
    String? nodeId,
  ) {
    if (nodeId == null) return null;
    for (final node in neighborhood.nodes) {
      if (node.id == nodeId) return node;
    }
    return null;
  }

  RpMemoryGraphEdge? _findMemoryGraphEdge(
    RpMemoryGraphNeighborhoodResponse neighborhood,
    String? edgeId,
  ) {
    if (edgeId == null) return null;
    for (final edge in neighborhood.edges) {
      if (edge.id == edgeId) return edge;
    }
    return null;
  }

  Widget _buildMetricChip(String label, int value) {
    return Chip(
      label: Text('$label $value'),
      visualDensity: VisualDensity.compact,
    );
  }

  Widget _buildStringChipWrap(
    List<String> values, {
    required String emptyLabel,
    int maxItems = 6,
  }) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    if (values.isEmpty) {
      return Text(
        emptyLabel,
        style: Theme.of(
          context,
        ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
      );
    }

    final visible = values.take(maxItems).toList();
    final overflow = values.length - visible.length;
    return Wrap(
      spacing: spacing.sm,
      runSpacing: spacing.sm,
      children: [
        ...visible.map((item) => Chip(label: Text(_truncateMiddle(item)))),
        if (overflow > 0) Chip(label: Text('+$overflow')),
      ],
    );
  }

  List<Widget> _buildRetrievalOverviewWidgets(RpSetupWorkspace workspace) {
    final spacing = context.owuiSpacing;
    if (workspace.retrievalIngestionJobs.isEmpty) {
      return const [Text('当前还没有 ingestion job。')];
    }
    return workspace.retrievalIngestionJobs
        .map(
          (job) => Padding(
            padding: EdgeInsets.only(bottom: spacing.xs),
            child: Text('${job.targetType} · ${job.targetRef} · ${job.state}'),
          ),
        )
        .toList();
  }

  String _truncateMiddle(String value, {int head = 10, int tail = 8}) {
    if (value.length <= head + tail + 3) return value;
    return '${value.substring(0, head)}...${value.substring(value.length - tail)}';
  }

  String _formatCountMap(Map<String, int> values) {
    if (values.isEmpty) return '';
    return values.entries
        .map((entry) => '${entry.key}:${entry.value}')
        .join(' ');
  }

  String _formatConfidence(double? value) {
    if (value == null) return 'confidence n/a';
    return 'confidence ${value.toStringAsFixed(2)}';
  }

  String _formatMapPreview(Map<String, dynamic> value) {
    if (value.isEmpty) return '{}';
    return value.entries
        .take(4)
        .map((entry) => '${entry.key}=${entry.value}')
        .join(', ');
  }

  String? _formatAgentSelectionSummary({
    required String? providerId,
    required String? modelId,
  }) {
    if ((providerId == null || providerId.isEmpty) &&
        (modelId == null || modelId.isEmpty)) {
      return null;
    }
    final providerName = providerId == null
        ? null
        : globalModelServiceManager.getProvider(providerId)?.name ?? providerId;
    final modelName = modelId == null
        ? null
        : globalModelServiceManager.getModel(modelId)?.displayName ?? modelId;
    if (providerName != null && modelName != null) {
      return '$providerName · $modelName';
    }
    return modelName ?? providerName;
  }

  String? _formatRetrievalSelectionSummary({
    required String? providerId,
    required String? modelId,
  }) {
    if ((providerId == null || providerId.isEmpty) &&
        (modelId == null || modelId.isEmpty)) {
      return null;
    }
    final providerName = providerId == null
        ? null
        : globalModelServiceManager.getProvider(providerId)?.name ?? providerId;
    final modelName = modelId == null
        ? null
        : globalModelServiceManager.getModel(modelId)?.displayName ?? modelId;
    if (providerName != null && modelName != null) {
      return '$providerName · $modelName';
    }
    return modelName ?? providerName;
  }

  String _formatDateTime(DateTime? value) {
    if (value == null) return 'n/a';
    final local = value.toLocal();
    final month = local.month.toString().padLeft(2, '0');
    final day = local.day.toString().padLeft(2, '0');
    final hour = local.hour.toString().padLeft(2, '0');
    final minute = local.minute.toString().padLeft(2, '0');
    return '${local.year}-$month-$day $hour:$minute';
  }

  List<Widget> _buildTextBlock({
    required String label,
    required String? value,
  }) {
    final spacing = context.owuiSpacing;
    if (value == null || value.trim().isEmpty) return const [];
    return [
      Text(label, style: Theme.of(context).textTheme.titleSmall),
      SizedBox(height: spacing.xs),
      Text(value),
      SizedBox(height: spacing.md),
    ];
  }

  Widget _buildTagBlock(String label, dynamic rawValue) {
    final spacing = context.owuiSpacing;
    final values = (rawValue as List? ?? const [])
        .map((item) => item.toString())
        .where((item) => item.trim().isNotEmpty)
        .toList();
    return Padding(
      padding: EdgeInsets.only(bottom: spacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: Theme.of(context).textTheme.titleSmall),
          SizedBox(height: spacing.xs),
          if (values.isEmpty)
            Text(
              '暂无内容',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: context.owuiColors.textSecondary,
              ),
            )
          else
            Wrap(
              spacing: spacing.sm,
              runSpacing: spacing.sm,
              children: values.map((item) => Chip(label: Text(item))).toList(),
            ),
        ],
      ),
    );
  }

  List<String> _stagePlanFor(RpSetupWorkspace workspace) {
    if (workspace.stagePlan.isNotEmpty) {
      return workspace.stagePlan;
    }
    return _legacyStagePlan();
  }

  String? _workspaceCurrentStageId(RpSetupWorkspace workspace) {
    return workspace.currentStage ?? _stageIdFor(_selectedStage);
  }

  String _currentStageLabel(RpSetupWorkspace workspace) {
    final stageId = _workspaceCurrentStageId(workspace);
    if (stageId == null) {
      return _selectedStage.label;
    }
    return _stageDisplayLabel(stageId);
  }

  String _stagePromptHintForWorkspace(RpSetupWorkspace workspace) {
    final stageId = _stageIdFor(_selectedStage);
    return _stageMetaFor(stageId).promptHint;
  }

  String _stageDisplayLabel(String stageId) {
    return _stageMetaFor(stageId).title;
  }

  String _stageStateLabel(RpSetupWorkspace workspace, String stageId) {
    final state = _stageStateFor(workspace, stageId);
    if (state != null) {
      switch (state.state) {
        case 'discussing':
          return '讨论中';
        case 'review_pending':
          return '待 Review';
        case 'ready_for_commit':
          return '待 Commit';
        case 'frozen':
          return '已冻结';
        default:
          return state.state;
      }
    }

    final block = _stageBlockFor(workspace, stageId);
    if (block != null && block.entries.isNotEmpty) {
      return '已填写';
    }
    if (stageId == 'overview') {
      return '待收敛';
    }
    if (stageId == 'activate') {
      return (_lastActivationCheck?.ready ?? false) ||
              workspace.workspaceState == 'ready_to_activate' ||
              workspace.workspaceState == 'activated'
          ? '可激活'
          : '未就绪';
    }
    return '待补充';
  }

  RpSetupStageState? _stageStateFor(
    RpSetupWorkspace workspace,
    String stageId,
  ) {
    for (final state in workspace.stageStates) {
      if (state.stageId == stageId) {
        return state;
      }
    }
    return null;
  }

  RpSetupStageDraftBlock? _stageBlockFor(
    RpSetupWorkspace workspace,
    String stageId,
  ) {
    final block = workspace.stageBlock(stageId);
    if (block != null) {
      return block;
    }
    return _legacyStageBlockFor(workspace, stageId);
  }

  RpSetupStageDraftBlock? _legacyStageBlockFor(
    RpSetupWorkspace workspace,
    String stageId,
  ) {
    switch (stageId) {
      case 'world_background':
        final entries = _worldFoundationEntries(
          workspace,
        ).map(_legacyFoundationEntryToDraftEntry).toList();
        if (entries.isEmpty) return null;
        return RpSetupStageDraftBlock(
          stageId: stageId,
          entries: entries,
          notes: null,
        );
      case 'character_design':
        final entries = _characterFoundationEntries(
          workspace,
        ).map(_legacyFoundationEntryToDraftEntry).toList();
        if (entries.isEmpty) return null;
        return RpSetupStageDraftBlock(
          stageId: stageId,
          entries: entries,
          notes: null,
        );
      case 'plot_blueprint':
        final blueprint = workspace.longformBlueprintDraft;
        if (blueprint == null) return null;
        return RpSetupStageDraftBlock(
          stageId: stageId,
          entries: [
            RpSetupDraftEntry(
              entryId: 'longform_blueprint',
              entryType: 'plot_blueprint',
              semanticPath: 'plot_blueprint',
              title: '伏笔 / 剧情设计',
              displayLabel: 'longform_blueprint',
              summary: blueprint['premise']?.toString(),
              aliases: const [],
              tags: const ['legacy'],
              sections: [
                RpSetupDraftSection(
                  sectionId: 'premise',
                  title: 'Premise',
                  kind: 'text',
                  content: {'text': blueprint['premise']?.toString() ?? ''},
                  retrievalRole: 'summary',
                  tags: const ['legacy'],
                ),
                RpSetupDraftSection(
                  sectionId: 'conflict',
                  title: 'Central Conflict',
                  kind: 'text',
                  content: {
                    'text': blueprint['central_conflict']?.toString() ?? '',
                  },
                  retrievalRole: 'detail',
                  tags: const ['legacy'],
                ),
                RpSetupDraftSection(
                  sectionId: 'chapter_strategy',
                  title: 'Chapter Strategy',
                  kind: 'text',
                  content: {
                    'text': blueprint['chapter_strategy']?.toString() ?? '',
                  },
                  retrievalRole: 'detail',
                  tags: const ['legacy'],
                ),
              ],
            ),
          ],
          notes: blueprint['notes']?.toString(),
        );
      case 'writer_config':
        final contract = workspace.writingContractDraft;
        if (contract == null) return null;
        return RpSetupStageDraftBlock(
          stageId: stageId,
          entries: [
            RpSetupDraftEntry(
              entryId: 'writing_contract',
              entryType: 'writer_config',
              semanticPath: 'writer_config',
              title: '作家配置',
              displayLabel: 'writing_contract',
              summary: _legacyListSummary(contract['style_rules']),
              aliases: const [],
              tags: const ['legacy'],
              sections: [
                RpSetupDraftSection(
                  sectionId: 'pov_rules',
                  title: 'POV Rules',
                  kind: 'list',
                  content: {'items': contract['pov_rules'] ?? const []},
                  retrievalRole: 'rule',
                  tags: const ['legacy'],
                ),
                RpSetupDraftSection(
                  sectionId: 'style_rules',
                  title: 'Style Rules',
                  kind: 'list',
                  content: {'items': contract['style_rules'] ?? const []},
                  retrievalRole: 'rule',
                  tags: const ['legacy'],
                ),
                RpSetupDraftSection(
                  sectionId: 'writing_constraints',
                  title: 'Writing Constraints',
                  kind: 'list',
                  content: {
                    'items': contract['writing_constraints'] ?? const [],
                  },
                  retrievalRole: 'rule',
                  tags: const ['legacy'],
                ),
              ],
            ),
          ],
          notes: contract['notes']?.toString(),
        );
      case 'worker_config':
        final config = workspace.storyConfigDraft;
        if (config == null) return null;
        return RpSetupStageDraftBlock(
          stageId: stageId,
          entries: [
            RpSetupDraftEntry(
              entryId: 'story_config',
              entryType: 'worker_config',
              semanticPath: 'worker_config',
              title: 'Worker 配置',
              displayLabel: 'story_config',
              summary: config['model_profile_ref']?.toString(),
              aliases: const [],
              tags: const ['legacy'],
              sections: [
                RpSetupDraftSection(
                  sectionId: 'model_profile',
                  title: 'Model Profile',
                  kind: 'text',
                  content: {
                    'text': config['model_profile_ref']?.toString() ?? '',
                  },
                  retrievalRole: 'detail',
                  tags: const ['legacy'],
                ),
                RpSetupDraftSection(
                  sectionId: 'worker_profile',
                  title: 'Worker Profile',
                  kind: 'text',
                  content: {
                    'text': config['worker_profile_ref']?.toString() ?? '',
                  },
                  retrievalRole: 'detail',
                  tags: const ['legacy'],
                ),
                RpSetupDraftSection(
                  sectionId: 'post_write_policy',
                  title: 'Post Write Preset',
                  kind: 'text',
                  content: {
                    'text':
                        config['post_write_policy_preset']?.toString() ?? '',
                  },
                  retrievalRole: 'detail',
                  tags: const ['legacy'],
                ),
              ],
            ),
          ],
          notes: config['notes']?.toString(),
        );
      default:
        return null;
    }
  }

  RpSetupDraftEntry _legacyFoundationEntryToDraftEntry(
    Map<String, dynamic> entry,
  ) {
    final summary = _entrySummary(entry);
    final content = entry['content'];
    final details = content is Map ? content['details']?.toString() : null;
    final notes = content is Map ? content['notes']?.toString() : null;
    final sections = <RpSetupDraftSection>[
      RpSetupDraftSection(
        sectionId: 'summary',
        title: '概要',
        kind: 'text',
        content: {'text': summary},
        retrievalRole: 'summary',
        tags: const ['legacy'],
      ),
    ];
    if (details != null && details.trim().isNotEmpty) {
      sections.add(
        RpSetupDraftSection(
          sectionId: 'details',
          title: '细节',
          kind: 'text',
          content: {'text': details},
          retrievalRole: 'detail',
          tags: const ['legacy'],
        ),
      );
    }
    if (notes != null && notes.trim().isNotEmpty) {
      sections.add(
        RpSetupDraftSection(
          sectionId: 'notes',
          title: '备注',
          kind: 'text',
          content: {'text': notes},
          retrievalRole: 'note',
          tags: const ['legacy'],
        ),
      );
    }
    return RpSetupDraftEntry(
      entryId:
          entry['entry_id']?.toString() ?? entry['path']?.toString() ?? summary,
      entryType: entry['domain']?.toString() ?? 'foundation',
      semanticPath:
          entry['path']?.toString() ?? entry['entry_id']?.toString() ?? summary,
      title: entry['title']?.toString().isNotEmpty == true
          ? entry['title'].toString()
          : summary,
      displayLabel: entry['path']?.toString(),
      summary: summary,
      aliases: [
        if (entry['title']?.toString().isNotEmpty == true)
          entry['title'].toString(),
      ],
      tags: (entry['tags'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      sections: sections,
    );
  }

  String _legacyListSummary(dynamic value) {
    final items = (value as List? ?? const [])
        .map((item) => item.toString())
        .where((item) => item.trim().isNotEmpty)
        .toList();
    if (items.isEmpty) {
      return '暂无内容';
    }
    return items.join(' / ');
  }

  List<String> _legacyStagePlan() {
    return _SetupWizardStage.values.map((stage) => _stageIdFor(stage)).toList();
  }

  _SetupStageMeta _stageMetaFor(String stageId) {
    return _setupStageMetaById[stageId] ??
        _SetupStageMeta(
          stageId: stageId,
          title: _humanizeStageId(stageId),
          description: '当前阶段内容由后端 stage contract 提供。',
          promptHint: '例如：请继续收敛当前阶段。',
          legacyStepId: null,
          icon: OwuiIcons.dashboard,
        );
  }

  _SetupWizardStage? _stageForId(String stageId) {
    switch (stageId) {
      case 'world_background':
        return _SetupWizardStage.worldBackground;
      case 'character_design':
        return _SetupWizardStage.characterDesign;
      case 'plot_blueprint':
        return _SetupWizardStage.plotBlueprint;
      case 'writer_config':
        return _SetupWizardStage.writerConfig;
      case 'worker_config':
        return _SetupWizardStage.workerConfig;
      case 'overview':
        return _SetupWizardStage.overview;
      case 'activate':
        return _SetupWizardStage.activate;
      default:
        return null;
    }
  }

  String _stageIdFor(_SetupWizardStage stage) {
    switch (stage) {
      case _SetupWizardStage.worldBackground:
        return 'world_background';
      case _SetupWizardStage.characterDesign:
        return 'character_design';
      case _SetupWizardStage.plotBlueprint:
        return 'plot_blueprint';
      case _SetupWizardStage.writerConfig:
        return 'writer_config';
      case _SetupWizardStage.workerConfig:
        return 'worker_config';
      case _SetupWizardStage.overview:
        return 'overview';
      case _SetupWizardStage.activate:
        return 'activate';
    }
  }

  String _humanizeStageId(String stageId) {
    return stageId
        .split('_')
        .where((part) => part.isNotEmpty)
        .map((part) => '${part[0].toUpperCase()}${part.substring(1)}')
        .join(' ');
  }
}

enum _SetupWizardStage {
  worldBackground('世界观背景'),
  characterDesign('角色设定'),
  plotBlueprint('伏笔剧情设计'),
  writerConfig('作家配置'),
  workerConfig('worker配置'),
  overview('全览'),
  activate('activate');

  final String label;

  const _SetupWizardStage(this.label);
}

class _SetupStageMeta {
  final String stageId;
  final String title;
  final String description;
  final String promptHint;
  final String? legacyStepId;
  final IconData icon;

  const _SetupStageMeta({
    required this.stageId,
    required this.title,
    required this.description,
    required this.promptHint,
    required this.legacyStepId,
    required this.icon,
  });
}

const Map<String, _SetupStageMeta> _setupStageMetaById = {
  'world_background': _SetupStageMeta(
    stageId: 'world_background',
    title: '世界观背景',
    description: '只看世界规则、背景设定和稳定的环境事实。',
    promptHint: '例如：先帮我补齐世界规则、地理背景和稳定设定。',
    legacyStepId: 'foundation',
    icon: OwuiIcons.globe,
  ),
  'character_design': _SetupStageMeta(
    stageId: 'character_design',
    title: '角色设定',
    description: '只看人物设定、人物背景和角色 voice seed 相关条目。',
    promptHint: '例如：继续收敛主角设定、关系和 voice seed。',
    legacyStepId: 'foundation',
    icon: OwuiIcons.person,
  ),
  'plot_blueprint': _SetupStageMeta(
    stageId: 'plot_blueprint',
    title: '伏笔 / 剧情设计',
    description: '只看 premise、冲突、章节推进和伏笔回收方向。',
    promptHint: '例如：请把核心冲突、章节推进和伏笔回收方向收敛清楚。',
    legacyStepId: 'longform_blueprint',
    icon: OwuiIcons.workflow,
  ),
  'writer_config': _SetupStageMeta(
    stageId: 'writer_config',
    title: '作家配置',
    description: '只看 POV、风格、写作约束和任务写作规则。',
    promptHint: '例如：帮我明确 POV、文风、写作约束和任务写作规则。',
    legacyStepId: 'writing_contract',
    icon: OwuiIcons.document,
  ),
  'worker_config': _SetupStageMeta(
    stageId: 'worker_config',
    title: 'Worker 配置',
    description: '只看模型画像、worker 画像和 post-write preset。',
    promptHint: '例如：帮我确定 model profile、worker profile 和 post-write preset。',
    legacyStepId: 'story_config',
    icon: OwuiIcons.tools,
  ),
  'overview': _SetupStageMeta(
    stageId: 'overview',
    title: '全览 / Review',
    description: '统一检查 setup 是否已经收敛到可激活状态。',
    promptHint: '例如：请帮我检查哪些部分已经可以提交 review，哪些还缺。',
    legacyStepId: null,
    icon: OwuiIcons.dashboard,
  ),
  'activate': _SetupStageMeta(
    stageId: 'activate',
    title: 'Activate',
    description: '最后一步才显示激活入口。',
    promptHint: '例如：请先检查当前是否已经满足激活条件。',
    legacyStepId: null,
    icon: OwuiIcons.checkCircle,
  ),
  'rp_interaction_contract': _SetupStageMeta(
    stageId: 'rp_interaction_contract',
    title: '互动契约',
    description: '角色扮演模式的互动边界、玩家 agency 和对话规则。',
    promptHint: '例如：请继续收敛角色扮演的互动契约和约束。',
    legacyStepId: null,
    icon: OwuiIcons.conversation,
  ),
  'trpg_rules': _SetupStageMeta(
    stageId: 'trpg_rules',
    title: 'TRPG 规则',
    description: 'TRPG 模式的规则、判定、表格与机制说明。',
    promptHint: '例如：请继续收敛 TRPG 的规则、判定和表格结构。',
    legacyStepId: null,
    icon: OwuiIcons.shield,
  ),
};

enum _SetupChatEntryKind { user, assistant, system }

class _SetupChatEntry {
  final _SetupChatEntryKind kind;
  String content;
  String thinking;
  List<String> toolEvents;
  bool isStreaming;

  _SetupChatEntry({
    required this.kind,
    required this.content,
    List<String>? toolEvents,
    this.isStreaming = false,
  }) : thinking = '',
       toolEvents = toolEvents ?? [];

  factory _SetupChatEntry.user(String content) =>
      _SetupChatEntry(kind: _SetupChatEntryKind.user, content: content);

  factory _SetupChatEntry.assistantStreaming() => _SetupChatEntry(
    kind: _SetupChatEntryKind.assistant,
    content: '',
    isStreaming: true,
  );

  factory _SetupChatEntry.system(String content) =>
      _SetupChatEntry(kind: _SetupChatEntryKind.system, content: content);
}
