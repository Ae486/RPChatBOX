import 'dart:convert';

import 'package:flutter/material.dart';

import '../chat_ui/owui/components/owui_card.dart';
import '../chat_ui/owui/owui_tokens_ext.dart';
import '../models/story_runtime.dart';
import '../services/backend_story_service.dart';

class StoryMemoryPanel extends StatefulWidget {
  final BackendStoryService service;
  final String sessionId;
  final int chapterIndex;
  final String mode;
  final String? preferredBranchHeadId;
  final String? preferredTurnId;
  final String? preferredRuntimeProfileSnapshotId;

  const StoryMemoryPanel({
    super.key,
    required this.service,
    required this.sessionId,
    required this.chapterIndex,
    required this.mode,
    required this.preferredBranchHeadId,
    required this.preferredTurnId,
    required this.preferredRuntimeProfileSnapshotId,
  });

  @override
  State<StoryMemoryPanel> createState() => _StoryMemoryPanelState();
}

class _StoryMemoryPanelState extends State<StoryMemoryPanel> {
  RpMemoryInspection? _memory;
  RpRuntimeInspection? _runtimeInspection;
  RpMemoryActionResponse? _lastAction;
  String _selectedLayer = _allFilter;
  String _selectedDomain = _allFilter;
  bool _isLoading = true;
  bool _isActing = false;
  String? _fatalError;

