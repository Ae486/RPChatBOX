import 'package:flutter/material.dart';

import '../chat_ui/owui/components/owui_app_bar.dart';
import '../chat_ui/owui/components/owui_card.dart';
import '../chat_ui/owui/components/owui_scaffold.dart';
import '../chat_ui/owui/components/owui_snack_bar.dart';
import '../chat_ui/owui/owui_tokens_ext.dart';
import '../main.dart';
import '../models/model_config.dart';
import '../models/provider_config.dart';

typedef RpAgentSelectionChanged =
    void Function({required String? providerId, required String? modelId});

typedef RpRetrievalConfigPersist =
    Future<void> Function({
      required String? embeddingProviderId,
      required String? embeddingModelId,
      required String? rerankProviderId,
      required String? rerankModelId,
      required String? graphExtractionProviderId,
      required String? graphExtractionModelId,
    });

class RpModelConfigPage extends StatefulWidget {
  final String title;
  final String subtitle;
  final String agentSectionTitle;
  final String agentSectionDescription;
  final String retrievalSectionTitle;
  final String retrievalSectionDescription;
  final List<ProviderConfig> agentProviders;
  final List<ModelConfig> Function(String providerId) agentModelsForProvider;
  final String? initialAgentProviderId;
  final String? initialAgentModelId;
  final RpAgentSelectionChanged onAgentSelectionChanged;
  final String? agentEmptyHint;
  final List<String> retrievalEmbeddingProviderIds;
  final List<ModelConfig> Function(String providerId)
  retrievalEmbeddingModelsForProvider;
  final List<String> retrievalRerankProviderIds;
  final List<ModelConfig> Function(String providerId)
  retrievalRerankModelsForProvider;
  final List<String> retrievalGraphExtractionProviderIds;
  final List<ModelConfig> Function(String providerId)
  retrievalGraphExtractionModelsForProvider;
  final String? initialRetrievalEmbeddingProviderId;
  final String? initialRetrievalEmbeddingModelId;
  final String? initialRetrievalRerankProviderId;
  final String? initialRetrievalRerankModelId;
  final String? initialRetrievalGraphExtractionProviderId;
  final String? initialRetrievalGraphExtractionModelId;
  final RpRetrievalConfigPersist onPersistRetrievalConfig;
  final String? retrievalSecondaryActionLabel;
  final Future<void> Function()? onRetrievalSecondaryAction;
  final bool retrievalSecondaryActionClearsSelections;
  final String? embeddingEmptyHint;
  final String? rerankEmptyHint;
  final String? graphExtractionEmptyHint;

  const RpModelConfigPage({
    super.key,
    required this.title,
    required this.subtitle,
    required this.agentSectionTitle,
    required this.agentSectionDescription,
    required this.retrievalSectionTitle,
    required this.retrievalSectionDescription,
    required this.agentProviders,
    required this.agentModelsForProvider,
    required this.initialAgentProviderId,
    required this.initialAgentModelId,
    required this.onAgentSelectionChanged,
    required this.retrievalEmbeddingProviderIds,
    required this.retrievalEmbeddingModelsForProvider,
    required this.retrievalRerankProviderIds,
    required this.retrievalRerankModelsForProvider,
    required this.retrievalGraphExtractionProviderIds,
    required this.retrievalGraphExtractionModelsForProvider,
    required this.initialRetrievalEmbeddingProviderId,
    required this.initialRetrievalEmbeddingModelId,
    required this.initialRetrievalRerankProviderId,
    required this.initialRetrievalRerankModelId,
    required this.initialRetrievalGraphExtractionProviderId,
    required this.initialRetrievalGraphExtractionModelId,
    required this.onPersistRetrievalConfig,
    this.agentEmptyHint,
    this.retrievalSecondaryActionLabel,
    this.onRetrievalSecondaryAction,
    this.retrievalSecondaryActionClearsSelections = false,
    this.embeddingEmptyHint,
    this.rerankEmptyHint,
    this.graphExtractionEmptyHint,
  });

  @override
  State<RpModelConfigPage> createState() => _RpModelConfigPageState();
}

