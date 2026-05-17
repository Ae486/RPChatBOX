import 'package:flutter/material.dart';

import '../chat_ui/owui/components/owui_snack_bar.dart';
import '../chat_ui/owui/owui_tokens_ext.dart';
import '../models/story_runtime.dart';

typedef BrainstormAddItemCallback =
    Future<RpBrainstormSession> Function(String batchId, String text);
typedef BrainstormUpdateItemCallback =
    Future<RpBrainstormSession> Function({
      required String batchId,
      required String itemId,
      String? text,
      String? status,
    });
typedef BrainstormSubmitBatchCallback =
    Future<RpBrainstormSession> Function(String batchId);

class StoryBrainstormBatchesDialog extends StatefulWidget {
  final RpBrainstormSession? initialSession;
  final BrainstormAddItemCallback onAddItem;
  final BrainstormUpdateItemCallback onUpdateItem;
  final BrainstormSubmitBatchCallback onSubmitBatch;

  const StoryBrainstormBatchesDialog({
    super.key,
    required this.initialSession,
    required this.onAddItem,
    required this.onUpdateItem,
    required this.onSubmitBatch,
  });

  @override
  State<StoryBrainstormBatchesDialog> createState() =>
      _StoryBrainstormBatchesDialogState();
}

class _StoryBrainstormBatchesDialogState
    extends State<StoryBrainstormBatchesDialog> {
  RpBrainstormSession? _session;
  final Map<String, String> _draftTexts = <String, String>{};
  final Map<String, TextEditingController> _newItemControllers =
      <String, TextEditingController>{};
  String? _selectedItemId;
  String? _hoveredItemId;
  bool _isBusy = false;

  @override
  void initState() {
    super.initState();
    _session = widget.initialSession;
  }

  @override
  void dispose() {
    for (final controller in _newItemControllers.values) {
      controller.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final spacing = context.owuiSpacing;
    return Dialog(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 820, maxHeight: 760),
        child: Padding(
          padding: EdgeInsets.all(spacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      'Brainstorm 变更项',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                  ),
                  IconButton(
                    onPressed: () => Navigator.of(context).pop(),
                    icon: const Icon(Icons.close),
                  ),
                ],
              ),
              SizedBox(height: spacing.md),
              Expanded(
                child: _session == null || _session!.batches.isEmpty
                    ? _buildEmptyState()
                    : ListView(
                        children: [
                          for (final batch in _session!.batches.reversed)
                            _buildBatchCard(batch),
                        ],
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Text(
        '暂无 brainstorm batch。\n先在右侧讨论，再点击“总结变更项”。',
        textAlign: TextAlign.center,
      ),
    );
  }

  Widget _buildBatchCard(RpBrainstormBatch batch) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    final controller = _newItemControllers.putIfAbsent(
      batch.batchId,
      () => TextEditingController(),
    );
    return Container(
      margin: EdgeInsets.only(bottom: spacing.md),
      padding: EdgeInsets.all(spacing.md),
      decoration: BoxDecoration(
        color: colors.surface2,
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
                      batch.batchId,
                      style: Theme.of(context).textTheme.labelMedium?.copyWith(
                        color: colors.textSecondary,
                      ),
                    ),
                    SizedBox(height: spacing.xs),
                    Text(
                      '状态: ${batch.status} · ${batch.items.length} 条',
                      style: Theme.of(context).textTheme.titleSmall,
                    ),
                  ],
                ),
              ),
              FilledButton.tonal(
                onPressed: _isBusy || batch.frozen || batch.activeItemCount == 0
                    ? null
                    : () => _submitBatch(batch.batchId),
                child: const Text('提交处理'),
              ),
            ],
          ),
          SizedBox(height: spacing.md),
          for (final item in batch.items)
            _buildItemRow(batch: batch, item: item),
          if (!batch.frozen) ...[
            SizedBox(height: spacing.sm),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: controller,
                    minLines: 1,
                    maxLines: 3,
                    decoration: const InputDecoration(labelText: '新增变更项'),
                  ),
                ),
                SizedBox(width: spacing.sm),
                IconButton(
                  onPressed: _isBusy
                      ? null
                      : () => _addItem(batch.batchId, controller),
                  icon: const Icon(Icons.add_circle_outline),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildItemRow({
    required RpBrainstormBatch batch,
    required RpBrainstormBatchItem item,
  }) {
    final spacing = context.owuiSpacing;
    final isSelected = _selectedItemId == item.itemId;
    final isHovered = _hoveredItemId == item.itemId;
    final showAction = isSelected || isHovered;
    final draftValue = _draftTexts[item.itemId] ?? item.text;
    return MouseRegion(
      onEnter: (_) => setState(() => _hoveredItemId = item.itemId),
      onExit: (_) => setState(() {
        if (_hoveredItemId == item.itemId) {
          _hoveredItemId = null;
        }
      }),
      child: GestureDetector(
        onTap: () => setState(() => _selectedItemId = item.itemId),
        child: Container(
          margin: EdgeInsets.only(bottom: spacing.sm),
          padding: EdgeInsets.all(spacing.sm),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(context.owuiRadius.rLg),
            border: Border.all(
              color: isSelected
                  ? Theme.of(context).colorScheme.primary
                  : context.owuiColors.borderSubtle,
            ),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: TextFormField(
                  key: ValueKey('${item.itemId}:${item.status}:${item.text}'),
                  initialValue: draftValue,
                  enabled: item.isEditable && !batch.frozen && !_isBusy,
                  minLines: 1,
                  maxLines: 4,
                  onChanged: (value) {
                    _draftTexts[item.itemId] = value;
                  },
                  style: TextStyle(
                    decoration: item.isDeleted
                        ? TextDecoration.lineThrough
                        : TextDecoration.none,
                    color: item.isDeleted
                        ? context.owuiColors.textSecondary
                        : null,
                  ),
                ),
              ),
              if (item.isEditable &&
                  !batch.frozen &&
                  draftValue.trim() != item.text &&
                  !_isBusy)
                IconButton(
                  onPressed: () => _saveItemText(
                    batchId: batch.batchId,
                    itemId: item.itemId,
                    text: draftValue,
                  ),
                  icon: const Icon(Icons.save_outlined),
                ),
              if (showAction && !batch.frozen)
                IconButton(
                  onPressed: _isBusy
                      ? null
                      : () => _toggleItemStatus(
                          batchId: batch.batchId,
                          item: item,
                        ),
                  icon: Icon(
                    item.isDeleted
                        ? Icons.restore_outlined
                        : Icons.delete_outline,
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _addItem(
    String batchId,
    TextEditingController controller,
  ) async {
    final text = controller.text.trim();
    if (text.isEmpty) return;
    await _runMutation(() => widget.onAddItem(batchId, text));
    controller.clear();
  }

  Future<void> _saveItemText({
    required String batchId,
    required String itemId,
    required String text,
  }) async {
    final normalized = text.trim();
    if (normalized.isEmpty) return;
    await _runMutation(
      () => widget.onUpdateItem(
        batchId: batchId,
        itemId: itemId,
        text: normalized,
      ),
    );
  }

  Future<void> _toggleItemStatus({
    required String batchId,
    required RpBrainstormBatchItem item,
  }) async {
    final nextStatus = item.isDeleted ? 'active' : 'deleted';
    await _runMutation(
      () => widget.onUpdateItem(
        batchId: batchId,
        itemId: item.itemId,
        status: nextStatus,
      ),
    );
  }

  Future<void> _submitBatch(String batchId) async {
    await _runMutation(() => widget.onSubmitBatch(batchId));
  }

  Future<void> _runMutation(
    Future<RpBrainstormSession> Function() operation,
  ) async {
    setState(() => _isBusy = true);
    try {
      final session = await operation();
      if (!mounted) return;
      setState(() {
        _session = session;
        _isBusy = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _isBusy = false);
      OwuiSnackBars.error(context, message: 'Brainstorm 操作失败: $error');
    }
  }
}
