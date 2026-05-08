import 'package:flutter/material.dart';

import '../adapters/ai_provider.dart';
import '../chat_ui/owui/components/owui_app_bar.dart';
import '../chat_ui/owui/components/owui_card.dart';
import '../chat_ui/owui/components/owui_scaffold.dart';
import '../chat_ui/owui/components/owui_snack_bar.dart';
import '../chat_ui/owui/owui_tokens_ext.dart';
import '../main.dart';
import '../models/model_config.dart';
import '../models/story_runtime.dart';
import '../pages/rp_model_config_page.dart';
import '../services/backend_story_service.dart';
import '../widgets/story_session_drawer.dart';

class LongformStoryPage extends StatefulWidget {
  final String? sessionId;

  const LongformStoryPage({super.key, this.sessionId});

  @override
  State<LongformStoryPage> createState() => _LongformStoryPageState();
}

enum _RevisionReviewMode {
  viewing('viewing'),
  editing('editing'),
  suggesting('suggesting');

  final String wireName;

  const _RevisionReviewMode(this.wireName);
}

class _LongformStoryPageState extends State<LongformStoryPage> {
  final _service = BackendStoryService();
  final _messageController = TextEditingController();
  final _reviewDraftController = TextEditingController();
  final _reviewCommentController = TextEditingController();
  final _reviewTrackedChangeController = TextEditingController();

  RpChapterSnapshot? _snapshot;
  List<RpStorySession> _sessions = const [];
  String? _currentSessionId;
  String? _selectedProviderId;
  String? _selectedModelId;
  String? _selectedRetrievalEmbeddingProviderId;
  String? _selectedRetrievalEmbeddingModelId;
  String? _selectedRetrievalRerankProviderId;
  String? _selectedRetrievalRerankModelId;
  String? _selectedGraphExtractionProviderId;
  String? _selectedGraphExtractionModelId;
  bool _isLoading = true;
  bool _isSending = false;
  String _streamingText = '';
  String _streamingThinking = '';
  String? _streamingCommandKind;
  String? _selectedPendingArtifactId;
  String? _selectedReviewBlockId;
  RpRevisionReviewSurface? _reviewSurface;
  _RevisionReviewMode _reviewMode = _RevisionReviewMode.viewing;
  bool _isReviewLoading = false;
  bool _isReviewSaving = false;

  @override
  void initState() {
    super.initState();
    _currentSessionId = widget.sessionId;
    final defaultPair = globalModelServiceManager.getDefaultProviderModel();
    _selectedProviderId = defaultPair.provider?.id;
    _selectedModelId = defaultPair.model?.id;
    _load();
  }