class _RpModelConfigPageState extends State<RpModelConfigPage> {
  String? _selectedAgentProviderId;
  String? _selectedAgentModelId;
  String? _selectedRetrievalEmbeddingProviderId;
  String? _selectedRetrievalEmbeddingModelId;
  String? _selectedRetrievalRerankProviderId;
  String? _selectedRetrievalRerankModelId;
  String? _selectedRetrievalGraphExtractionProviderId;
  String? _selectedRetrievalGraphExtractionModelId;
  bool _isPersistingRetrievalConfig = false;

  @override
  void initState() {
    super.initState();
    _selectedAgentProviderId = widget.initialAgentProviderId;
    _selectedAgentModelId = widget.initialAgentModelId;
    _selectedRetrievalEmbeddingProviderId =
        widget.initialRetrievalEmbeddingProviderId;
    _selectedRetrievalEmbeddingModelId =
        widget.initialRetrievalEmbeddingModelId;
    _selectedRetrievalRerankProviderId =
        widget.initialRetrievalRerankProviderId;
    _selectedRetrievalRerankModelId = widget.initialRetrievalRerankModelId;
    _selectedRetrievalGraphExtractionProviderId =
        widget.initialRetrievalGraphExtractionProviderId;
    _selectedRetrievalGraphExtractionModelId =
        widget.initialRetrievalGraphExtractionModelId;
    _normalizeAgentSelection();
  }

  void _normalizeAgentSelection() {
    final providers = widget.agentProviders;
    if (providers.isEmpty) {
      _selectedAgentProviderId = null;
      _selectedAgentModelId = null;
      return;
    }
    final providerId =
        providers.any((item) => item.id == _selectedAgentProviderId)
        ? _selectedAgentProviderId!
        : providers.first.id;
    final models = widget.agentModelsForProvider(providerId);
    final modelId = models.any((item) => item.id == _selectedAgentModelId)
        ? _selectedAgentModelId
        : (models.isNotEmpty ? models.first.id : null);
    _selectedAgentProviderId = providerId;
    _selectedAgentModelId = modelId;
  }

  void _handleAgentProviderChanged(String? providerId) {
    final models = providerId == null
        ? const <ModelConfig>[]
        : widget.agentModelsForProvider(providerId);
    final modelId = models.isEmpty ? null : models.first.id;
    setState(() {
      _selectedAgentProviderId = providerId;
      _selectedAgentModelId = modelId;
    });
    widget.onAgentSelectionChanged(providerId: providerId, modelId: modelId);
  }

  void _handleAgentModelChanged(String? modelId) {
    setState(() {
      _selectedAgentModelId = modelId;
    });
    widget.onAgentSelectionChanged(
      providerId: _selectedAgentProviderId,
      modelId: modelId,
    );
  }

