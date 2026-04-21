import 'package:flutter/material.dart';

import '../adapters/ai_provider.dart';
import '../chat_ui/owui/components/owui_app_bar.dart';
import '../chat_ui/owui/components/owui_card.dart';
import '../chat_ui/owui/components/owui_scaffold.dart';
import '../chat_ui/owui/components/owui_snack_bar.dart';
import '../chat_ui/owui/owui_tokens_ext.dart';
import '../pages/longform_story_page.dart';
import '../main.dart';
import '../models/rp_setup.dart';
import '../services/backend_rp_setup_service.dart';
import '../services/backend_story_service.dart';

class PrestorySetupPage extends StatefulWidget {
  const PrestorySetupPage({super.key});

  @override
  State<PrestorySetupPage> createState() => _PrestorySetupPageState();
}

class _PrestorySetupPageState extends State<PrestorySetupPage> {
  final _service = BackendRpSetupService();
  final _storyService = BackendStoryService();
  final _messageController = TextEditingController();
  final Map<String, List<_SetupChatEntry>> _dialogues = {};

  List<RpSetupWorkspace> _workspaces = const [];
  RpSetupWorkspace? _currentWorkspace;
  RpActivationCheckResult? _lastActivationCheck;
  _SetupWizardStage _selectedStage = _SetupWizardStage.worldBackground;
  String? _selectedProviderId;
  String? _selectedModelId;
  bool _isLoading = true;
  bool _isSending = false;

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
      _syncSelectedStage(force: true);
      _syncSelectedProviderAndModel();
      if (_currentWorkspace != null) {
        await _refreshWorkspace(_currentWorkspace!.workspaceId, preserveStage: false);
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
    final workspaceChanged = _currentWorkspace?.workspaceId != workspace.workspaceId;
    setState(() {
      _workspaces = [
        workspace,
        ..._workspaces.where((item) => item.workspaceId != workspace.workspaceId),
      ];
      _currentWorkspace = workspace;
    });
    if (!preserveStage || workspaceChanged) {
      _syncSelectedStage(force: true);
    }
    _syncSelectedProviderAndModel();
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
    if (!force && _selectedStage != _SetupWizardStage.activate) {
      return;
    }
    setState(() {
      _selectedStage = nextStage;
    });
  }