  @override
  void dispose() {
    _messageController.dispose();
    _reviewDraftController.dispose();
    _reviewCommentController.dispose();
    _reviewTrackedChangeController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _isLoading = true);
    try {
      final sessions = await _service.listSessions();
      final resolvedSessionId = _resolveSessionId(sessions);
      final snapshot = resolvedSessionId == null
          ? null
          : await _service.getSession(resolvedSessionId);
      if (!mounted) return;
      setState(() {
        _sessions = sessions;
        _currentSessionId = resolvedSessionId;
        _snapshot = snapshot;
        _selectedPendingArtifactId = _resolveSelectedPendingArtifactId(
          snapshot,
          previousSelected: _selectedPendingArtifactId,
        );
        if (_reviewSurface?.artifactId != _selectedPendingArtifactId) {
          _reviewSurface = null;
          _selectedReviewBlockId = null;
        }
        _isLoading = false;
      });
      _syncModelSelections();
      await _loadReviewSurfaceForSelection();
    } catch (e) {
      if (!mounted) return;
      setState(() => _isLoading = false);
      OwuiSnackBars.error(context, message: '加载 story session 失败: $e');
    }
  }

  Future<void> _refresh() async {
    final sessions = await _service.listSessions();
    final resolvedSessionId = _resolveSessionId(sessions);
    final snapshot = resolvedSessionId == null
        ? null
        : await _service.getSession(resolvedSessionId);
    if (!mounted) return;
    setState(() {
      _sessions = sessions;
      _currentSessionId = resolvedSessionId;
      _snapshot = snapshot;
      _selectedPendingArtifactId = _resolveSelectedPendingArtifactId(
        snapshot,
        previousSelected: _selectedPendingArtifactId,
      );
      if (_reviewSurface?.artifactId != _selectedPendingArtifactId) {
        _reviewSurface = null;
        _selectedReviewBlockId = null;
      }
    });
    _syncModelSelections();
    await _loadReviewSurfaceForSelection();
  }

  String? _resolveSessionId(List<RpStorySession> sessions) {
    if (_currentSessionId != null &&
        sessions.any((item) => item.sessionId == _currentSessionId)) {
      return _currentSessionId!;
    }
    if (widget.sessionId != null &&
        sessions.any((item) => item.sessionId == widget.sessionId)) {
      return widget.sessionId;
    }
    if (sessions.isNotEmpty) {
      return sessions.first.sessionId;
    }
    return widget.sessionId;
  }

  String? _resolveSelectedPendingArtifactId(
    RpChapterSnapshot? snapshot, {
    required String? previousSelected,
  }) {
    if (snapshot == null) return null;
    final candidates = snapshot.pendingSegmentCandidates;
    if (candidates.isEmpty) return null;
    if (previousSelected != null &&
        candidates.any((item) => item.artifactId == previousSelected)) {
      return previousSelected;
    }
    return snapshot.pendingSegment?.artifactId ?? candidates.last.artifactId;
  }

  RpStoryArtifact? _selectedPendingSegment(RpChapterSnapshot snapshot) {
    final selectedId = _selectedPendingArtifactId;
    if (selectedId != null) {
      for (final item in snapshot.pendingSegmentCandidates) {
        if (item.artifactId == selectedId) return item;
      }
    }
    return snapshot.pendingSegment;
  }

  Future<void> _selectPendingArtifact(String artifactId) async {
    if (_isSending || _selectedPendingArtifactId == artifactId) return;
    setState(() {
      _selectedPendingArtifactId = artifactId;
      _selectedReviewBlockId = null;
      _reviewSurface = null;
    });
    await _loadReviewSurfaceForSelection();
  }

  Future<void> _loadReviewSurfaceForSelection() async {
    final sessionId = _currentSessionId;
    final artifactId = _selectedPendingArtifactId;
    if (sessionId == null || artifactId == null) {
      if (!mounted) return;
      setState(() {
        _reviewSurface = null;
        _selectedReviewBlockId = null;
      });
      return;
    }
    await _loadReviewSurface(sessionId: sessionId, artifactId: artifactId);
  }

  Future<void> _loadReviewSurface({
    required String sessionId,
    required String artifactId,
  }) async {
    if (!mounted) return;
    setState(() => _isReviewLoading = true);
    try {
      final surface = await _service.getRevisionReviewSurface(
        sessionId: sessionId,
        artifactId: artifactId,
        mode: _reviewMode.wireName,
      );
      if (!mounted) return;
      setState(() {
        _reviewSurface = surface;
        _reviewDraftController.text = surface.draftText;
        _selectedReviewBlockId = _resolveReviewBlockId(surface);
        _isReviewLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _isReviewLoading = false);
      OwuiSnackBars.warning(context, message: '加载修订视图失败: $e');
    }
  }

  String? _resolveReviewBlockId(RpRevisionReviewSurface surface) {
    final current = _selectedReviewBlockId;
    if (current != null &&
        surface.draftDocument.blocks.any((item) => item.blockId == current)) {
      return current;
    }
    final blocks = surface.draftDocument.blocks;
    return blocks.isEmpty ? null : blocks.first.blockId;
  }

  RpDraftDocumentBlock? _reviewBlockById(String blockId) {
    final surface = _reviewSurface;
    if (surface == null) return null;
    for (final block in surface.draftDocument.blocks) {
      if (block.blockId == blockId) return block;
    }
    return null;
  }

  Future<void> _selectSession(String sessionId) async {
    setState(() {
      _currentSessionId = sessionId;
      _isLoading = true;
      _streamingText = '';
      _streamingThinking = '';
      _streamingCommandKind = null;
      _reviewSurface = null;
      _selectedReviewBlockId = null;
    });
    try {
      final snapshot = await _service.getSession(sessionId);
      final sessions = await _service.listSessions();
      if (!mounted) return;
      setState(() {
        _sessions = sessions;
        _snapshot = snapshot;
        _currentSessionId = sessionId;
        _selectedPendingArtifactId = _resolveSelectedPendingArtifactId(
          snapshot,
          previousSelected: null,
        );
        _reviewSurface = null;
        _selectedReviewBlockId = null;
        _isLoading = false;
      });
      _syncModelSelections();
      await _loadReviewSurfaceForSelection();
    } catch (e) {
      if (!mounted) return;
      setState(() => _isLoading = false);
      OwuiSnackBars.error(context, message: '切换 story session 失败: $e');
    }
  }

  void _syncModelSelections() {
    _syncSelectedProviderAndModel();
    _syncRetrievalModelSelections();
  }

  void _syncSelectedProviderAndModel() {
    final providers = globalModelServiceManager.getEnabledProviders();
    if (providers.isEmpty) {
      if (mounted) {
        setState(() {
          _selectedProviderId = null;
          _selectedModelId = null;
        });
      }
      return;
    }

    final providerId = providers.any((item) => item.id == _selectedProviderId)
        ? _selectedProviderId!
        : providers.first.id;
    final models = globalModelServiceManager
        .getModelsByProvider(providerId)
        .where((item) => item.isEnabled)
        .toList();
    final modelId = models.any((item) => item.id == _selectedModelId)
        ? _selectedModelId
        : (models.isNotEmpty ? models.first.id : null);

    if (!mounted) return;
    setState(() {
      _selectedProviderId = providerId;
      _selectedModelId = modelId;
    });
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
    final config =
        _snapshot?.session.runtimeStoryConfig ?? const <String, dynamic>{};
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

  Future<void> _persistRetrievalRuntimeConfig({
    required String? embeddingProviderId,
    required String? embeddingModelId,
    required String? rerankProviderId,
    required String? rerankModelId,
    required String? graphExtractionProviderId,
    required String? graphExtractionModelId,
  }) async {
    final sessionId = _currentSessionId;
    final current = _snapshot?.session.runtimeStoryConfig;
    if (sessionId == null || current == null) {
      return;
    }

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

    final snapshot = await _service.updateRuntimeStoryConfig(
      sessionId: sessionId,
      patch: {
        'retrieval_embedding_provider_id': embeddingProviderId,
        'retrieval_embedding_model_id': embeddingModelId,
        'retrieval_rerank_provider_id': rerankProviderId,
        'retrieval_rerank_model_id': rerankModelId,
        'graph_extraction_provider_id': graphExtractionProviderId,
        'graph_extraction_model_id': graphExtractionModelId,
      },
    );
    List<RpStorySession>? sessions;
    try {
      sessions = await _service.listSessions();
    } catch (_) {
      sessions = null;
    }
    if (!mounted) return;
    setState(() {
      _snapshot = snapshot;
      if (sessions != null) {
        _sessions = sessions;
      }
    });
    _syncRetrievalModelSelections();
  }

  Future<void> _resetRetrievalRuntimeOverrides() async {
    await _persistRetrievalRuntimeConfig(
      embeddingProviderId: null,
      embeddingModelId: null,
      rerankProviderId: null,
      rerankModelId: null,
      graphExtractionProviderId: null,
      graphExtractionModelId: null,
    );
  }

  Future<void> _setReviewMode(_RevisionReviewMode mode) async {
    if (_reviewMode == mode || _isReviewSaving) return;
    setState(() => _reviewMode = mode);
    await _loadReviewSurfaceForSelection();
  }

  Future<void> _saveReviewDraft() async {
    final sessionId = _currentSessionId;
    final artifactId = _selectedPendingArtifactId;
    if (sessionId == null || artifactId == null || _isReviewSaving) return;
    setState(() => _isReviewSaving = true);
    try {
      final snapshot = await _service.updateRevisionDraft(
        sessionId: sessionId,
        artifactId: artifactId,
        contentText: _reviewDraftController.text,
      );
      List<RpStorySession>? sessions;
      try {
        sessions = await _service.listSessions();
      } catch (_) {
        sessions = null;
      }
      if (!mounted) return;
      setState(() {
        _snapshot = snapshot;
        if (sessions != null) _sessions = sessions;
        _isReviewSaving = false;
      });
      await _loadReviewSurfaceForSelection();
      if (!mounted) return;
      OwuiSnackBars.success(context, message: '已保存 draft candidate 编辑');
    } catch (e) {
      if (!mounted) return;
      setState(() => _isReviewSaving = false);
      OwuiSnackBars.error(context, message: '保存修订草稿失败: $e');
    }
  }

  Future<void> _addReviewComment() async {
    final sessionId = _currentSessionId;
    final artifactId = _selectedPendingArtifactId;
    final blockId = _selectedReviewBlockId;
    final text = _reviewCommentController.text.trim();
    if (sessionId == null ||
        artifactId == null ||
        blockId == null ||
        text.isEmpty ||
        _isReviewSaving) {
      return;
    }
    setState(() => _isReviewSaving = true);
    try {
      final block = _reviewBlockById(blockId);
      final surface = await _service.addRevisionComment(
        sessionId: sessionId,
        artifactId: artifactId,
        blockId: blockId,
        instructionText: text,
        selectedExcerpt: block?.selectedExcerpt ?? block?.text,
      );
      if (!mounted) return;
      setState(() {
        _reviewSurface = surface;
        _reviewCommentController.clear();
        _selectedReviewBlockId = _resolveReviewBlockId(surface);
        _isReviewSaving = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _isReviewSaving = false);
      OwuiSnackBars.error(context, message: '添加批注失败: $e');
    }
  }

  Future<void> _addReviewTrackedChange() async {
    final sessionId = _currentSessionId;
    final artifactId = _selectedPendingArtifactId;
    final blockId = _selectedReviewBlockId;
    final suggestedText = _reviewTrackedChangeController.text.trim();
    if (sessionId == null ||
        artifactId == null ||
        blockId == null ||
        suggestedText.isEmpty ||
        _isReviewSaving) {
      return;
    }
    setState(() => _isReviewSaving = true);
    try {
      final block = _reviewBlockById(blockId);
      final surface = await _service.addRevisionTrackedChange(
        sessionId: sessionId,
        artifactId: artifactId,
        blockId: blockId,
        originalText: block?.text,
        suggestedText: suggestedText,
      );
      if (!mounted) return;
      setState(() {
        _reviewSurface = surface;
        _reviewTrackedChangeController.clear();
        _selectedReviewBlockId = _resolveReviewBlockId(surface);
        _isReviewSaving = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _isReviewSaving = false);
      OwuiSnackBars.error(context, message: '添加修订建议失败: $e');
    }
  }

  Future<void> _resolveReviewComment(String commentId) async {
    await _updateReviewCommentLifecycle(commentId: commentId, resolve: true);
  }

  Future<void> _deleteReviewComment(String commentId) async {
    await _updateReviewCommentLifecycle(commentId: commentId, resolve: false);
  }

  Future<void> _updateReviewCommentLifecycle({
    required String commentId,
    required bool resolve,
  }) async {
    final sessionId = _currentSessionId;
    final artifactId = _selectedPendingArtifactId;
    if (sessionId == null || artifactId == null || _isReviewSaving) return;
    setState(() => _isReviewSaving = true);
    try {
      final surface = resolve
          ? await _service.resolveRevisionComment(
              sessionId: sessionId,
              artifactId: artifactId,
              commentId: commentId,
            )
          : await _service.deleteRevisionComment(
              sessionId: sessionId,
              artifactId: artifactId,
              commentId: commentId,
            );
      if (!mounted) return;
      setState(() {
        _reviewSurface = surface;
        _selectedReviewBlockId = _resolveReviewBlockId(surface);
        _isReviewSaving = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _isReviewSaving = false);
      OwuiSnackBars.error(context, message: '更新批注状态失败: $e');
    }
  }

  Future<void> _openModelConfigPage() async {
    if (_snapshot == null) return;
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => RpModelConfigPage(
          title: 'Longform Story · 模型配置',
          subtitle: '将 story 页面里的 agent / retrieval 配置表单抽离到独立页面，避免挤占正文讨论与审阅空间。',
          agentSectionTitle: 'Story Runtime 模型',
          agentSectionDescription: '这里选择当前 story 命令和讨论发送使用的模型，只影响前端当前会话的发送行为。',
          retrievalSectionTitle: 'Retrieval Runtime',
          retrievalSectionDescription:
              '这里修改 active story session 的 retrieval override；Embedding / Rerank / Graph Extraction 清空后都会回退到 setup 阶段写入的默认配置。',
          agentProviders: globalModelServiceManager.getEnabledProviders(),
          agentModelsForProvider: (providerId) => globalModelServiceManager
              .getModelsByProvider(providerId)
              .where((item) => item.isEnabled)
              .toList(),
          initialAgentProviderId: _selectedProviderId,
          initialAgentModelId: _selectedModelId,
          onAgentSelectionChanged: _updateAgentSelection,
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
          onPersistRetrievalConfig: _persistRetrievalRuntimeConfig,
          retrievalSecondaryActionLabel: 'Use Setup Defaults',
          onRetrievalSecondaryAction: _resetRetrievalRuntimeOverrides,
          retrievalSecondaryActionClearsSelections: true,
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

  Future<void> _runImmediateCommand(
    String commandKind, {
    String? targetArtifactId,
  }) async {
    final modelId = _selectedModelId;
    final sessionId = _currentSessionId;
    if (_snapshot == null ||
        modelId == null ||
        _isSending ||
        sessionId == null) {
      return;
    }
    final providerModel = globalModelServiceManager.getModelWithProvider(
      modelId,
    );
    if (providerModel == null) {
      OwuiSnackBars.warning(context, message: '请先选择可用模型');
      return;
    }
    setState(() => _isSending = true);
    try {
      final response = await _service.runTurn(
        sessionId: sessionId,
        commandKind: commandKind,
        modelId: modelId,
        providerId: providerModel.provider.id,
        targetArtifactId: targetArtifactId,
      );
      await _refresh();
      if (!mounted) return;
      if ((response.assistantText ?? '').isNotEmpty) {
        OwuiSnackBars.success(context, message: response.assistantText!);
      }
    } catch (e) {
      if (!mounted) return;
      OwuiSnackBars.error(context, message: '执行命令失败: $e');
    } finally {
      if (mounted) {
        setState(() => _isSending = false);
      }
    }
  }

  Future<void> _runStreamingCommand(
    String commandKind, {
    String? userPrompt,
    String? targetArtifactId,
  }) async {
    final modelId = _selectedModelId;
    final sessionId = _currentSessionId;
    if (_snapshot == null ||
        modelId == null ||
        _isSending ||
        sessionId == null) {
      return;
    }
    final providerModel = globalModelServiceManager.getModelWithProvider(
      modelId,
    );
    if (providerModel == null) {
      OwuiSnackBars.warning(context, message: '请先选择可用模型');
      return;
    }
    setState(() {
      _isSending = true;
      _streamingCommandKind = commandKind;
      _streamingText = '';
      _streamingThinking = '';
    });
    try {
      await for (final event in _service.streamTurn(
        sessionId: sessionId,
        commandKind: commandKind,
        modelId: modelId,
        providerId: providerModel.provider.id,
        userPrompt: userPrompt,
        targetArtifactId: targetArtifactId,
      )) {
        if (!mounted) return;
        setState(() {
          switch (event.type) {
            case AIStreamEventType.thinking:
              _streamingThinking += event.text ?? '';
              break;
            case AIStreamEventType.text:
              _streamingText += event.text ?? '';
              break;
            default:
              break;
          }
        });
      }
      await _refresh();
    } catch (e) {
      if (!mounted) return;
      OwuiSnackBars.error(context, message: '流式执行失败: $e');
    } finally {
      if (mounted) {
        setState(() {
          _isSending = false;
          _streamingCommandKind = null;
          _streamingThinking = '';
        });
      }
    }
  }

  Future<void> _sendDiscussion() async {
    final prompt = _messageController.text.trim();
    if (prompt.isEmpty) return;
    _messageController.clear();
    await _runStreamingCommand(
      _discussionCommandForPhase(
        _snapshot?.chapter.phase ?? 'outline_drafting',
      ),
      userPrompt: prompt,
    );
  }

  String _discussionCommandForPhase(String phase) {
    return 'discuss_outline';
  }

  @override
  Widget build(BuildContext context) {
    final spacing = context.owuiSpacing;
    if (_isLoading) {
      return OwuiScaffold(
        appBar: _buildAppBar(title: 'Longform Story'),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    final snapshot = _snapshot;
    if (snapshot == null) {
      return OwuiScaffold(
        drawer: StorySessionDrawer(
          sessions: _sessions,
          currentSessionId: _currentSessionId,
          onSessionSelected: _selectSession,
          onRefresh: _refresh,
        ),
        appBar: _buildAppBar(title: 'Longform Story'),
        body: const Center(
          child: Text(
            '当前还没有 active story session，可先从 prestory setup 里 activate。',
          ),
        ),
      );
    }

    final isWide = MediaQuery.of(context).size.width >= 1180;

    return OwuiScaffold(
      drawer: StorySessionDrawer(
        sessions: _sessions,
        currentSessionId: _currentSessionId,
        onSessionSelected: _selectSession,
        onRefresh: _refresh,
      ),
      appBar: _buildAppBar(
        title: 'Longform Story · Chapter ${snapshot.chapter.chapterIndex}',
      ),
      body: Padding(
        padding: EdgeInsets.all(spacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildHeader(snapshot),
            SizedBox(height: spacing.lg),
            Expanded(
              child: isWide
                  ? Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(flex: 7, child: _buildStoryPane(snapshot)),
                        SizedBox(width: spacing.lg),
                        Expanded(
                          flex: 5,
                          child: _buildDiscussionPane(snapshot),
                        ),
                      ],
                    )
                  : Column(
                      children: [
                        Expanded(flex: 6, child: _buildStoryPane(snapshot)),
                        SizedBox(height: spacing.lg),
                        Expanded(
                          flex: 5,
                          child: _buildDiscussionPane(snapshot),
                        ),
                      ],
                    ),
            ),
          ],
        ),
      ),
    );
  }

  PreferredSizeWidget _buildAppBar({required String title}) {
    final canPop = Navigator.of(context).canPop();
    return OwuiAppBar(
      automaticallyImplyLeading: false,
      leading: canPop
          ? IconButton(
              tooltip: '返回',
              icon: const Icon(Icons.arrow_back),
              onPressed: () => Navigator.of(context).maybePop(),
            )
          : Builder(
              builder: (context) => IconButton(
                tooltip: 'Sessions',
                icon: const Icon(Icons.menu),
                onPressed: () => Scaffold.of(context).openDrawer(),
              ),
            ),
      title: Text(title),
      actions: [
        if (canPop)
          Builder(
            builder: (context) => IconButton(
              tooltip: 'Sessions',
              icon: const Icon(Icons.menu_book_outlined),
              onPressed: () => Scaffold.of(context).openDrawer(),
            ),
          ),
        IconButton(
          onPressed: _refresh,
          tooltip: '刷新',
          icon: const Icon(Icons.refresh),
        ),
      ],
    );
  }

  Widget _buildHeader(RpChapterSnapshot snapshot) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    final title =
        snapshot.chapter.acceptedOutlineJson?['title']?.toString() ??
        snapshot.chapter.chapterGoal ??
        'Chapter ${snapshot.chapter.chapterIndex}';

    return OwuiCard(
      padding: EdgeInsets.all(spacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
              fontWeight: FontWeight.w700,
              letterSpacing: -0.4,
            ),
          ),
          SizedBox(height: spacing.sm),
          Wrap(
            spacing: spacing.sm,
            runSpacing: spacing.sm,
            children: [
              _statusChip('Phase', snapshot.chapter.phase),
              _statusChip('State', snapshot.session.sessionState),
              _statusChip(
                'Accepted Segments',
                snapshot.chapter.acceptedSegmentIds.length.toString(),
              ),
              if (snapshot.session.currentStateJson['narrative_progress']
                  is Map)
                _statusChip(
                  'Progress',
                  (snapshot.session.currentStateJson['narrative_progress']
                              as Map)['accepted_segments']
                          ?.toString() ??
                      '0',
                ),
            ],
          ),
          SizedBox(height: spacing.md),
          Text(
            'Left column keeps accepted outline and prose visible. Right column stays for discussion, review, and command control.',
            style: Theme.of(
              context,
            ).textTheme.bodyMedium?.copyWith(color: colors.textSecondary),
          ),
        ],
      ),
    );
  }

  Widget _statusChip(String label, String value) {
    final colors = context.owuiColors;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: colors.surface2,
        borderRadius: BorderRadius.circular(context.owuiRadius.rXl),
        border: Border.all(color: colors.borderSubtle),
      ),
      child: Text('$label · $value'),
    );
  }

  Widget _buildStoryPane(RpChapterSnapshot snapshot) {
    final spacing = context.owuiSpacing;
    final acceptedOutline = snapshot.acceptedOutlineArtifacts.isNotEmpty
        ? snapshot.acceptedOutlineArtifacts.last
        : null;
    final acceptedSegments = snapshot.acceptedSegmentArtifacts;
    final pendingCandidates = snapshot.pendingSegmentCandidates;
    final pendingSegment = _selectedPendingSegment(snapshot);

    return OwuiCard(
      padding: EdgeInsets.all(spacing.lg),
      child: ListView(
        children: [
          Text('Story Surface', style: Theme.of(context).textTheme.titleLarge),
          SizedBox(height: spacing.md),
          if (acceptedOutline != null)
            _buildArtifactCard(acceptedOutline, isPrimary: true),
          if (acceptedOutline == null && snapshot.latestOutlineDraft != null)
            _buildArtifactCard(snapshot.latestOutlineDraft!, isPrimary: true),
          if (acceptedOutline == null && snapshot.latestOutlineDraft == null)
            _emptyPaneNote(
              'No outline yet. Generate one to start the chapter loop.',
            ),
          if (acceptedSegments.isNotEmpty) ...[
            SizedBox(height: spacing.lg),
            Text(
              'Accepted Segments',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            SizedBox(height: spacing.md),
            ...acceptedSegments.map(
              (item) => Padding(
                padding: EdgeInsets.only(bottom: spacing.md),
                child: _buildArtifactCard(item),
              ),
            ),
          ],
          if (pendingCandidates.isNotEmpty || _isStreamingLeftPane) ...[
            SizedBox(height: spacing.lg),
            if (pendingCandidates.isNotEmpty)
              _buildReviewSurfaceSection(
                snapshot: snapshot,
                pendingCandidates: pendingCandidates,
                pendingSegment: pendingSegment,
              ),
            if (_isStreamingLeftPane)
              Padding(
                padding: EdgeInsets.only(
                  top: pendingCandidates.isNotEmpty ? spacing.md : 0,
                ),
                child: _buildStreamingCard(),
              ),
          ],
        ],
      ),
    );
  }

  Widget _buildReviewSurfaceSection({
    required RpChapterSnapshot snapshot,
    required List<RpStoryArtifact> pendingCandidates,
    required RpStoryArtifact? pendingSegment,
  }) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    final selectedId = pendingSegment?.artifactId;
    final multipleCandidates = pendingCandidates.length > 1;

    return Container(
      padding: EdgeInsets.all(spacing.lg),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(context.owuiRadius.rXl),
        border: Border.all(color: colors.borderSubtle),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  'Review Surface',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              IconButton(
                tooltip: '刷新修订视图',
                onPressed: _isReviewLoading || _isSending
                    ? null
                    : _loadReviewSurfaceForSelection,
                icon: const Icon(Icons.refresh),
              ),
            ],
          ),
          SizedBox(height: spacing.md),
          _buildCandidateSelector(
            candidates: pendingCandidates,
            selectedArtifactId: selectedId,
          ),
          SizedBox(height: spacing.md),
          _buildReviewToolbar(
            multipleCandidates: multipleCandidates,
            selectedArtifactId: selectedId,
          ),
          SizedBox(height: spacing.md),
          if (_isReviewLoading)
            const LinearProgressIndicator(minHeight: 2)
          else if (_reviewSurface == null)
            _emptyPaneNote('当前候选还没有可用修订视图。')
          else
            LayoutBuilder(
              builder: (context, constraints) {
                final sidePanel = _buildReviewSidePanel(_reviewSurface!);
                if (constraints.maxWidth >= 900) {
                  return Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        flex: 7,
                        child: _buildDocumentSurface(_reviewSurface!),
                      ),
                      SizedBox(width: spacing.lg),
                      Expanded(flex: 4, child: sidePanel),
                    ],
                  );
                }
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _buildDocumentSurface(_reviewSurface!),
                    SizedBox(height: spacing.lg),
                    sidePanel,
                  ],
                );
              },
            ),
        ],
      ),
    );
  }

  Widget _buildCandidateSelector({
    required List<RpStoryArtifact> candidates,
    required String? selectedArtifactId,
  }) {
    final spacing = context.owuiSpacing;
    return Wrap(
      spacing: spacing.sm,
      runSpacing: spacing.sm,
      children: [
        for (var index = 0; index < candidates.length; index++)
          ChoiceChip(
            label: Text('Candidate ${index + 1}'),
            selected: candidates[index].artifactId == selectedArtifactId,
            onSelected: _isSending || _isReviewSaving
                ? null
                : (_) => _selectPendingArtifact(candidates[index].artifactId),
          ),
      ],
    );
  }

  Widget _buildReviewToolbar({
    required bool multipleCandidates,
    required String? selectedArtifactId,
  }) {
    final spacing = context.owuiSpacing;
    final modes = [
      (_RevisionReviewMode.viewing, Icons.visibility_outlined, 'Viewing'),
      (_RevisionReviewMode.editing, Icons.edit_note_outlined, 'Editing'),
      (
        _RevisionReviewMode.suggesting,
        Icons.rate_review_outlined,
        'Suggesting',
      ),
    ];
    return Wrap(
      spacing: spacing.sm,
      runSpacing: spacing.sm,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        for (final item in modes)
          ChoiceChip(
            avatar: Icon(item.$2, size: 18),
            label: Text(item.$3),
            selected: _reviewMode == item.$1,
            onSelected: _isReviewSaving ? null : (_) => _setReviewMode(item.$1),
          ),
        SizedBox(width: spacing.sm),
        OutlinedButton.icon(
          onPressed: _isSending || selectedArtifactId == null
              ? null
              : () => _runStreamingCommand(
                  'rewrite_pending_segment',
                  targetArtifactId: selectedArtifactId,
                ),
          icon: const Icon(Icons.auto_fix_high_outlined),
          label: const Text('Rewrite'),
        ),
        FilledButton.tonalIcon(
          onPressed: _isSending || selectedArtifactId == null
              ? null
              : () => _runImmediateCommand(
                  'accept_pending_segment',
                  targetArtifactId: selectedArtifactId,
                ),
          icon: Icon(
            multipleCandidates
                ? Icons.check_circle_outline
                : Icons.done_outline,
          ),
          label: const Text('Accept & Continue'),
        ),
      ],
    );
  }

  Widget _buildDocumentSurface(RpRevisionReviewSurface surface) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    if (_reviewMode == _RevisionReviewMode.editing) {
      return Container(
        padding: EdgeInsets.all(spacing.lg),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(context.owuiRadius.rLg),
          border: Border.all(color: colors.borderSubtle),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.08),
              blurRadius: 18,
              offset: const Offset(0, 8),
            ),
          ],
        ),
        child: Column(
          children: [
            TextField(
              controller: _reviewDraftController,
              minLines: 14,
              maxLines: 28,
              style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                height: 1.65,
                color: Colors.black87,
              ),
              decoration: const InputDecoration(
                border: InputBorder.none,
                hintText: 'Draft candidate',
              ),
            ),
            SizedBox(height: spacing.md),
            Align(
              alignment: Alignment.centerRight,
              child: FilledButton.icon(
                onPressed: _isReviewSaving ? null : _saveReviewDraft,
                icon: const Icon(Icons.save_outlined),
                label: const Text('Save Draft'),
              ),
            ),
          ],
        ),
      );
    }

    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: spacing.xl,
        vertical: spacing.lg,
      ),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(context.owuiRadius.rLg),
        border: Border.all(color: colors.borderSubtle),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.08),
            blurRadius: 18,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final block in surface.draftDocument.blocks)
            _buildReviewBlock(block, surface: surface),
        ],
      ),
    );
  }

  Widget _buildReviewBlock(
    RpDraftDocumentBlock block, {
    required RpRevisionReviewSurface surface,
  }) {
    final spacing = context.owuiSpacing;
    final isSelected = block.blockId == _selectedReviewBlockId;
    final hasComment = surface.comments.any(
      (item) =>
          item.isActive && item.anchorRef.blockIds.contains(block.blockId),
    );
    final hasTrackedChange = surface.trackedChanges.any(
      (item) =>
          item.isActive && item.anchorRef.blockIds.contains(block.blockId),
    );
    final baseStyle = Theme.of(
      context,
    ).textTheme.bodyLarge?.copyWith(color: Colors.black87, height: 1.68);
    final style = block.blockKind == 'heading'
        ? Theme.of(context).textTheme.titleLarge?.copyWith(
            color: Colors.black87,
            fontWeight: FontWeight.w700,
          )
        : baseStyle;

    return InkWell(
      onTap: _reviewMode == _RevisionReviewMode.viewing
          ? null
          : () => setState(() => _selectedReviewBlockId = block.blockId),
      child: Container(
        margin: EdgeInsets.only(bottom: spacing.md),
        padding: EdgeInsets.all(spacing.md),
        decoration: BoxDecoration(
          color: isSelected
              ? Theme.of(context).colorScheme.primary.withValues(alpha: 0.08)
              : Colors.transparent,
          border: Border(
            left: BorderSide(
              color: hasTrackedChange
                  ? Colors.green.shade600
                  : (hasComment ? Colors.amber.shade700 : Colors.transparent),
              width: 3,
            ),
          ),
        ),
        child: Text(_blockDisplayText(block), style: style),
      ),
    );
  }

  String _blockDisplayText(RpDraftDocumentBlock block) {
    if (block.blockKind == 'list_item') return '• ${block.text}';
    if (block.blockKind == 'blockquote') return '> ${block.text}';
    return block.text;
  }

  Widget _buildReviewSidePanel(RpRevisionReviewSurface surface) {
    final spacing = context.owuiSpacing;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (_reviewMode == _RevisionReviewMode.suggesting)
          _buildReviewInputPanel(surface),
        if (_reviewMode == _RevisionReviewMode.suggesting)
          SizedBox(height: spacing.md),
        _buildCommentsList(surface),
        SizedBox(height: spacing.md),
        _buildTrackedChangesList(surface),
      ],
    );
  }

  Widget _buildReviewInputPanel(RpRevisionReviewSurface surface) {
    final spacing = context.owuiSpacing;
    final selectedBlockId = _selectedReviewBlockId;
    final selectedBlock = selectedBlockId == null
        ? null
        : _reviewBlockById(selectedBlockId);
    return Container(
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
            selectedBlock == null
                ? 'No block selected'
                : _blockLabel(selectedBlock),
            style: Theme.of(context).textTheme.titleSmall,
          ),
          SizedBox(height: spacing.md),
          TextField(
            controller: _reviewCommentController,
            minLines: 2,
            maxLines: 4,
            decoration: const InputDecoration(labelText: 'Comment'),
          ),
          SizedBox(height: spacing.sm),
          Align(
            alignment: Alignment.centerRight,
            child: OutlinedButton.icon(
              onPressed: selectedBlockId == null || _isReviewSaving
                  ? null
                  : _addReviewComment,
              icon: const Icon(Icons.add_comment_outlined),
              label: const Text('Add Comment'),
            ),
          ),
          SizedBox(height: spacing.md),
          TextField(
            controller: _reviewTrackedChangeController,
            minLines: 2,
            maxLines: 5,
            decoration: const InputDecoration(
              labelText: 'Suggested replacement',
            ),
          ),
          SizedBox(height: spacing.sm),
          Align(
            alignment: Alignment.centerRight,
            child: OutlinedButton.icon(
              onPressed: selectedBlockId == null || _isReviewSaving
                  ? null
                  : _addReviewTrackedChange,
              icon: const Icon(Icons.change_circle_outlined),
              label: const Text('Track Change'),
            ),
          ),
        ],
      ),
    );
  }

  String _blockLabel(RpDraftDocumentBlock block) {
    return '${block.blockKind} #${block.order + 1}';
  }

  Widget _buildCommentsList(RpRevisionReviewSurface surface) {
    final spacing = context.owuiSpacing;
    final active = surface.comments.where((item) => item.isActive).toList();
    final historyCount = surface.comments.length - active.length;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Comments', style: Theme.of(context).textTheme.titleSmall),
        SizedBox(height: spacing.sm),
        if (active.isEmpty) _emptyPaneNote('No active comments.'),
        for (final comment in active)
          Container(
            margin: EdgeInsets.only(bottom: spacing.sm),
            padding: EdgeInsets.all(spacing.md),
            decoration: BoxDecoration(
              color: context.owuiColors.surface2,
              borderRadius: BorderRadius.circular(context.owuiRadius.rLg),
              border: Border.all(color: context.owuiColors.borderSubtle),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(_anchorLabel(comment.anchorRef.blockIds)),
                SizedBox(height: spacing.xs),
                Text(comment.instructionText),
                SizedBox(height: spacing.sm),
                Wrap(
                  spacing: spacing.sm,
                  children: [
                    TextButton.icon(
                      onPressed: _isReviewSaving
                          ? null
                          : () => _resolveReviewComment(comment.commentId),
                      icon: const Icon(Icons.task_alt_outlined),
                      label: const Text('Resolve'),
                    ),
                    TextButton.icon(
                      onPressed: _isReviewSaving
                          ? null
                          : () => _deleteReviewComment(comment.commentId),
                      icon: const Icon(Icons.delete_outline),
                      label: const Text('Delete'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        if (historyCount > 0)
          Text(
            '$historyCount resolved/deleted comments in history',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: context.owuiColors.textSecondary,
            ),
          ),
      ],
    );
  }

  Widget _buildTrackedChangesList(RpRevisionReviewSurface surface) {
    final spacing = context.owuiSpacing;
    final active = surface.trackedChanges
        .where((item) => item.isActive)
        .toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Tracked Changes', style: Theme.of(context).textTheme.titleSmall),
        SizedBox(height: spacing.sm),
        if (active.isEmpty) _emptyPaneNote('No active tracked changes.'),
        for (final change in active)
          Container(
            margin: EdgeInsets.only(bottom: spacing.sm),
            padding: EdgeInsets.all(spacing.md),
            decoration: BoxDecoration(
              color: Colors.green.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(context.owuiRadius.rLg),
              border: Border.all(color: Colors.green.withValues(alpha: 0.22)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(_anchorLabel(change.anchorRef.blockIds)),
                if ((change.originalText ?? '').isNotEmpty) ...[
                  SizedBox(height: spacing.xs),
                  Text(
                    change.originalText!,
                    style: const TextStyle(
                      decoration: TextDecoration.lineThrough,
                    ),
                  ),
                ],
                if ((change.suggestedText ?? '').isNotEmpty) ...[
                  SizedBox(height: spacing.xs),
                  Text(
                    change.suggestedText!,
                    style: TextStyle(color: Colors.green.shade700),
                  ),
                ],
              ],
            ),
          ),
      ],
    );
  }

  String _anchorLabel(List<String> blockIds) {
    if (blockIds.isEmpty) return 'whole draft';
    final blocks = _reviewSurface?.draftDocument.blocks ?? const [];
    final labels = <String>[];
    for (final blockId in blockIds) {
      RpDraftDocumentBlock? block;
      for (final candidate in blocks) {
        if (candidate.blockId == blockId) {
          block = candidate;
          break;
        }
      }
      labels.add(block == null ? blockId : _blockLabel(block));
    }
    return labels.join(', ');
  }

  Widget _buildDiscussionPane(RpChapterSnapshot snapshot) {
    final spacing = context.owuiSpacing;
    final phase = snapshot.chapter.phase;
    return OwuiCard(
      padding: EdgeInsets.all(spacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Discussion / Review',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          SizedBox(height: spacing.md),
          Wrap(
            spacing: spacing.sm,
            runSpacing: spacing.sm,
            children: _buildCommandButtons(snapshot),
          ),
          SizedBox(height: spacing.lg),
          Expanded(
            child: ListView(
              children: [
                ...snapshot.discussionEntries.map(_buildDiscussionEntry),
                if (_isStreamingDiscussionPane) _buildStreamingCard(),
              ],
            ),
          ),
          SizedBox(height: spacing.md),
          TextField(
            controller: _messageController,
            minLines: 3,
            maxLines: 6,
            decoration: InputDecoration(
              labelText: switch (phase) {
                'outline_drafting' || 'outline_review' =>
                  'Discuss outline or request a sharper direction',
                'segment_drafting' || 'segment_review' || 'chapter_review' =>
                  'Discuss pacing, continuity, or rewrite direction',
                _ => 'Discuss current chapter state',
              },
              alignLabelWithHint: true,
            ),
          ),
          SizedBox(height: spacing.md),
          _buildComposerFooter(),
        ],
      ),
    );
  }

  String? _formatModelSelectionSummary({
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

  Widget _buildComposerFooter() {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    final agentSummary =
        _formatModelSelectionSummary(
          providerId: _selectedProviderId,
          modelId: _selectedModelId,
        ) ??
        '未选择';
    final embeddingSummary =
        _formatModelSelectionSummary(
          providerId: _selectedRetrievalEmbeddingProviderId,
          modelId: _selectedRetrievalEmbeddingModelId,
        ) ??
        '跟随 setup 默认';
    final rerankSummary =
        _formatModelSelectionSummary(
          providerId: _selectedRetrievalRerankProviderId,
          modelId: _selectedRetrievalRerankModelId,
        ) ??
        '跟随 setup 默认';
    final graphSummary =
        _formatModelSelectionSummary(
          providerId: _selectedGraphExtractionProviderId,
          modelId: _selectedGraphExtractionModelId,
        ) ??
        '跟随 setup 默认';

    return LayoutBuilder(
      builder: (context, constraints) {
        final summary = Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('当前模型配置', style: Theme.of(context).textTheme.titleSmall),
            SizedBox(height: spacing.xs),
            Text(
              'Agent: $agentSummary',
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
            ),
            SizedBox(height: spacing.xs),
            Text(
              'Retrieval: Embedding $embeddingSummary · Rerank $rerankSummary',
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
            ),
            SizedBox(height: spacing.xs),
            Text(
              'Graph Extraction: $graphSummary',
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
            ),
          ],
        );

        final actions = Wrap(
          spacing: spacing.md,
          runSpacing: spacing.sm,
          children: [
            OutlinedButton.icon(
              onPressed: _isSending ? null : _openModelConfigPage,
              icon: const Icon(Icons.tune),
              label: const Text('模型配置'),
            ),
            FilledButton.icon(
              onPressed: _isSending ? null : _sendDiscussion,
              icon: const Icon(Icons.send_outlined),
              label: const Text('Send'),
            ),
          ],
        );

        if (constraints.maxWidth >= 760) {
          return Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(child: summary),
              SizedBox(width: spacing.md),
              actions,
            ],
          );
        }

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            summary,
            SizedBox(height: spacing.md),
            actions,
          ],
        );
      },
    );
  }

  List<Widget> _buildCommandButtons(RpChapterSnapshot snapshot) {
    final phase = snapshot.chapter.phase;
    final pendingSegment = _selectedPendingSegment(snapshot);
    final outlineDraft = snapshot.latestOutlineDraft;
    final buttons = <Widget>[];

    if (phase == 'outline_drafting') {
      buttons.add(
        FilledButton(
          onPressed: _isSending
              ? null
              : () => _runStreamingCommand('generate_outline'),
          child: const Text('Generate Outline'),
        ),
      );
    }
    if (outlineDraft != null && phase == 'outline_review') {
      buttons.add(
        FilledButton.tonal(
          onPressed: _isSending
              ? null
              : () => _runImmediateCommand(
                  'accept_outline',
                  targetArtifactId: outlineDraft.artifactId,
                ),
          child: const Text('Accept Outline'),
        ),
      );
    }
    if (phase == 'segment_drafting' || phase == 'chapter_review') {
      buttons.add(
        FilledButton(
          onPressed: _isSending
              ? null
              : () => _runStreamingCommand('write_next_segment'),
          child: const Text('Write Next Segment'),
        ),
      );
    }
    if (pendingSegment != null && phase == 'segment_review') {
      buttons.add(
        OutlinedButton(
          onPressed: _isSending
              ? null
              : () => _runStreamingCommand(
                  'rewrite_pending_segment',
                  targetArtifactId: pendingSegment.artifactId,
                ),
          child: const Text('Rewrite'),
        ),
      );
      buttons.add(
        FilledButton.tonal(
          onPressed: _isSending
              ? null
              : () => _runImmediateCommand(
                  'accept_pending_segment',
                  targetArtifactId: pendingSegment.artifactId,
                ),
          child: const Text('Accept Segment'),
        ),
      );
    }
    if ((phase == 'segment_drafting' || phase == 'chapter_review') &&
        snapshot.acceptedSegmentArtifacts.isNotEmpty) {
      buttons.add(
        OutlinedButton.icon(
          onPressed: _isSending
              ? null
              : () => _runImmediateCommand('complete_chapter'),
          icon: const Icon(Icons.flag_outlined),
          label: const Text('Complete Chapter'),
        ),
      );
    }
    return buttons;
  }

  Widget _buildArtifactCard(
    RpStoryArtifact artifact, {
    bool isPrimary = false,
    bool isPending = false,
  }) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    return Container(
      padding: EdgeInsets.all(spacing.lg),
      decoration: BoxDecoration(
        color: isPrimary
            ? Theme.of(context).colorScheme.primary.withValues(alpha: 0.06)
            : colors.surface2,
        borderRadius: BorderRadius.circular(context.owuiRadius.r3xl),
        border: Border.all(
          color: isPending
              ? Theme.of(context).colorScheme.primary.withValues(alpha: 0.34)
              : colors.borderSubtle,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '${artifact.artifactKind} · ${artifact.status} · r${artifact.revision}',
            style: Theme.of(
              context,
            ).textTheme.labelLarge?.copyWith(color: colors.textSecondary),
          ),
          SizedBox(height: spacing.sm),
          SelectableText(
            artifact.contentText,
            style: Theme.of(context).textTheme.bodyLarge?.copyWith(height: 1.6),
          ),
        ],
      ),
    );
  }

  Widget _buildDiscussionEntry(RpStoryDiscussionEntry entry) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    final isUser = entry.role == 'user';
    final isSystem = entry.role == 'system';
    return Container(
      margin: EdgeInsets.only(bottom: spacing.md),
      padding: EdgeInsets.all(spacing.md),
      decoration: BoxDecoration(
        color: isUser
            ? Theme.of(context).colorScheme.primary.withValues(alpha: 0.08)
            : (isSystem ? colors.surface2 : colors.surfaceCard),
        borderRadius: BorderRadius.circular(context.owuiRadius.rXl),
        border: Border.all(color: colors.borderSubtle),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(switch (entry.role) {
            'user' => 'You',
            'system' => 'System',
            _ => 'Story Runtime',
          }, style: Theme.of(context).textTheme.titleSmall),
          SizedBox(height: spacing.sm),
          SelectableText(entry.contentText),
        ],
      ),
    );
  }

  Widget _buildStreamingCard() {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    return Container(
      padding: EdgeInsets.all(spacing.lg),
      decoration: BoxDecoration(
        color: colors.surface2,
        borderRadius: BorderRadius.circular(context.owuiRadius.r3xl),
        border: Border.all(color: colors.borderSubtle),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Streaming · ${_streamingCommandKind ?? 'story'}',
            style: Theme.of(
              context,
            ).textTheme.labelLarge?.copyWith(color: colors.textSecondary),
          ),
          if (_streamingThinking.isNotEmpty) ...[
            SizedBox(height: spacing.sm),
            Text(
              _streamingThinking,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: colors.textSecondary,
                fontStyle: FontStyle.italic,
              ),
            ),
          ],
          if (_streamingText.isNotEmpty) ...[
            SizedBox(height: spacing.sm),
            SelectableText(_streamingText),
          ],
          SizedBox(height: spacing.md),
          const LinearProgressIndicator(minHeight: 2),
        ],
      ),
    );
  }

  Widget _emptyPaneNote(String text) {
    return Text(
      text,
      style: Theme.of(
        context,
      ).textTheme.bodyMedium?.copyWith(color: context.owuiColors.textSecondary),
    );
  }

  bool get _isStreamingLeftPane =>
      _isSending &&
      (_streamingCommandKind == 'generate_outline' ||
          _streamingCommandKind == 'write_next_segment' ||
          _streamingCommandKind == 'rewrite_pending_segment');

  bool get _isStreamingDiscussionPane =>
      _isSending && _streamingCommandKind == 'discuss_outline';
}