  Future<void> _persistRetrievalConfig({
    required String? embeddingProviderId,
    required String? embeddingModelId,
    required String? rerankProviderId,
    required String? rerankModelId,
    required String? graphExtractionProviderId,
    required String? graphExtractionModelId,
  }) async {
    if (_isPersistingRetrievalConfig) return;
    final previous = (
      embeddingProviderId: _selectedRetrievalEmbeddingProviderId,
      embeddingModelId: _selectedRetrievalEmbeddingModelId,
      rerankProviderId: _selectedRetrievalRerankProviderId,
      rerankModelId: _selectedRetrievalRerankModelId,
      graphExtractionProviderId: _selectedRetrievalGraphExtractionProviderId,
      graphExtractionModelId: _selectedRetrievalGraphExtractionModelId,
    );

    setState(() {
      _isPersistingRetrievalConfig = true;
      _selectedRetrievalEmbeddingProviderId = embeddingProviderId;
      _selectedRetrievalEmbeddingModelId = embeddingModelId;
      _selectedRetrievalRerankProviderId = rerankProviderId;
      _selectedRetrievalRerankModelId = rerankModelId;
      _selectedRetrievalGraphExtractionProviderId = graphExtractionProviderId;
      _selectedRetrievalGraphExtractionModelId = graphExtractionModelId;
    });

    try {
      await widget.onPersistRetrievalConfig(
        embeddingProviderId: embeddingProviderId,
        embeddingModelId: embeddingModelId,
        rerankProviderId: rerankProviderId,
        rerankModelId: rerankModelId,
        graphExtractionProviderId: graphExtractionProviderId,
        graphExtractionModelId: graphExtractionModelId,
      );
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _selectedRetrievalEmbeddingProviderId = previous.embeddingProviderId;
        _selectedRetrievalEmbeddingModelId = previous.embeddingModelId;
        _selectedRetrievalRerankProviderId = previous.rerankProviderId;
        _selectedRetrievalRerankModelId = previous.rerankModelId;
        _selectedRetrievalGraphExtractionProviderId =
            previous.graphExtractionProviderId;
        _selectedRetrievalGraphExtractionModelId =
            previous.graphExtractionModelId;
      });
      OwuiSnackBars.error(context, message: '更新 retrieval 模型配置失败: $e');
    } finally {
      if (mounted) {
        setState(() {
          _isPersistingRetrievalConfig = false;
        });
      }
    }
  }

  Future<void> _runRetrievalSecondaryAction() async {
    final action = widget.onRetrievalSecondaryAction;
    if (action == null || _isPersistingRetrievalConfig) return;
    final previous = (
      embeddingProviderId: _selectedRetrievalEmbeddingProviderId,
      embeddingModelId: _selectedRetrievalEmbeddingModelId,
      rerankProviderId: _selectedRetrievalRerankProviderId,
      rerankModelId: _selectedRetrievalRerankModelId,
      graphExtractionProviderId: _selectedRetrievalGraphExtractionProviderId,
      graphExtractionModelId: _selectedRetrievalGraphExtractionModelId,
    );

    setState(() {
      _isPersistingRetrievalConfig = true;
      if (widget.retrievalSecondaryActionClearsSelections) {
        _selectedRetrievalEmbeddingProviderId = null;
        _selectedRetrievalEmbeddingModelId = null;
        _selectedRetrievalRerankProviderId = null;
        _selectedRetrievalRerankModelId = null;
        _selectedRetrievalGraphExtractionProviderId = null;
        _selectedRetrievalGraphExtractionModelId = null;
      }
    });

    try {
      await action();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _selectedRetrievalEmbeddingProviderId = previous.embeddingProviderId;
        _selectedRetrievalEmbeddingModelId = previous.embeddingModelId;
        _selectedRetrievalRerankProviderId = previous.rerankProviderId;
        _selectedRetrievalRerankModelId = previous.rerankModelId;
        _selectedRetrievalGraphExtractionProviderId =
            previous.graphExtractionProviderId;
        _selectedRetrievalGraphExtractionModelId =
            previous.graphExtractionModelId;
      });
      OwuiSnackBars.error(context, message: '更新 retrieval 默认配置失败: $e');
    } finally {
      if (mounted) {
        setState(() {
          _isPersistingRetrievalConfig = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;

    return OwuiScaffold(
      appBar: OwuiAppBar(
        leading: IconButton(
          tooltip: '返回',
          icon: const Icon(Icons.arrow_back),
          onPressed: () => Navigator.of(context).maybePop(),
        ),
        title: Text(widget.title),
      ),
      body: ListView(
        padding: EdgeInsets.all(spacing.lg),
        children: [
          OwuiCard(
            padding: EdgeInsets.all(spacing.lg),
            child: Text(
              widget.subtitle,
              style: Theme.of(
                context,
              ).textTheme.bodyMedium?.copyWith(color: colors.textSecondary),
            ),
          ),
          SizedBox(height: spacing.lg),
          OwuiCard(
            padding: EdgeInsets.all(spacing.lg),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  widget.agentSectionTitle,
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                SizedBox(height: spacing.xs),
                Text(
                  widget.agentSectionDescription,
                  style: Theme.of(
                    context,
                  ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
                ),
                SizedBox(height: spacing.md),
                DropdownButtonFormField<String>(
                  initialValue: _selectedAgentProviderId,
                  decoration: const InputDecoration(
                    labelText: 'Agent Provider',
                  ),
                  items: widget.agentProviders
                      .map(
                        (provider) => DropdownMenuItem<String>(
                          value: provider.id,
                          child: Text(provider.name),
                        ),
                      )
                      .toList(),
                  onChanged: widget.agentProviders.isEmpty
                      ? null
                      : _handleAgentProviderChanged,
                ),
                SizedBox(height: spacing.md),
                DropdownButtonFormField<String>(
                  initialValue: _selectedAgentModelId,
                  decoration: const InputDecoration(labelText: 'Agent Model'),
                  items:
                      (_selectedAgentProviderId == null
                              ? const <ModelConfig>[]
                              : widget.agentModelsForProvider(
                                  _selectedAgentProviderId!,
                                ))
                          .map(
                            (model) => DropdownMenuItem<String>(
                              value: model.id,
                              child: Text(model.displayName),
                            ),
                          )
                          .toList(),
                  onChanged: _selectedAgentProviderId == null
                      ? null
                      : _handleAgentModelChanged,
                ),
                if (widget.agentEmptyHint != null &&
                    widget.agentEmptyHint!.trim().isNotEmpty &&
                    widget.agentProviders.isEmpty) ...[
                  SizedBox(height: spacing.sm),
                  Text(
                    widget.agentEmptyHint!,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: colors.textSecondary,
                    ),
                  ),
                ],
              ],
            ),
          ),
          SizedBox(height: spacing.lg),
          OwuiCard(
            padding: EdgeInsets.all(spacing.lg),
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
                            widget.retrievalSectionTitle,
                            style: Theme.of(context).textTheme.titleLarge,
                          ),
                          SizedBox(height: spacing.xs),
                          Text(
                            widget.retrievalSectionDescription,
                            style: Theme.of(context).textTheme.bodySmall
                                ?.copyWith(color: colors.textSecondary),
                          ),
                        ],
                      ),
                    ),
                    if (widget.retrievalSecondaryActionLabel != null &&
                        widget.onRetrievalSecondaryAction != null)
                      TextButton.icon(
                        onPressed: _isPersistingRetrievalConfig
                            ? null
                            : _runRetrievalSecondaryAction,
                        icon: const Icon(Icons.restart_alt),
                        label: Text(widget.retrievalSecondaryActionLabel!),
                      ),
                  ],
                ),
                if (_isPersistingRetrievalConfig) ...[
                  SizedBox(height: spacing.md),
                  const LinearProgressIndicator(minHeight: 2),
                ],
                SizedBox(height: spacing.md),
                LayoutBuilder(
                  builder: (context, constraints) {
                    final fieldWidth = constraints.maxWidth >= 720
                        ? (constraints.maxWidth - spacing.md) / 2
                        : constraints.maxWidth;
                    return Wrap(
                      spacing: spacing.md,
                      runSpacing: spacing.md,
                      children: [
                        SizedBox(
                          width: fieldWidth,
                          child: DropdownButtonFormField<String>(
                            initialValue: _selectedRetrievalEmbeddingProviderId,
                            decoration: const InputDecoration(
                              labelText: 'Embedding Provider',
                            ),
                            items: widget.retrievalEmbeddingProviderIds
                                .map(
                                  (providerId) => DropdownMenuItem<String>(
                                    value: providerId,
                                    child: Text(
                                      globalModelServiceManager
                                              .getProvider(providerId)
                                              ?.name ??
                                          providerId,
                                    ),
                                  ),
                                )
                                .toList(),
                            onChanged: _isPersistingRetrievalConfig
                                ? null
                                : (value) async {
                                    final models = value == null
                                        ? const <ModelConfig>[]
                                        : widget
                                              .retrievalEmbeddingModelsForProvider(
                                                value,
                                              );
                                    final nextModelId = models.isEmpty
                                        ? null
                                        : models.first.id;
                                    await _persistRetrievalConfig(
                                      embeddingProviderId: value,
                                      embeddingModelId: nextModelId,
                                      rerankProviderId:
                                          _selectedRetrievalRerankProviderId,
                                      rerankModelId:
                                          _selectedRetrievalRerankModelId,
                                      graphExtractionProviderId:
                                          _selectedRetrievalGraphExtractionProviderId,
                                      graphExtractionModelId:
                                          _selectedRetrievalGraphExtractionModelId,
                                    );
                                  },
                          ),
                        ),
                        SizedBox(
                          width: fieldWidth,
                          child: DropdownButtonFormField<String>(
                            initialValue: _selectedRetrievalEmbeddingModelId,
                            decoration: const InputDecoration(
                              labelText: 'Embedding Model',
                            ),
                            items:
                                (_selectedRetrievalEmbeddingProviderId == null
                                        ? const <ModelConfig>[]
                                        : widget.retrievalEmbeddingModelsForProvider(
                                            _selectedRetrievalEmbeddingProviderId!,
                                          ))
                                    .map(
                                      (model) => DropdownMenuItem<String>(
                                        value: model.id,
                                        child: Text(model.displayName),
                                      ),
                                    )
                                    .toList(),
                            onChanged:
                                _selectedRetrievalEmbeddingProviderId == null ||
                                    _isPersistingRetrievalConfig
                                ? null
                                : (value) async {
                                    await _persistRetrievalConfig(
                                      embeddingProviderId:
                                          _selectedRetrievalEmbeddingProviderId,
                                      embeddingModelId: value,
                                      rerankProviderId:
                                          _selectedRetrievalRerankProviderId,
                                      rerankModelId:
                                          _selectedRetrievalRerankModelId,
                                      graphExtractionProviderId:
                                          _selectedRetrievalGraphExtractionProviderId,
                                      graphExtractionModelId:
                                          _selectedRetrievalGraphExtractionModelId,
                                    );
                                  },
                          ),
                        ),
                        SizedBox(
                          width: fieldWidth,
                          child: DropdownButtonFormField<String>(
                            initialValue: _selectedRetrievalRerankProviderId,
                            decoration: const InputDecoration(
                              labelText: 'Rerank Provider',
                            ),
                            items: widget.retrievalRerankProviderIds
                                .map(
                                  (providerId) => DropdownMenuItem<String>(
                                    value: providerId,
                                    child: Text(
                                      globalModelServiceManager
                                              .getProvider(providerId)
                                              ?.name ??
                                          providerId,
                                    ),
                                  ),
                                )
                                .toList(),
                            onChanged: _isPersistingRetrievalConfig
                                ? null
                                : (value) async {
                                    final models = value == null
                                        ? const <ModelConfig>[]
                                        : widget
                                              .retrievalRerankModelsForProvider(
                                                value,
                                              );
                                    final nextModelId = models.isEmpty
                                        ? null
                                        : models.first.id;
                                    await _persistRetrievalConfig(
                                      embeddingProviderId:
                                          _selectedRetrievalEmbeddingProviderId,
                                      embeddingModelId:
                                          _selectedRetrievalEmbeddingModelId,
                                      rerankProviderId: value,
                                      rerankModelId: nextModelId,
                                      graphExtractionProviderId:
                                          _selectedRetrievalGraphExtractionProviderId,
                                      graphExtractionModelId:
                                          _selectedRetrievalGraphExtractionModelId,
                                    );
                                  },
                          ),
                        ),
                        SizedBox(
                          width: fieldWidth,
                          child: DropdownButtonFormField<String>(
                            initialValue: _selectedRetrievalRerankModelId,
                            decoration: const InputDecoration(
                              labelText: 'Rerank Model',
                            ),
                            items:
                                (_selectedRetrievalRerankProviderId == null
                                        ? const <ModelConfig>[]
                                        : widget.retrievalRerankModelsForProvider(
                                            _selectedRetrievalRerankProviderId!,
                                          ))
                                    .map(
                                      (model) => DropdownMenuItem<String>(
                                        value: model.id,
                                        child: Text(model.displayName),
                                      ),
                                    )
                                    .toList(),
                            onChanged:
                                _selectedRetrievalRerankProviderId == null ||
                                    _isPersistingRetrievalConfig
                                ? null
                                : (value) async {
                                    await _persistRetrievalConfig(
                                      embeddingProviderId:
                                          _selectedRetrievalEmbeddingProviderId,
                                      embeddingModelId:
                                          _selectedRetrievalEmbeddingModelId,
                                      rerankProviderId:
                                          _selectedRetrievalRerankProviderId,
                                      rerankModelId: value,
                                      graphExtractionProviderId:
                                          _selectedRetrievalGraphExtractionProviderId,
                                      graphExtractionModelId:
                                          _selectedRetrievalGraphExtractionModelId,
                                    );
                                  },
                          ),
                        ),
                        SizedBox(
                          width: fieldWidth,
                          child: DropdownButtonFormField<String>(
                            initialValue:
                                _selectedRetrievalGraphExtractionProviderId,
                            decoration: const InputDecoration(
                              labelText: 'Graph Extraction Provider',
                            ),
                            items: widget.retrievalGraphExtractionProviderIds
                                .map(
                                  (providerId) => DropdownMenuItem<String>(
                                    value: providerId,
                                    child: Text(
                                      globalModelServiceManager
                                              .getProvider(providerId)
                                              ?.name ??
                                          providerId,
                                    ),
                                  ),
                                )
                                .toList(),
                            onChanged: _isPersistingRetrievalConfig
                                ? null
                                : (value) async {
                                    final models = value == null
                                        ? const <ModelConfig>[]
                                        : widget
                                              .retrievalGraphExtractionModelsForProvider(
                                                value,
                                              );
                                    final nextModelId = models.isEmpty
                                        ? null
                                        : models.first.id;
                                    await _persistRetrievalConfig(
                                      embeddingProviderId:
                                          _selectedRetrievalEmbeddingProviderId,
                                      embeddingModelId:
                                          _selectedRetrievalEmbeddingModelId,
                                      rerankProviderId:
                                          _selectedRetrievalRerankProviderId,
                                      rerankModelId:
                                          _selectedRetrievalRerankModelId,
                                      graphExtractionProviderId: value,
                                      graphExtractionModelId: nextModelId,
                                    );
                                  },
                          ),
                        ),
                        SizedBox(
                          width: fieldWidth,
                          child: DropdownButtonFormField<String>(
                            initialValue:
                                _selectedRetrievalGraphExtractionModelId,
                            decoration: const InputDecoration(
                              labelText: 'Graph Extraction Model',
                            ),
                            items:
                                (_selectedRetrievalGraphExtractionProviderId ==
                                            null
                                        ? const <ModelConfig>[]
                                        : widget.retrievalGraphExtractionModelsForProvider(
                                            _selectedRetrievalGraphExtractionProviderId!,
                                          ))
                                    .map(
                                      (model) => DropdownMenuItem<String>(
                                        value: model.id,
                                        child: Text(model.displayName),
                                      ),
                                    )
                                    .toList(),
                            onChanged:
                                _selectedRetrievalGraphExtractionProviderId ==
                                        null ||
                                    _isPersistingRetrievalConfig
                                ? null
                                : (value) async {
                                    await _persistRetrievalConfig(
                                      embeddingProviderId:
                                          _selectedRetrievalEmbeddingProviderId,
                                      embeddingModelId:
                                          _selectedRetrievalEmbeddingModelId,
                                      rerankProviderId:
                                          _selectedRetrievalRerankProviderId,
                                      rerankModelId:
                                          _selectedRetrievalRerankModelId,
                                      graphExtractionProviderId:
                                          _selectedRetrievalGraphExtractionProviderId,
                                      graphExtractionModelId: value,
                                    );
                                  },
                          ),
                        ),
                      ],
                    );
                  },
                ),
                if (widget.embeddingEmptyHint != null &&
                    widget.embeddingEmptyHint!.trim().isNotEmpty &&
                    widget.retrievalEmbeddingProviderIds.isEmpty) ...[
                  SizedBox(height: spacing.sm),
                  Text(
                    widget.embeddingEmptyHint!,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: colors.textSecondary,
                    ),
                  ),
                ],
                if (widget.rerankEmptyHint != null &&
                    widget.rerankEmptyHint!.trim().isNotEmpty &&
                    widget.retrievalRerankProviderIds.isEmpty) ...[
                  SizedBox(height: spacing.sm),
                  Text(
                    widget.rerankEmptyHint!,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: colors.textSecondary,
                    ),
                  ),
                ],
                if (widget.graphExtractionEmptyHint != null &&
                    widget.graphExtractionEmptyHint!.trim().isNotEmpty &&
                    widget.retrievalGraphExtractionProviderIds.isEmpty) ...[
                  SizedBox(height: spacing.sm),
                  Text(
                    widget.graphExtractionEmptyHint!,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: colors.textSecondary,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