  static const _allFilter = '__all__';
  static const _actor = 'frontend.memory_panel';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load({
    RpMemoryActionResponse? actionRefresh,
    bool preserveAction = false,
  }) async {
    setState(() {
      _isLoading = true;
      _fatalError = null;
      if (!preserveAction) _lastAction = null;
    });

    try {
      final runtimeRefresh = actionRefresh?.runtimeInspectRefresh;
      final runtimeParams = _mapOrEmpty(runtimeRefresh?['query_params']);
      final runtimeInspection = await widget.service.getRuntimeInspection(
        sessionId: widget.sessionId,
        branchHeadId:
            _stringOrNull(runtimeParams['branch_head_id']) ??
            widget.preferredBranchHeadId,
        turnId:
            _stringOrNull(runtimeParams['turn_id']) ?? widget.preferredTurnId,
        targetChapterIndex: widget.chapterIndex,
        limit: 12,
      );

      final memoryRefresh = actionRefresh?.memoryInspectionRefresh;
      final memoryParams = _mapOrEmpty(memoryRefresh?['query_params']);
      final branchHeadId =
          _stringOrNull(memoryParams['branch_head_id']) ??
          runtimeInspection.activeBranchHeadId ??
          widget.preferredBranchHeadId;
      final turnId =
          _stringOrNull(memoryParams['turn_id']) ??
          runtimeInspection.selection.selectedTurnId ??
          widget.preferredTurnId;
      final snapshotId =
          _stringOrNull(memoryParams['runtime_profile_snapshot_id']) ??
          runtimeInspection.activeSnapshotId ??
          widget.preferredRuntimeProfileSnapshotId;

      if (branchHeadId == null || turnId == null || snapshotId == null) {
        throw StateError(
          'memory_identity_incomplete: branch=$branchHeadId turn=$turnId snapshot=$snapshotId',
        );
      }

      final memory = await widget.service.getMemoryInspection(
        sessionId: widget.sessionId,
        branchHeadId: branchHeadId,
        turnId: turnId,
        runtimeProfileSnapshotId: snapshotId,
      );

      if (!mounted) return;
      setState(() {
        _runtimeInspection = runtimeInspection;
        _memory = memory;
        if (preserveAction && actionRefresh != null) {
          _lastAction = actionRefresh;
        }
        _isLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _fatalError = 'Memory 加载失败: $e';
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final spacing = context.owuiSpacing;
    return SafeArea(
      top: false,
      child: FractionallySizedBox(
        heightFactor: 0.94,
        child: Padding(
          padding: EdgeInsets.fromLTRB(spacing.lg, 0, spacing.lg, spacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _buildHeader(),
              SizedBox(height: spacing.md),
              if (_isLoading)
                const Expanded(
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (_fatalError != null)
                Expanded(child: _buildErrorState())
              else
                Expanded(child: _buildLoadedState()),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHeader() {
    final spacing = context.owuiSpacing;
    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Memory', style: Theme.of(context).textTheme.titleLarge),
              SizedBox(height: spacing.xs),
              Text(
                'Core / Projection / Workspace / Recall / Archival',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: context.owuiColors.textSecondary,
                ),
              ),
            ],
          ),
        ),
        IconButton(
          tooltip: '刷新 Memory',
          onPressed: _isLoading || _isActing ? null : () => _load(),
          icon: const Icon(Icons.refresh),
        ),
      ],
    );
  }

  Widget _buildErrorState() {
    final spacing = context.owuiSpacing;
    return Center(
      child: OwuiCard(
        padding: EdgeInsets.all(spacing.lg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, size: 32),
            SizedBox(height: spacing.md),
            Text(_fatalError ?? 'Memory 暂不可用'),
            SizedBox(height: spacing.md),
            FilledButton.icon(
              onPressed: _load,
              icon: const Icon(Icons.refresh),
              label: const Text('重试'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildLoadedState() {
    final memory = _memory;
    if (memory == null) {
      return Center(
        child: Text(
          'Memory 暂不可用',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
      );
    }

    final spacing = context.owuiSpacing;
    final blocks = _filteredBlocks(memory);
    return ListView(
      children: [
        _buildIdentityCard(memory),
        SizedBox(height: spacing.md),
        _buildFilters(memory),
        if (_lastAction != null) ...[
          SizedBox(height: spacing.md),
          _buildActionReceipt(_lastAction!),
        ],
        SizedBox(height: spacing.md),
        if (blocks.isEmpty)
          _buildEmptyState()
        else
          for (final block in blocks) ...[
            _buildBlockCard(block),
            SizedBox(height: spacing.md),
          ],
      ],
    );
  }

  Widget _buildIdentityCard(RpMemoryInspection memory) {
    final spacing = context.owuiSpacing;
    final runtime = _runtimeInspection;
    return OwuiCard(
      padding: EdgeInsets.all(spacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: spacing.sm,
            runSpacing: spacing.sm,
            children: [
              _metricChip('schema', memory.schemaVersion ?? 'unknown'),
              _metricChip('mode', widget.mode),
              _metricChip('chapter', widget.chapterIndex.toString()),
              _metricChip('blocks', memory.blocks.length.toString()),
            ],
          ),
          SizedBox(height: spacing.md),
          _detailRow(
            'active branch',
            _displayValue(memory.activeBranchHeadId),
            monospace: true,
          ),
          _detailRow(
            'cutoff turn',
            _displayValue(memory.cutoffTurnId),
            monospace: true,
          ),
          _detailRow(
            'snapshot',
            _displayValue(memory.runtimeProfileSnapshotId),
            monospace: true,
          ),
          _detailRow(
            'runtime selected turn',
            _displayValue(runtime?.selection.selectedTurnId),
            monospace: true,
          ),
        ],
      ),
    );
  }

  Widget _buildFilters(RpMemoryInspection memory) {
    final spacing = context.owuiSpacing;
    final layers = [
      _allFilter,
      ...memory.blocks.map((block) => block.layer).toSet().toList()..sort(),
    ];
    final domains = [
      _allFilter,
      ...memory.blocks.map((block) => block.domain).toSet().toList()..sort(),
    ];
    return OwuiCard(
      padding: EdgeInsets.all(spacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _filterRow(
            label: 'Layer',
            values: layers,
            selected: _selectedLayer,
            onSelected: (value) => setState(() => _selectedLayer = value),
          ),
          SizedBox(height: spacing.sm),
          _filterRow(
            label: 'Domain',
            values: domains,
            selected: _selectedDomain,
            onSelected: (value) => setState(() => _selectedDomain = value),
          ),
        ],
      ),
    );
  }

  Widget _filterRow({
    required String label,
    required List<String> values,
    required String selected,
    required ValueChanged<String> onSelected,
  }) {
    final spacing = context.owuiSpacing;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(width: 64, child: Text(label)),
        Expanded(
          child: Wrap(
            spacing: spacing.sm,
            runSpacing: spacing.xs,
            children: [
              for (final value in values)
                ChoiceChip(
                  label: Text(_filterLabel(value)),
                  selected: selected == value,
                  onSelected: (_) => onSelected(value),
                ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildActionReceipt(RpMemoryActionResponse receipt) {
    final spacing = context.owuiSpacing;
    return OwuiCard(
      padding: EdgeInsets.all(spacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('最近动作回执', style: Theme.of(context).textTheme.titleSmall),
          SizedBox(height: spacing.sm),
          _detailRow('action', _displayValue(receipt.action)),
          _detailRow('governed by', _displayValue(receipt.governedBy)),
          _detailRow(
            'affected refs',
            receipt.affectedRefs.isEmpty
                ? '当前不可用'
                : receipt.affectedRefs.join(', '),
            monospace: true,
          ),
        ],
      ),
    );
  }

  Widget _buildEmptyState() {
    return OwuiCard(
      padding: EdgeInsets.all(context.owuiSpacing.lg),
      child: const Text('当前筛选下没有 Memory block。'),
    );
  }

  Widget _buildBlockCard(RpMemoryBlockEnvelope block) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    return Container(
      decoration: BoxDecoration(
        color: colors.surfaceCard,
        borderRadius: BorderRadius.circular(context.owuiRadius.rLg),
        border: Border.all(color: colors.borderSubtle),
      ),
      child: ExpansionTile(
        tilePadding: EdgeInsets.symmetric(
          horizontal: spacing.lg,
          vertical: spacing.sm,
        ),
        childrenPadding: EdgeInsets.fromLTRB(
          spacing.lg,
          0,
          spacing.lg,
          spacing.lg,
        ),
        title: Text(
          block.blockId,
          style: Theme.of(
            context,
          ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
        ),
        subtitle: Padding(
          padding: EdgeInsets.only(top: spacing.xs),
          child: Wrap(
            spacing: spacing.sm,
            runSpacing: spacing.xs,
            children: [
              _metricChip('layer', block.layer),
              _metricChip('domain', block.domain),
              _metricChip('rev', block.revision?.toString() ?? 'n/a'),
              _metricChip('life', block.lifecycleState ?? 'n/a'),
            ],
          ),
        ),
        children: [
          _detailRow('scope', _displayValue(block.scope)),
          _detailRow(
            'visibility',
            _jsonPreview(block.visibility),
            monospace: true,
          ),
          _detailRow(
            'permission',
            _jsonPreview(block.permissionLevel),
            monospace: true,
          ),
          _detailRow(
            'validation',
            _jsonPreview(block.validationSummary),
            monospace: true,
          ),
          _detailRow(
            'entrypoints',
            _jsonPreview(block.entrypoints),
            monospace: true,
          ),
          _detailRow(
            'source refs',
            _jsonPreview(block.sourceRefs),
            monospace: true,
          ),
          SizedBox(height: spacing.md),
          _buildActionButtons(block),
          SizedBox(height: spacing.md),
          for (final entry in block.entries) ...[
            _buildEntryCard(block, entry),
            SizedBox(height: spacing.sm),
          ],
        ],
      ),
    );
  }

  Widget _buildEntryCard(
    RpMemoryBlockEnvelope block,
    RpMemoryEntryEnvelope entry,
  ) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(spacing.md),
      decoration: BoxDecoration(
        color: colors.surface2,
        borderRadius: BorderRadius.circular(context.owuiRadius.rLg),
        border: Border.all(color: colors.borderSubtle),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            entry.label ?? entry.entryId,
            style: Theme.of(context).textTheme.titleSmall,
          ),
          SizedBox(height: spacing.sm),
          _detailRow('entry id', entry.entryId, monospace: true),
          _detailRow('type', entry.entryType),
          _detailRow(
            'base revision',
            entry.baseRevision?.toString() ?? '当前不可用',
          ),
          _detailRow('conflict', entry.conflictState ?? 'n/a'),
          _detailRow(
            'allowed actions',
            _mergedActions(block, entry).join(', '),
            monospace: true,
          ),
          _detailRow(
            'validation errors',
            entry.validationErrors.isEmpty
                ? '无'
                : entry.validationErrors.join(', '),
          ),
          _detailRow(
            'source refs',
            _jsonPreview(entry.sourceRefs),
            monospace: true,
          ),
          SizedBox(height: spacing.sm),
          SelectableText(
            _jsonPreview(entry.currentValue),
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              fontFamily: 'monospace',
              color: colors.textSecondary,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildActionButtons(RpMemoryBlockEnvelope block) {
    final entry = block.entries.isEmpty ? null : block.entries.first;
    final actions = _mergedActions(block, entry);
    final spacing = context.owuiSpacing;
    final buttons = <Widget>[];

    if (entry != null && actions.contains('direct_core_edit')) {
      buttons.add(
        FilledButton.icon(
          onPressed: _isActing ? null : () => _openCoreEditDialog(block, entry),
          icon: const Icon(Icons.edit_outlined),
          label: const Text('Core edit'),
        ),
      );
    }

    for (final action in const ['recompute', 'invalidate', 'supersede']) {
      if (entry != null && actions.contains('review_recall:$action')) {
        buttons.add(
          OutlinedButton.icon(
            onPressed: _isActing
                ? null
                : () => _confirmRecallAction(block, entry, action),
            icon: const Icon(Icons.history_toggle_off),
            label: Text('Recall $action'),
          ),
        );
      }
    }

    if (entry != null && actions.contains('evolve_archival')) {
      buttons.add(
        OutlinedButton.icon(
          onPressed: _isActing
              ? null
              : () => _openArchivalEvolutionDialog(block, entry),
          icon: const Icon(Icons.auto_fix_high_outlined),
          label: const Text('Archival evolve'),
        ),
      );
    }

    if (buttons.isEmpty) {
      return Text(
        'No governed action',
        style: Theme.of(context).textTheme.bodySmall?.copyWith(
          color: context.owuiColors.textSecondary,
        ),
      );
    }
    return Wrap(spacing: spacing.sm, runSpacing: spacing.sm, children: buttons);
  }

  Future<void> _openCoreEditDialog(
    RpMemoryBlockEnvelope block,
    RpMemoryEntryEnvelope entry,
  ) async {
    final editableFields = entry.editableFields.isNotEmpty
        ? entry.editableFields
        : block.editableFields;
    if (editableFields.isEmpty) return;

    var selectedField = editableFields.first;
    final valueController = TextEditingController(
      text: _initialFieldValue(entry.currentValue, selectedField),
    );
    final reasonController = TextEditingController();
    try {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => StatefulBuilder(
          builder: (context, setDialogState) => AlertDialog(
            title: const Text('Core direct edit'),
            content: SizedBox(
              width: 520,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  DropdownButtonFormField<String>(
                    initialValue: selectedField,
                    items: [
                      for (final field in editableFields)
                        DropdownMenuItem(value: field, child: Text(field)),
                    ],
                    onChanged: (value) {
                      if (value == null) return;
                      setDialogState(() {
                        selectedField = value;
                        valueController.text = _initialFieldValue(
                          entry.currentValue,
                          selectedField,
                        );
                      });
                    },
                    decoration: const InputDecoration(labelText: 'field'),
                  ),
                  TextField(
                    controller: valueController,
                    minLines: 3,
                    maxLines: 8,
                    decoration: const InputDecoration(labelText: 'value'),
                  ),
                  TextField(
                    controller: reasonController,
                    decoration: const InputDecoration(labelText: 'reason'),
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(dialogContext).pop(false),
                child: const Text('取消'),
              ),
              FilledButton(
                onPressed: () => Navigator.of(dialogContext).pop(true),
                child: const Text('提交'),
              ),
            ],
          ),
        ),
      );
      if (confirmed != true) return;

      final targetRef = _objectRefFor(block, entry);
      final value = _parseEditedValue(valueController.text);
      await _runMemoryAction(
        () => widget.service.directEditCoreMemory(
          sessionId: widget.sessionId,
          identity: _requireIdentity(),
          actor: _actor,
          domain: block.domain,
          domainPath: _stringOrNull(targetRef['domain_path']),
          operations: [
            {
              'kind': 'patch_fields',
              'target_ref': targetRef,
              'field_patch': {selectedField: value},
            },
          ],
          baseRefs: [targetRef],
          sourceRefs: entry.sourceRefs,
          reason: reasonController.text.trim(),
        ),
      );
    } finally {
      valueController.dispose();
      reasonController.dispose();
    }
  }

  Future<void> _confirmRecallAction(
    RpMemoryBlockEnvelope block,
    RpMemoryEntryEnvelope entry,
    String action,
  ) async {
    final reasonController = TextEditingController();
    try {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: Text('Recall $action'),
          content: SizedBox(
            width: 480,
            child: TextField(
              controller: reasonController,
              decoration: const InputDecoration(labelText: 'reason'),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: const Text('提交'),
            ),
          ],
        ),
      );
      if (confirmed != true) return;
      await _runMemoryAction(
        () => widget.service.reviewRecallMemory(
          sessionId: widget.sessionId,
          identity: _requireIdentity(),
          actor: _actor,
          action: action,
          materialRefs: [entry.entryId],
          reason: reasonController.text.trim().isEmpty
              ? 'frontend memory panel $action'
              : reasonController.text.trim(),
        ),
      );
    } finally {
      reasonController.dispose();
    }
  }

  Future<void> _openArchivalEvolutionDialog(
    RpMemoryBlockEnvelope block,
    RpMemoryEntryEnvelope entry,
  ) async {
    final textController = TextEditingController();
    final reasonController = TextEditingController();
    try {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('Archival evolution'),
          content: SizedBox(
            width: 560,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: textController,
                  minLines: 5,
                  maxLines: 10,
                  decoration: const InputDecoration(
                    labelText: 'replacement text',
                  ),
                ),
                TextField(
                  controller: reasonController,
                  decoration: const InputDecoration(labelText: 'reason'),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: const Text('提交'),
            ),
          ],
        ),
      );
      if (confirmed != true || textController.text.trim().isEmpty) return;
      await _runMemoryAction(
        () => widget.service.evolveArchivalMemory(
          sessionId: widget.sessionId,
          identity: _requireIdentity(),
          actor: _actor,
          sourceAssetId: entry.entryId,
          expectedSourceVersion: entry.baseRevision ?? block.revision,
          replacementSections: [
            {
              'text': textController.text.trim(),
              'metadata': {
                'domain': block.domain,
                if (_domainPathFor(block, entry) != null)
                  'domain_path': _domainPathFor(block, entry),
              },
            },
          ],
          sourceRefs: entry.sourceRefs,
          reason: reasonController.text.trim().isEmpty
              ? 'frontend memory panel archival evolution'
              : reasonController.text.trim(),
        ),
      );
    } finally {
      textController.dispose();
      reasonController.dispose();
    }
  }

  Future<void> _runMemoryAction(
    Future<RpMemoryActionResponse> Function() action,
  ) async {
    if (_isActing) return;
    setState(() => _isActing = true);
    try {
      final receipt = await action();
      if (!mounted) return;
      setState(() => _lastAction = receipt);
      await _load(actionRefresh: receipt, preserveAction: true);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('${receipt.action ?? 'memory action'} 已完成')),
        );
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('Memory 动作失败: $e')));
    } finally {
      if (mounted) setState(() => _isActing = false);
    }
  }

  Map<String, dynamic> _requireIdentity() {
    final memory = _memory;
    if (memory == null || memory.identity.isEmpty) {
      throw StateError('memory_identity_unavailable');
    }
    return Map<String, dynamic>.from(memory.identity);
  }

  Map<String, dynamic> _objectRefFor(
    RpMemoryBlockEnvelope block,
    RpMemoryEntryEnvelope entry,
  ) {
    final revision = entry.baseRevision ?? block.revision;
    return {
      'object_id': _objectIdFor(block, entry),
      'layer': block.layer,
      'domain': block.domain,
      if (_domainPathFor(block, entry) != null)
        'domain_path': _domainPathFor(block, entry),
      if (block.scope != null) 'scope': block.scope,
      if (revision != null) 'revision': revision,
    };
  }

  String _objectIdFor(
    RpMemoryBlockEnvelope block,
    RpMemoryEntryEnvelope entry,
  ) {
    final metadata = _firstSourceMetadata(block, entry);
    return _stringOrNull(metadata['label']) ??
        _stringOrNull(block.provenance['label']) ??
        entry.label ??
        block.blockId;
  }

  String? _domainPathFor(
    RpMemoryBlockEnvelope block,
    RpMemoryEntryEnvelope entry,
  ) {
    final metadata = _firstSourceMetadata(block, entry);
    return _stringOrNull(metadata['domain_path']) ??
        _stringOrNull(block.provenance['domain_path']);
  }

  Map<String, dynamic> _firstSourceMetadata(
    RpMemoryBlockEnvelope block,
    RpMemoryEntryEnvelope entry,
  ) {
    final refs = entry.sourceRefs.isNotEmpty
        ? entry.sourceRefs
        : block.sourceRefs;
    if (refs.isEmpty) return const {};
    return _mapOrEmpty(refs.first['metadata']);
  }

  List<RpMemoryBlockEnvelope> _filteredBlocks(RpMemoryInspection memory) {
    return memory.blocks.where((block) {
      final layerMatches =
          _selectedLayer == _allFilter || block.layer == _selectedLayer;
      final domainMatches =
          _selectedDomain == _allFilter || block.domain == _selectedDomain;
      return layerMatches && domainMatches;
    }).toList();
  }

  List<String> _mergedActions(
    RpMemoryBlockEnvelope block,
    RpMemoryEntryEnvelope? entry,
  ) {
    return {
      ...block.allowedActions,
      if (entry != null) ...entry.allowedActions,
    }.toList();
  }

  Widget _metricChip(String label, String value) {
    final colors = context.owuiColors;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: colors.surface2,
        borderRadius: BorderRadius.circular(context.owuiRadius.rXl),
        border: Border.all(color: colors.borderSubtle),
      ),
      child: Text('$label · $value'),
    );
  }

  Widget _detailRow(String label, String value, {bool monospace = false}) {
    final spacing = context.owuiSpacing;
    final secondary = context.owuiColors.textSecondary;
    return Padding(
      padding: EdgeInsets.only(bottom: spacing.sm),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 136,
            child: Text(
              label,
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: secondary),
            ),
          ),
          Expanded(
            child: Text(
              value.isEmpty ? '当前不可用' : value,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: monospace ? secondary : null,
                fontFamily: monospace ? 'monospace' : null,
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _filterLabel(String value) => value == _allFilter ? 'All' : value;

  String _displayValue(String? value) {
    return value == null || value.isEmpty ? '当前不可用' : value;
  }

  String _jsonPreview(Object? value) {
    final encoded = const JsonEncoder.withIndent('  ').convert(value);
    if (encoded.length <= 900) return encoded;
    return '${encoded.substring(0, 900)}...';
  }

  String _initialFieldValue(Object? currentValue, String field) {
    if (currentValue is Map && currentValue.containsKey(field)) {
      return _jsonPreview(currentValue[field]);
    }
    return '';
  }

  Object? _parseEditedValue(String raw) {
    final trimmed = raw.trim();
    if (trimmed.isEmpty) return '';
    try {
      return jsonDecode(trimmed);
    } catch (_) {
      return raw;
    }
  }
}

String? _stringOrNull(Object? value) {
  final normalized = value?.toString().trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}

Map<String, dynamic> _mapOrEmpty(Object? value) {
  if (value is Map) {
    return Map<String, dynamic>.from(value);
  }
  return const <String, dynamic>{};
}