  void _syncSelectedProviderAndModel() {
    final providers = globalModelServiceManager.getEnabledProviders();
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
            onPressed: () => Navigator.pop(dialogContext, controller.text.trim()),
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
      });
      _syncSelectedStage(force: true);
      OwuiSnackBars.success(context, message: '已创建 prestory workspace');
    } catch (e) {
      if (!mounted) return;
      OwuiSnackBars.error(context, message: '创建 workspace 失败: $e');
    }
  }

  Future<void> _sendTurn() async {
    final workspace = _currentWorkspace;
    final modelId = _selectedModelId;
    final userPrompt = _messageController.text.trim();
    if (workspace == null || modelId == null || userPrompt.isEmpty || _isSending) {
      return;
    }
    final modelWithProvider = globalModelServiceManager.getModelWithProvider(modelId);
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
        targetStep: _targetStepForStage(_selectedStage, workspace),
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
      final result = await _storyService.activateWorkspace(workspace.workspaceId);
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
                borderRadius: BorderRadius.circular(dialogContext.owuiRadius.r3xl),
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
        final curved = CurvedAnimation(parent: animation, curve: Curves.easeOutCubic);
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
            padding: EdgeInsets.fromLTRB(spacing.lg, spacing.lg, spacing.lg, spacing.md),
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
                            : '当前向导步骤: ${_selectedStage.label} · workspace state: ${workspace.workspaceState}',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: colors.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
                if (workspace != null)
                  Chip(
                    label: Text('v${workspace.version}'),
                  ),
              ],
            ),
          ),
          Divider(height: 1, color: colors.borderSubtle),
          Expanded(
            child: Padding(
              padding: EdgeInsets.fromLTRB(spacing.lg, spacing.lg, spacing.lg, spacing.md),
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
                            '当前还没有对话。发送第一条指令开始收敛 ${_selectedStage.label}。',
                            style: Theme.of(context).textTheme.bodyMedium,
                            textAlign: TextAlign.center,
                          ),
                        )
                      : ListView.separated(
                          itemCount: entries.length,
                          separatorBuilder: (_, __) => SizedBox(height: spacing.md),
                          itemBuilder: (context, index) => _buildMessage(entries[index]),
                        ),
            ),
          ),
          Padding(
            padding: EdgeInsets.fromLTRB(spacing.lg, spacing.sm, spacing.lg, spacing.lg),
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
                            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: colors.textSecondary,
                            ),
                          ),
                        ),
                        Text(
                          'Mode: ${workspace.mode}',
                          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: colors.textSecondary,
                          ),
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
                            labelText: '给 SetupAgent 的当前 step 指令',
                            hintText: _stagePromptHint(_selectedStage),
                            suffixIcon: _isSending
                                ? const Padding(
                                    padding: EdgeInsets.all(12),
                                    child: SizedBox(
                                      width: 16,
                                      height: 16,
                                      child: CircularProgressIndicator(strokeWidth: 2),
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

  Widget _buildSidebarContent({
    required bool isModal,
    VoidCallback? onClose,
  }) {
    final workspace = _currentWorkspace;
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;

    return Column(
      children: [
        Padding(
          padding: EdgeInsets.fromLTRB(spacing.lg, spacing.lg, spacing.lg, spacing.md),
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
                IconButton(
                  onPressed: onClose,
                  icon: const Icon(Icons.close),
                ),
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
                    Text('入口与模型', style: Theme.of(context).textTheme.titleMedium),
                    SizedBox(height: spacing.md),
                    DropdownButtonFormField<String>(
                      initialValue: workspace?.workspaceId,
                      decoration: const InputDecoration(labelText: 'Workspace'),
                      items: _workspaces
                          .map(
                            (item) => DropdownMenuItem<String>(
                              value: item.workspaceId,
                              child: Text('${item.storyId} · ${item.currentStep}'),
                            ),
                          )
                          .toList(),
                      onChanged: (value) async {
                        if (value == null) return;
                        await _refreshWorkspace(value, preserveStage: false);
                      },
                    ),
                    SizedBox(height: spacing.md),
                    DropdownButtonFormField<String>(
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
                    SizedBox(height: spacing.md),
                    DropdownButtonFormField<String>(
                      initialValue: _selectedModelId,
                      decoration: const InputDecoration(labelText: 'Model'),
                      items: globalModelServiceManager
                          .getModelsByProvider(_selectedProviderId ?? '')
                          .where((item) => item.isEnabled)
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
                    if (workspace != null) ...[
                      SizedBox(height: spacing.md),
                      Text(
                        '当前聚焦：${_selectedStage.label}',
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
                _buildSidebarStageMap(workspace),
                SizedBox(height: spacing.lg),
                _buildCurrentStagePanel(workspace),
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
          Text(
            switch (entry.kind) {
              _SetupChatEntryKind.user => 'You',
              _SetupChatEntryKind.assistant => 'SetupAgent',
              _SetupChatEntryKind.system => 'System',
            },
            style: Theme.of(context).textTheme.titleSmall,
          ),
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
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: colors.textSecondary,
                  ),
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
          Text(proposal.reviewMessage, style: Theme.of(context).textTheme.titleSmall),
          SizedBox(height: spacing.sm),
          Text('Step: ${proposal.stepId}'),
          if ((proposal.reason ?? '').isNotEmpty) Text('Reason: ${proposal.reason}'),
          if (proposal.unresolvedWarnings.isNotEmpty)
            ...proposal.unresolvedWarnings.map((warning) => Text('Warning: $warning')),
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

  Widget _buildSidebarStageMap(RpSetupWorkspace workspace) {
    final spacing = context.owuiSpacing;
    final items = _SetupWizardStage.values;

    return _buildSidebarSectionCard(
      title: '流程地图',
      subtitle: '一次只看一个步骤。当前步骤高亮，后续步骤可以手动切换查看。',
      children: [
        Wrap(
          spacing: spacing.sm,
          runSpacing: spacing.sm,
          children: items
              .map(
                (item) => ChoiceChip(
                  label: Text('${item.label} · ${_stageReadyLabel(item, workspace)}'),
                  selected: _selectedStage == item,
                  onSelected: (_) {
                    setState(() {
                      _selectedStage = item;
                    });
                  },
                ),
              )
              .toList(),
        ),
      ],
    );
  }

  _SetupWizardStage _preferredStageForWorkspace(RpSetupWorkspace workspace) {
    if (workspace.workspaceState == 'activated') {
      return _SetupWizardStage.activate;
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

  String _stageReadyLabel(_SetupWizardStage stage, RpSetupWorkspace workspace) {
    switch (stage) {
      case _SetupWizardStage.worldBackground:
        return _worldFoundationEntries(workspace).isNotEmpty ? '已填写' : '待补充';
      case _SetupWizardStage.characterDesign:
        return _characterFoundationEntries(workspace).isNotEmpty ? '已填写' : '待补充';
      case _SetupWizardStage.plotBlueprint:
        return workspace.longformBlueprintDraft != null ? '已填写' : '待补充';
      case _SetupWizardStage.writerConfig:
        return workspace.writingContractDraft != null ? '已填写' : '待补充';
      case _SetupWizardStage.workerConfig:
        return workspace.storyConfigDraft != null ? '已填写' : '待补充';
      case _SetupWizardStage.overview:
        return workspace.acceptedCommits.isNotEmpty ? '可查看' : '待收敛';
      case _SetupWizardStage.activate:
        return (_lastActivationCheck?.ready ?? false) ||
                workspace.workspaceState == 'ready_to_activate' ||
                workspace.workspaceState == 'activated'
            ? '可激活'
            : '未就绪';
    }
  }

  String _stagePromptHint(_SetupWizardStage stage) {
    switch (stage) {
      case _SetupWizardStage.worldBackground:
        return '例如：先帮我补齐世界规则、地理背景和稳定设定。';
      case _SetupWizardStage.characterDesign:
        return '例如：继续收敛主角设定、关系和 voice seed。';
      case _SetupWizardStage.plotBlueprint:
        return '例如：请把核心冲突、章节推进和伏笔回收方向收敛清楚。';
      case _SetupWizardStage.writerConfig:
        return '例如：帮我明确 POV、文风、写作约束和任务写作规则。';
      case _SetupWizardStage.workerConfig:
        return '例如：帮我确定 model profile、worker profile 和 post-write preset。';
      case _SetupWizardStage.overview:
        return '例如：请帮我检查哪些部分已经可以提交 review，哪些还缺。';
      case _SetupWizardStage.activate:
        return '例如：请先检查当前是否已经满足激活条件。';
    }
  }

  String? _targetStepForStage(
    _SetupWizardStage stage,
    RpSetupWorkspace workspace,
  ) {
    switch (stage) {
      case _SetupWizardStage.worldBackground:
      case _SetupWizardStage.characterDesign:
        return 'foundation';
      case _SetupWizardStage.plotBlueprint:
        return 'longform_blueprint';
      case _SetupWizardStage.writerConfig:
        return 'writing_contract';
      case _SetupWizardStage.workerConfig:
        return 'story_config';
      case _SetupWizardStage.overview:
      case _SetupWizardStage.activate:
        return workspace.currentStep;
    }
  }

  Widget _buildCurrentStagePanel(RpSetupWorkspace workspace) {
    final spacing = context.owuiSpacing;
    final panel = switch (_selectedStage) {
      _SetupWizardStage.worldBackground => _buildSidebarSectionCard(
          title: '世界观背景',
          subtitle: '只看世界规则、背景设定和稳定的环境事实。',
          children: _buildFoundationEntryWidgets(
            _worldFoundationEntries(workspace),
            emptyText: '还没有世界观背景条目。',
          ),
        ),
      _SetupWizardStage.characterDesign => _buildSidebarSectionCard(
          title: '角色设定',
          subtitle: '只看人物设定、人物背景和角色 voice seed 相关条目。',
          children: _buildFoundationEntryWidgets(
            _characterFoundationEntries(workspace),
            emptyText: '还没有角色设定条目。',
          ),
        ),
      _SetupWizardStage.plotBlueprint => _buildSidebarSectionCard(
          title: '伏笔 / 剧情设计',
          subtitle: '只看 premise、冲突、章节推进和伏笔回收方向。',
          children: _buildBlueprintWidgets(workspace),
        ),
      _SetupWizardStage.writerConfig => _buildSidebarSectionCard(
          title: '作家配置',
          subtitle: '只看 POV、风格、写作约束和任务写作规则。',
          children: _buildWritingContractWidgets(workspace),
        ),
      _SetupWizardStage.workerConfig => _buildSidebarSectionCard(
          title: 'Worker 配置',
          subtitle: '只看模型画像、worker画像和 post-write preset。',
          children: _buildStoryConfigWidgets(workspace),
        ),
      _SetupWizardStage.overview => _buildSidebarSectionCard(
          title: '全览 / Review',
          subtitle: '在这里统一检查 setup 是否已经收敛到可激活状态。',
          children: [
            ..._buildOverviewWidgets(workspace),
            SizedBox(height: spacing.md),
            Text('待 Review / Commit', style: Theme.of(context).textTheme.titleSmall),
            SizedBox(height: spacing.sm),
            if (workspace.pendingCommitProposals.isEmpty)
              const Text('当前没有待 review proposal')
            else
              ...workspace.pendingCommitProposals.map(_buildProposalCard),
            SizedBox(height: spacing.md),
            Text('Retrieval Ingestion', style: Theme.of(context).textTheme.titleSmall),
            SizedBox(height: spacing.sm),
            ..._buildRetrievalOverviewWidgets(workspace),
          ],
        ),
      _SetupWizardStage.activate => _buildSidebarSectionCard(
          title: 'Activate',
          subtitle: '最后一步才显示激活入口。',
          children: [
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
                _lastActivationCheck!.ready
                    ? '当前已满足激活前提。'
                    : '当前还不能激活，需要先处理阻塞项。',
              ),
              if (_lastActivationCheck!.blockingIssues.isNotEmpty) ...[
                SizedBox(height: spacing.sm),
                ..._lastActivationCheck!.blockingIssues.map((issue) => Text('Blocking: $issue')),
              ],
              if (_lastActivationCheck!.warnings.isNotEmpty) ...[
                SizedBox(height: spacing.sm),
                ..._lastActivationCheck!.warnings.map((item) => Text('Warning: $item')),
              ],
            ],
          ],
        ),
    };

    return Column(
      children: [
        panel,
        SizedBox(height: spacing.lg),
        _buildStageNavigation(),
      ],
    );
  }

  Widget _buildStageNavigation() {
    final spacing = context.owuiSpacing;
    final stages = _SetupWizardStage.values;
    final currentIndex = stages.indexOf(_selectedStage);
    final prevStage = currentIndex > 0 ? stages[currentIndex - 1] : null;
    final nextStage = currentIndex < stages.length - 1 ? stages[currentIndex + 1] : null;
    return OwuiCard(
      padding: EdgeInsets.all(spacing.md),
      child: Row(
        children: [
          Expanded(
            child: OutlinedButton.icon(
              onPressed: prevStage == null
                  ? null
                  : () {
                      setState(() {
                        _selectedStage = prevStage;
                      });
                    },
              icon: const Icon(Icons.arrow_back),
              label: const Text('上一步'),
            ),
          ),
          SizedBox(width: spacing.md),
          Expanded(
            child: FilledButton.icon(
              onPressed: nextStage == null
                  ? null
                  : () {
                      setState(() {
                        _selectedStage = nextStage;
                      });
                    },
              icon: const Icon(Icons.arrow_forward),
              label: Text(nextStage == null ? '完成' : '下一步'),
            ),
          ),
        ],
      ),
    );
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

  List<Map<String, dynamic>> _worldFoundationEntries(RpSetupWorkspace workspace) {
    return _foundationEntries(workspace)
        .where((item) => (item['domain']?.toString() ?? '') != 'character')
        .toList();
  }

  List<Map<String, dynamic>> _characterFoundationEntries(RpSetupWorkspace workspace) {
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
                      : (entry['path']?.toString() ?? entry['entry_id']?.toString() ?? '未命名条目'),
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
    final chapterBlueprints = (blueprint['chapter_blueprints'] as List? ?? const [])
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
        label: 'Notes',
        value: config['notes']?.toString(),
      ),
    ];
  }

  List<Widget> _buildOverviewWidgets(RpSetupWorkspace workspace) {
    final spacing = context.owuiSpacing;
    return [
      Text('Story: ${workspace.storyId}'),
      Text('Mode: ${workspace.mode}'),
      Text('Workspace State: ${workspace.workspaceState}'),
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
      SizedBox(height: spacing.md),
      Text(
        'Accepted Commits',
        style: Theme.of(context).textTheme.titleSmall,
      ),
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
  })  : thinking = '',
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
