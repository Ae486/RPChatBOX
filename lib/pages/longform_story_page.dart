import 'package:flutter/material.dart';

import '../adapters/ai_provider.dart';
import '../chat_ui/owui/components/owui_app_bar.dart';
import '../chat_ui/owui/components/owui_card.dart';
import '../chat_ui/owui/components/owui_scaffold.dart';
import '../chat_ui/owui/components/owui_snack_bar.dart';
import '../chat_ui/owui/owui_tokens_ext.dart';
import '../main.dart';
import '../models/story_runtime.dart';
import '../services/backend_story_service.dart';
import '../widgets/story_session_drawer.dart';

class LongformStoryPage extends StatefulWidget {
  final String? sessionId;

  const LongformStoryPage({
    super.key,
    this.sessionId,
  });

  @override
  State<LongformStoryPage> createState() => _LongformStoryPageState();
}

class _LongformStoryPageState extends State<LongformStoryPage> {
  final _service = BackendStoryService();
  final _messageController = TextEditingController();

  RpChapterSnapshot? _snapshot;
  List<RpStorySession> _sessions = const [];
  String? _currentSessionId;
  String? _selectedProviderId;
  String? _selectedModelId;
  bool _isLoading = true;
  bool _isSending = false;
  String _streamingText = '';
  String _streamingThinking = '';
  String? _streamingCommandKind;

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
        _isLoading = false;
      });
      _syncSelectedProviderAndModel();
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
    });
    _syncSelectedProviderAndModel();
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

  Future<void> _selectSession(String sessionId) async {
    setState(() {
      _currentSessionId = sessionId;
      _isLoading = true;
      _streamingText = '';
      _streamingThinking = '';
      _streamingCommandKind = null;
    });
    try {
      final snapshot = await _service.getSession(sessionId);
      final sessions = await _service.listSessions();
      if (!mounted) return;
      setState(() {
        _sessions = sessions;
        _snapshot = snapshot;
        _currentSessionId = sessionId;
        _isLoading = false;
      });
      _syncSelectedProviderAndModel();
    } catch (e) {
      if (!mounted) return;
      setState(() => _isLoading = false);
      OwuiSnackBars.error(context, message: '切换 story session 失败: $e');
    }
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

  Future<void> _runImmediateCommand(
    String commandKind, {
    String? targetArtifactId,
  }) async {
    final modelId = _selectedModelId;
    final sessionId = _currentSessionId;
    if (_snapshot == null || modelId == null || _isSending || sessionId == null) {
      return;
    }
    final providerModel = globalModelServiceManager.getModelWithProvider(modelId);
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
    if (_snapshot == null || modelId == null || _isSending || sessionId == null) {
      return;
    }
    final providerModel = globalModelServiceManager.getModelWithProvider(modelId);
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
      _discussionCommandForPhase(_snapshot?.chapter.phase ?? 'outline_drafting'),
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
          child: Text('当前还没有 active story session，可先从 prestory setup 里 activate。'),
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
                        Expanded(flex: 5, child: _buildDiscussionPane(snapshot)),
                      ],
                    )
                  : Column(
                      children: [
                        Expanded(flex: 6, child: _buildStoryPane(snapshot)),
                        SizedBox(height: spacing.lg),
                        Expanded(flex: 5, child: _buildDiscussionPane(snapshot)),
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
    final title = snapshot.chapter.acceptedOutlineJson?['title']?.toString() ??
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
              if (snapshot.session.currentStateJson['narrative_progress'] is Map)
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
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: colors.textSecondary,
                ),
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
    final pendingSegment = snapshot.pendingSegment;

    return OwuiCard(
      padding: EdgeInsets.all(spacing.lg),
      child: ListView(
        children: [
          Text(
            'Story Surface',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          SizedBox(height: spacing.md),
          if (acceptedOutline != null) _buildArtifactCard(acceptedOutline, isPrimary: true),
          if (acceptedOutline == null && snapshot.latestOutlineDraft != null)
            _buildArtifactCard(snapshot.latestOutlineDraft!, isPrimary: true),
          if (acceptedOutline == null && snapshot.latestOutlineDraft == null)
            _emptyPaneNote('No outline yet. Generate one to start the chapter loop.'),
          if (acceptedSegments.isNotEmpty) ...[
            SizedBox(height: spacing.lg),
            Text('Accepted Segments', style: Theme.of(context).textTheme.titleMedium),
            SizedBox(height: spacing.md),
            ...acceptedSegments.map((item) => Padding(
                  padding: EdgeInsets.only(bottom: spacing.md),
                  child: _buildArtifactCard(item),
                )),
          ],
          if (pendingSegment != null || _isStreamingLeftPane) ...[
            SizedBox(height: spacing.lg),
            Text('Pending Candidate', style: Theme.of(context).textTheme.titleMedium),
            SizedBox(height: spacing.md),
            if (pendingSegment != null)
              _buildArtifactCard(
                pendingSegment,
                isPending: true,
              ),
            if (_isStreamingLeftPane)
              Padding(
                padding: EdgeInsets.only(top: pendingSegment != null ? spacing.md : 0),
                child: _buildStreamingCard(),
              ),
          ],
        ],
      ),
    );
  }

  Widget _buildDiscussionPane(RpChapterSnapshot snapshot) {
    final spacing = context.owuiSpacing;
    final phase = snapshot.chapter.phase;
    return OwuiCard(
      padding: EdgeInsets.all(spacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Discussion / Review', style: Theme.of(context).textTheme.titleLarge),
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
          Row(
            children: [
              Expanded(
                child: DropdownButtonFormField<String>(
                  initialValue: _selectedProviderId,
                  decoration: const InputDecoration(labelText: 'Provider'),
                  items: globalModelServiceManager
                      .getEnabledProviders()
                      .map(
                        (provider) => DropdownMenuItem<String>(
                          value: provider.id,
                          child: Text(provider.name),
                        ),
                      )
                      .toList(),
                  onChanged: (value) {
                    setState(() {
                      _selectedProviderId = value;
                      final models = value == null
                          ? const []
                          : globalModelServiceManager
                              .getModelsByProvider(value)
                              .where((item) => item.isEnabled)
                              .toList();
                      _selectedModelId =
                          models.isEmpty ? null : models.first.id;
                    });
                  },
                ),
              ),
              SizedBox(width: spacing.md),
              Expanded(
                child: DropdownButtonFormField<String>(
                  initialValue: _selectedModelId,
                  decoration: const InputDecoration(labelText: 'Model'),
                  items: (_selectedProviderId == null
                          ? const []
                          : globalModelServiceManager
                              .getModelsByProvider(_selectedProviderId!)
                              .where((item) => item.isEnabled)
                              .toList())
                      .map(
                        (model) => DropdownMenuItem<String>(
                          value: model.id,
                          child: Text(model.displayName),
                        ),
                      )
                      .toList(),
                  onChanged: (value) {
                    setState(() {
                      _selectedModelId = value;
                    });
                  },
                ),
              ),
              SizedBox(width: spacing.md),
              FilledButton.icon(
                onPressed: _isSending ? null : _sendDiscussion,
                icon: const Icon(Icons.send_outlined),
                label: const Text('Send'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  List<Widget> _buildCommandButtons(RpChapterSnapshot snapshot) {
    final phase = snapshot.chapter.phase;
    final pendingSegment = snapshot.pendingSegment;
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
            style: Theme.of(context).textTheme.labelLarge?.copyWith(
                  color: colors.textSecondary,
                ),
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
          Text(
            switch (entry.role) {
              'user' => 'You',
              'system' => 'System',
              _ => 'Story Runtime',
            },
            style: Theme.of(context).textTheme.titleSmall,
          ),
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
            style: Theme.of(context).textTheme.labelLarge?.copyWith(
                  color: colors.textSecondary,
                ),
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
      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
            color: context.owuiColors.textSecondary,
          ),
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
