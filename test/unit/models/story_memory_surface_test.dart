import 'package:chatboxapp/models/story_runtime.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('memory inspection keeps backend canonical envelope fields', () {
    final inspection = RpMemoryInspection.fromJson({
      'identity': {
        'story_id': 'story-1',
        'session_id': 'session-1',
        'branch_head_id': 'branch:session-1:main',
        'turn_id': 'turn-7',
        'runtime_profile_snapshot_id': 'snapshot-1',
      },
      'branch_scope': {
        'active_branch_head_id': 'branch:session-1:main',
        'selected_turn_id': 'turn-7',
      },
      'canonical_envelope': {
        'schema_version': 'rp.memory.display.v1',
        'governance_bound': true,
      },
      'blocks': [
        {
          'block_id': 'block.chapter.current',
          'domain': 'chapter',
          'layer': 'core_state.authoritative',
          'scope': 'story',
          'visibility': {'visibility_scope': 'active_runtime_identity'},
          'revision': 3,
          'permission_level': {'direct_edit': true},
          'lifecycle_state': 'active',
          'source_refs': [
            {
              'source_type': 'core_state_block',
              'source_id': 'block.chapter.current',
              'metadata': {'label': 'chapter.current'},
            },
          ],
          'validation_summary': {'state': 'valid'},
          'editable_fields': ['title'],
          'allowed_actions': ['inspect', 'direct_core_edit'],
          'entrypoints': {
            'direct_core_edit': {'path_template': '/memory/core/direct-edit'},
          },
          'entries': [
            {
              'entry_id': 'block.chapter.current:current',
              'entry_type': 'core_state_object',
              'current_value': {'title': 'Visible Core'},
              'editable_fields': ['title'],
              'base_revision': 3,
              'conflict_state': 'none',
              'source_refs': [],
              'allowed_actions': ['direct_core_edit'],
            },
          ],
        },
      ],
      'layers': {
        'core_state.authoritative': {'count': 1, 'items': []},
      },
      'boundaries': ['core_direct_edit_routes_through_shared_mutation_kernel'],
    });

    expect(inspection.schemaVersion, 'rp.memory.display.v1');
    expect(inspection.activeBranchHeadId, 'branch:session-1:main');
    expect(inspection.cutoffTurnId, 'turn-7');
    expect(inspection.runtimeProfileSnapshotId, 'snapshot-1');
    expect(inspection.blocks.single.layer, 'core_state.authoritative');
    expect(
      inspection.blocks.single.allowedActions,
      contains('direct_core_edit'),
    );
    expect(inspection.blocks.single.entries.single.baseRevision, 3);
    expect(
      inspection.blocks.single.entrypoints['direct_core_edit'],
      containsPair('path_template', '/memory/core/direct-edit'),
    );
  });

  test('memory action response exposes backend refresh contracts', () {
    final response = RpMemoryActionResponse.fromJson({
      'session_id': 'session-1',
      'item': {'proposal_id': 'proposal-1', 'status': 'applied'},
      'action_metadata': {
        'schema_version': 'rp.memory.action_receipt.v1',
        'action': 'direct_core_edit',
        'governed_by': 'StoryBlockMutationService.direct_edit_block',
        'affected_refs': ['proposal-1', 'chapter.current'],
      },
      'refresh': {
        'memory_inspection': {
          'method': 'GET',
          'path_template': '/memory/inspection',
          'query_params': {
            'branch_head_id': 'branch:session-1:main',
            'turn_id': 'turn-7',
            'runtime_profile_snapshot_id': 'snapshot-1',
          },
        },
        'runtime_inspect': {
          'method': 'GET',
          'path_template': '/runtime/inspect',
          'query_params': {'branch_head_id': 'branch:session-1:main'},
        },
      },
    });

    expect(response.schemaVersion, 'rp.memory.action_receipt.v1');
    expect(response.action, 'direct_core_edit');
    expect(response.governedBy, 'StoryBlockMutationService.direct_edit_block');
    expect(response.affectedRefs, contains('proposal-1'));
    expect(
      response.memoryInspectionRefresh['query_params'],
      containsPair('turn_id', 'turn-7'),
    );
    expect(response.runtimeInspectRefresh['path_template'], '/runtime/inspect');
  });
}
