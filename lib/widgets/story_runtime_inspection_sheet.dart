import 'package:flutter/material.dart';

import '../chat_ui/owui/components/owui_card.dart';
import '../chat_ui/owui/owui_tokens_ext.dart';
import '../models/story_runtime.dart';
import '../services/backend_story_service.dart';

class StoryRuntimeInspectionSheet extends StatefulWidget {
  final BackendStoryService service;
  final String sessionId;
  final int chapterIndex;
  final String mode;
  final String? preferredBranchHeadId;
  final String? preferredTurnId;
  final int activeCommentCount;
  final int activeTrackedChangeCount;

  const StoryRuntimeInspectionSheet({
    super.key,
    required this.service,
    required this.sessionId,
    required this.chapterIndex,
    required this.mode,
    required this.preferredBranchHeadId,
    required this.preferredTurnId,
    required this.activeCommentCount,
    required this.activeTrackedChangeCount,
  });

  @override
  State<StoryRuntimeInspectionSheet> createState() =>
      _StoryRuntimeInspectionSheetState();
}

class _StoryRuntimeInspectionSheetState
    extends State<StoryRuntimeInspectionSheet> {
  RpRuntimeInspection? _inspection;
  RpRuntimeDebugSurface? _debugSurface;
  List<RpRuntimeConfigControlReceipt> _configHistory = const [];
  List<String> _loadNotes = const [];
  bool _isLoading = true;
  String? _fatalError;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _fatalError = null;
      _loadNotes = const [];
    });

    final notes = <String>[];
    try {
      final inspection = await widget.service.getRuntimeInspection(
        sessionId: widget.sessionId,
        branchHeadId: widget.preferredBranchHeadId,
        turnId: widget.preferredTurnId,
        targetChapterIndex: widget.chapterIndex,
        limit: 12,
      );

      RpRuntimeDebugSurface? debugSurface;
      try {
        debugSurface = await widget.service.getRuntimeDebug(
          sessionId: widget.sessionId,
        );
      } catch (_) {
        notes.add('图执行检查点暂不可用，已退回 inspect 摘要。');
      }

      List<RpRuntimeConfigControlReceipt> configHistory;
      try {
        configHistory = await widget.service.getRuntimeConfigHistory(
          sessionId: widget.sessionId,
        );
      } catch (_) {
        notes.add('运行配置历史接口暂不可用，已使用 inspect 内联摘要。');
        configHistory = inspection.runtimeConfig.controlHistory;
      }
      configHistory.sort((a, b) => b.createdAt.compareTo(a.createdAt));

      if (!mounted) return;
      setState(() {
        _inspection = inspection;
        _debugSurface = debugSurface;
        _configHistory = configHistory;
        _loadNotes = notes;
        _isLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _fatalError = '加载运行态检查失败: $e';
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
        heightFactor: 0.92,
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
              Text('运行态检查', style: Theme.of(context).textTheme.titleLarge),
              SizedBox(height: spacing.xs),
              Text(
                '查看当前章节的 branch / turn / packet / retrieval / chapter bridge 只读摘要。',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: context.owuiColors.textSecondary,
                ),
              ),
            ],
          ),
        ),
        IconButton(
          tooltip: '刷新运行态检查',
          onPressed: _isLoading ? null : _load,
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
            Text(_fatalError ?? '运行态检查暂不可用'),
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
    final inspection = _inspection;
    if (inspection == null) {
      return Center(
        child: Text('运行态检查暂不可用', style: Theme.of(context).textTheme.bodyMedium),
      );
    }

    final spacing = context.owuiSpacing;
    return ListView(
      children: [
        if (_loadNotes.isNotEmpty) ...[
          _buildNoticeCard(_loadNotes),
          SizedBox(height: spacing.md),
        ],
        _buildOverviewCard(inspection),
        SizedBox(height: spacing.md),
        _buildRuntimeConfigCard(inspection),
        SizedBox(height: spacing.md),
        _buildWriterPacketCard(inspection),
        SizedBox(height: spacing.md),
        _buildChapterProgressCard(inspection),
        SizedBox(height: spacing.md),
        _buildReviewOverlayCard(inspection),
        SizedBox(height: spacing.md),
        _buildChapterBridgeCard(inspection),
        SizedBox(height: spacing.md),
        _buildJobLedgerCard(inspection),
        SizedBox(height: spacing.md),
        _buildRetrievalCard(inspection),
        SizedBox(height: spacing.md),
        _buildModeSidecarsCard(inspection),
        SizedBox(height: spacing.md),
        _buildBranchReceiptsCard(inspection),
        SizedBox(height: spacing.md),
        _buildGraphDebugCard(),
      ],
    );
  }

  Widget _buildNoticeCard(List<String> notes) {
    final spacing = context.owuiSpacing;
    return OwuiCard(
      padding: EdgeInsets.all(spacing.md),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.only(top: 2),
            child: Icon(Icons.info_outline, size: 18),
          ),
          SizedBox(width: spacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: notes
                  .map(
                    (item) => Padding(
                      padding: EdgeInsets.only(bottom: spacing.xs),
                      child: Text(item),
                    ),
                  )
                  .toList(),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildOverviewCard(RpRuntimeInspection inspection) {
    final spacing = context.owuiSpacing;
    return _buildSectionCard(
      title: '当前定位',
      description: '用于确认当前页面看到的是哪条分支、哪一轮 turn、哪份快照。',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: spacing.sm,
            runSpacing: spacing.sm,
            children: [
              _metricChip('模式', inspection.mode),
              _metricChip('章节', '第 ${widget.chapterIndex} 章'),
              _metricChip('只读', inspection.readOnly ? '是' : '否'),
            ],
          ),
          SizedBox(height: spacing.md),
          _detailRow(
            '活动分支',
            _displayValue(inspection.activeBranchHeadId),
            monospace: true,
          ),
          _detailRow(
            '选中 turn',
            _displayValue(inspection.selection.selectedTurnId),
            monospace: true,
          ),
          _detailRow(
            '活动 snapshot',
            _displayValue(inspection.activeSnapshotId),
            monospace: true,
          ),
          _detailRow(
            '分支锚点 turn',
            _displayValue(inspection.branchAnchorTurnId),
            monospace: true,
          ),
          _detailRow(
            '可见告警',
            inspection.warnings.isEmpty ? '无' : inspection.warnings.join('，'),
          ),
        ],
      ),
    );
  }

  Widget _buildRuntimeConfigCard(RpRuntimeInspection inspection) {
    final history = _configHistory;
    final latest = history.isEmpty ? null : history.first;
    return _buildSectionCard(
      title: '运行配置 / 历史',
      description: '这里只看当前生效快照和最近控制历史，不在面板里做任何配置改写。',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _detailRow(
            '当前生效 snapshot',
            _displayValue(
              inspection.runtimeConfig.activeRuntimeProfileSnapshotId ??
                  inspection.activeSnapshotId,
            ),
            monospace: true,
          ),
          _detailRow(
            '当前配置项数',
            inspection.runtimeConfig.effectiveRuntimeStoryConfig.length
                .toString(),
          ),
          _detailRow('历史记录数', history.length.toString()),
          _detailRow(
            '最近变更字段',
            latest == null || latest.changedFields.isEmpty
                ? '当前不可用'
                : latest.changedFields.join('，'),
          ),
          _detailRow('最近变更来源', latest == null ? '当前不可用' : latest.source),
          _detailRow(
            '最近发布时间',
            latest == null ? '当前不可用' : latest.createdAt.toLocal().toString(),
          ),
        ],
      ),
    );
  }

  Widget _buildWriterPacketCard(RpRuntimeInspection inspection) {
    final packet = inspection.writerPacket;
    final writerInputRefs = _mapList(packet?['writer_input_refs']);
    final packetRefs = _mapList(packet?['packet_refs']);
    final writerOutputRefs = _mapList(packet?['writer_output_refs']);
    final manifests = inspection.writerReadManifests;
    final manifestIds = _stringList(packet?['runtime_read_manifest_ids']);
    return _buildSectionCard(
      title: 'Writer 包摘要',
      description: '帮助判断这次写作/改写有没有拿到可审计的 packet / read manifest 证据。',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _detailRow('writer input refs', writerInputRefs.length.toString()),
          _detailRow('packet refs', packetRefs.length.toString()),
          _detailRow('writer output refs', writerOutputRefs.length.toString()),
          _detailRow('read manifests', manifests.length.toString()),
          _detailRow(
            'runtime read manifest ids',
            manifestIds.isEmpty ? '当前不可用' : manifestIds.join('，'),
            monospace: true,
          ),
        ],
      ),
    );
  }

  Widget _buildReviewOverlayCard(RpRuntimeInspection inspection) {
    final sections = _reviewOverlaySections(inspection);
    final labelSummary = sections
        .map((item) => _stringOrNull(item['label']) ?? 'review_overlay')
        .toSet()
        .join('，');
    final sourceRefCount = sections.fold<int>(
      0,
      (sum, item) => sum + _stringList(item['source_ref_ids']).length,
    );
    final hasPageConstraints =
        widget.activeCommentCount > 0 || widget.activeTrackedChangeCount > 0;

    return _buildSectionCard(
      title: '修订约束摘要',
      description:
          '同时对照页面上的批注/修订数量，以及 inspect 里 writer 包是否真的带上了 review overlay 证据。',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _detailRow('当前页面活跃批注', widget.activeCommentCount.toString()),
          _detailRow('当前页面活跃修订', widget.activeTrackedChangeCount.toString()),
          _detailRow('writer review sections', sections.length.toString()),
          _detailRow(
            'review section labels',
            labelSummary.isEmpty ? '当前不可用' : labelSummary,
          ),
          _detailRow('review source refs', sourceRefCount.toString()),
          if (hasPageConstraints && sections.isEmpty)
            Padding(
              padding: EdgeInsets.only(top: context.owuiSpacing.sm),
              child: Text(
                '当前页面已经有修订约束，但本次运行态摘要里还看不到 writer 已读取的 review overlay 证据。',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: Theme.of(context).colorScheme.error,
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildChapterProgressCard(RpRuntimeInspection inspection) {
    final latest = _nullableMap(inspection.chapterProgress['latest_for_chapter']);
    return _buildSectionCard(
      title: 'Beat 进度',
      description: '用于确认当前续写到底绑定到了哪个 beat，以及本章已经覆盖了多少 beat。',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _detailRow(
            '进度条目数',
            _mapList(inspection.chapterProgress['items']).length.toString(),
          ),
          _detailRow(
            '当前 beat',
            _displayValue(_stringOrNull(latest?['current_beat_id'])),
            monospace: true,
          ),
          _detailRow(
            '已覆盖 beat',
            (latest?['covered_beat_count'] as num?)?.toInt().toString() ??
                '当前不可用',
          ),
          _detailRow(
            'outline ref',
            _displayValue(_stringOrNull(latest?['outline_artifact_id'])),
            monospace: true,
          ),
        ],
      ),
    );
  }

  Widget _buildChapterBridgeCard(RpRuntimeInspection inspection) {
    final latest = _nullableMap(
      inspection.chapterBridge['latest_for_target_chapter'],
    );
    return _buildSectionCard(
      title: '章节衔接',
      description: '用于确认下一章或续写承接读取的 bridge 是否已经落盘。',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _detailRow(
            'bridge 条目数',
            _mapList(inspection.chapterBridge['items']).length.toString(),
          ),
          _detailRow(
            '目标章节',
            _displayValue(
              _stringOrNull(inspection.chapterBridge['target_chapter_index']),
            ),
          ),
          _detailRow(
            '最新桥接来源章',
            _displayValue(_stringOrNull(latest?['source_chapter_index'])),
          ),
          _detailRow(
            'latest continuity refs',
            _stringList(latest?['continuity_refs']).length.toString(),
          ),
          _detailRow('摘要', _shortText(_stringOrNull(latest?['summary_text']))),
        ],
      ),
    );
  }

  Widget _buildJobLedgerCard(RpRuntimeInspection inspection) {
    final items = _mapList(inspection.jobLedger['items']);
    final latest = items.isEmpty ? null : items.first;
    final statusCounts = _nullableMap(inspection.jobLedger['status_counts']);
    final requiredCount = items
        .where((item) => item['required_for_turn_completion'] == true)
        .length;
    return _buildSectionCard(
      title: '作业账本',
      description: '这里看 turn 相关 job 的数量、状态汇总，以及是否存在完成判定依赖。',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _detailRow('job 数量', items.length.toString()),
          _detailRow('required job 数量', requiredCount.toString()),
          _detailRow('状态汇总', _statusSummary(statusCounts)),
          _detailRow(
            '最近 job',
            latest == null
                ? '当前不可用'
                : '${_stringOrNull(latest['job_kind']) ?? 'unknown'} · ${_stringOrNull(latest['status']) ?? 'unknown'}',
          ),
        ],
      ),
    );
  }

  Widget _buildRetrievalCard(RpRuntimeInspection inspection) {
    return _buildSectionCard(
      title: 'Retrieval 摘要',
      description: '确认本轮有没有检索卡片、展开块、miss 记录以及 usage 回执。',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _detailRow(
            'cards',
            _mapList(inspection.retrieval['cards']).length.toString(),
          ),
          _detailRow(
            'expanded chunks',
            _mapList(inspection.retrieval['expanded_chunks']).length.toString(),
          ),
          _detailRow(
            'misses',
            _mapList(inspection.retrieval['misses']).length.toString(),
          ),
          _detailRow(
            'usage records',
            _mapList(inspection.retrieval['usage_records']).length.toString(),
          ),
          _detailRow(
            'usage refs',
            _stringList(inspection.retrieval['usage_refs']).length.toString(),
          ),
        ],
      ),
    );
  }

  Widget _buildModeSidecarsCard(RpRuntimeInspection inspection) {
    final materials = _mapList(inspection.modeSidecars['materials']);
    final packetSections = _mapList(inspection.modeSidecars['packet_sections']);
    final kinds = materials
        .map((item) => _stringOrNull(item['material_kind']))
        .whereType<String>()
        .toSet()
        .join('，');
    return _buildSectionCard(
      title: 'Mode Sidecars',
      description: '用于确认规则卡、规则状态卡等 sidecar 没有混入正文真相层。',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _detailRow('sidecar materials', materials.length.toString()),
          _detailRow('packet sections', packetSections.length.toString()),
          _detailRow('sidecar kinds', kinds.isEmpty ? '当前不可用' : kinds),
        ],
      ),
    );
  }

  Widget _buildBranchReceiptsCard(RpRuntimeInspection inspection) {
    final receipts = inspection.branchControlReceipts;
    final latest = receipts.isEmpty ? null : receipts.first;
    return _buildSectionCard(
      title: 'Branch Receipts',
      description: '这里只做 receipt 摘要，不在前端实现完整 branch 操作面板。',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _detailRow('receipt 数量', receipts.length.toString()),
          _detailRow(
            '最近 control kind',
            latest == null
                ? '当前不可用'
                : (_stringOrNull(latest['control_kind']) ?? 'unknown'),
          ),
          _detailRow(
            '目标 turn',
            latest == null
                ? '当前不可用'
                : _displayValue(_stringOrNull(latest['target_turn_id'])),
            monospace: true,
          ),
          _detailRow(
            '最新时间',
            latest == null
                ? '当前不可用'
                : (_stringOrNull(latest['created_at']) ?? '当前不可用'),
          ),
        ],
      ),
    );
  }

  Widget _buildGraphDebugCard() {
    final debugSurface = _debugSurface;
    return _buildSectionCard(
      title: '图执行检查点',
      description: '附带展示 graph thread 和最近 checkpoint，方便区分“面板没看到”还是“图状态没推进”。',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _detailRow(
            'graph thread',
            debugSurface == null
                ? '当前不可用'
                : _displayValue(debugSurface.graphThreadId),
            monospace: true,
          ),
          _detailRow(
            'latest checkpoint',
            debugSurface == null
                ? '当前不可用'
                : _displayValue(
                    _stringOrNull(
                          debugSurface
                              .latestMeaningfulCheckpoint?['checkpoint_id'],
                        ) ??
                        _stringOrNull(
                          debugSurface.latestCheckpoint?['checkpoint_id'],
                        ),
                  ),
            monospace: true,
          ),
          _detailRow(
            'history 长度',
            debugSurface == null
                ? '当前不可用'
                : debugSurface.history.length.toString(),
          ),
        ],
      ),
    );
  }

  Widget _buildSectionCard({
    required String title,
    required String description,
    required Widget child,
  }) {
    final spacing = context.owuiSpacing;
    return OwuiCard(
      padding: EdgeInsets.all(spacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          SizedBox(height: spacing.xs),
          Text(
            description,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: context.owuiColors.textSecondary,
            ),
          ),
          SizedBox(height: spacing.md),
          child,
        ],
      ),
    );
  }

  Widget _metricChip(String label, String value) {
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

  Widget _detailRow(String label, String value, {bool monospace = false}) {
    final spacing = context.owuiSpacing;
    final secondary = context.owuiColors.textSecondary;
    final valueStyle =
        (monospace
                ? Theme.of(context).textTheme.bodySmall
                : Theme.of(context).textTheme.bodyMedium)
            ?.copyWith(
              color: monospace ? secondary : null,
              fontFamily: monospace ? 'monospace' : null,
            );
    return Padding(
      padding: EdgeInsets.only(bottom: spacing.sm),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 156,
            child: Text(
              label,
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: secondary),
            ),
          ),
          Expanded(child: Text(value, style: valueStyle)),
        ],
      ),
    );
  }

  List<Map<String, dynamic>> _reviewOverlaySections(
    RpRuntimeInspection inspection,
  ) {
    final sections = <Map<String, dynamic>>[];
    for (final manifest in inspection.writerReadManifests) {
      for (final section in _mapList(manifest['packet_sections'])) {
        final metadata =
            _nullableMap(section['metadata_json']) ??
            _nullableMap(section['metadata']);
        final family = _stringOrNull(metadata?['section_family']);
        final sourceKind = _stringOrNull(section['source_kind']) ?? '';
        final sectionId = _stringOrNull(section['section_id']) ?? '';
        final label = _stringOrNull(section['label']) ?? '';
        if (family == 'review_overlay' ||
            sourceKind.contains('review_overlay') ||
            sectionId.startsWith('review_overlay.') ||
            label == 'review_overlay') {
          sections.add(section);
        }
      }
    }
    return sections;
  }

  String _statusSummary(Map<String, dynamic>? statusCounts) {
    if (statusCounts == null || statusCounts.isEmpty) {
      return '当前不可用';
    }
    final items = statusCounts.entries
        .map((entry) => '${entry.key}: ${entry.value}')
        .toList();
    return items.join('，');
  }

  String _displayValue(String? value) {
    return value == null || value.isEmpty ? '当前不可用' : value;
  }

  String _shortText(String? value) {
    if (value == null || value.isEmpty) return '当前不可用';
    if (value.length <= 140) return value;
    return '${value.substring(0, 140)}…';
  }
}

String? _stringOrNull(Object? value) {
  final normalized = value?.toString().trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}

Map<String, dynamic>? _nullableMap(Object? value) {
  if (value is Map) {
    return Map<String, dynamic>.from(value);
  }
  return null;
}

List<Map<String, dynamic>> _mapList(Object? value) {
  return (value as List? ?? const [])
      .whereType<Map>()
      .map((item) => Map<String, dynamic>.from(item))
      .toList();
}

List<String> _stringList(Object? value) {
  return (value as List? ?? const []).map((item) => item.toString()).toList();
}
