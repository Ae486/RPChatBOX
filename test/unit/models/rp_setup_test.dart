import 'package:chatboxapp/models/rp_setup.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('RpSetupWorkspace', () {
    test('parses stage contract fields from backend payload', () {
      final updatedAt = DateTime(2026, 5, 4, 12, 0, 0);
      final json = <String, dynamic>{
        'workspace_id': 'ws-1',
        'story_id': 'story-1',
        'mode': 'longform',
        'workspace_state': 'discussing',
        'current_step': 'foundation',
        'current_stage': 'world_background',
        'stage_plan': [
          'world_background',
          'character_design',
          'plot_blueprint',
          'writer_config',
          'worker_config',
          'overview',
          'activate',
        ],
        'step_states': [
          {
            'step_id': 'foundation',
            'state': 'discussing',
            'discussion_round': 2,
            'review_round': 1,
            'last_proposal_id': 'proposal-1',
            'last_commit_id': 'commit-1',
            'updated_at': updatedAt.toIso8601String(),
          },
        ],
        'stage_states': [
          {
            'stage_id': 'world_background',
            'state': 'discussing',
            'discussion_round': 2,
            'review_round': 1,
            'last_proposal_id': 'proposal-1',
            'last_commit_id': 'commit-1',
            'updated_at': updatedAt.toIso8601String(),
          },
        ],
        'draft_blocks': {
          'world_background': {
            'stage_id': 'world_background',
            'entries': [
              {
                'entry_id': 'world-rule-1',
                'entry_type': 'world_rule',
                'semantic_path': 'world/rule/magic',
                'title': 'Magic Rule',
                'display_label': 'Magic Rule',
                'summary': 'Magic stays rare.',
                'aliases': ['rare magic'],
                'tags': ['world', 'rule'],
                'sections': [
                  {
                    'section_id': 'summary',
                    'title': '概要',
                    'kind': 'text',
                    'content': {'text': 'Magic stays rare.'},
                    'retrieval_role': 'summary',
                    'tags': ['world'],
                  },
                ],
              },
            ],
            'notes': 'keep this stable',
          },
        },
        'story_config_draft': {
          'model_profile_ref': 'model-profile-1',
          'worker_profile_ref': 'worker-profile-1',
          'post_write_policy_preset': 'default',
        },
        'writing_contract_draft': null,
        'foundation_draft': null,
        'longform_blueprint_draft': null,
        'imported_assets': const [],
        'commit_proposals': const [],
        'accepted_commits': const [],
        'retrieval_ingestion_jobs': const [],
        'readiness_status': {
          'step_readiness': const {},
          'blocking_issues': const [],
          'warnings': const [],
        },
        'activated_story_session_id': null,
        'version': 7,
        'updated_at': updatedAt.toIso8601String(),
      };

      final workspace = RpSetupWorkspace.fromJson(json);

      expect(workspace.currentStage, equals('world_background'));
      expect(
        workspace.stagePlan,
        equals([
          'world_background',
          'character_design',
          'plot_blueprint',
          'writer_config',
          'worker_config',
          'overview',
          'activate',
        ]),
      );
      expect(workspace.stageStates, hasLength(1));
      expect(workspace.stageStates.first.stageId, equals('world_background'));
      expect(workspace.stageBlock('world_background'), isNotNull);
      expect(
        workspace.stageBlock('world_background')!.entries.first.summary,
        equals('Magic stays rare.'),
      );
      expect(
        workspace.stageBlock('world_background')!.notes,
        equals('keep this stable'),
      );
      expect(
        workspace.storyConfigDraft?['model_profile_ref'],
        equals('model-profile-1'),
      );
      expect(workspace.version, equals(7));
      expect(workspace.updatedAt, equals(updatedAt));
    });

    test('keeps legacy fields usable when new stage fields are absent', () {
      final updatedAt = DateTime(2026, 5, 4, 12, 30, 0);
      final json = <String, dynamic>{
        'workspace_id': 'ws-legacy',
        'story_id': 'story-legacy',
        'mode': 'longform',
        'workspace_state': 'discussing',
        'current_step': 'foundation',
        'step_states': const [],
        'story_config_draft': const {},
        'writing_contract_draft': const {},
        'foundation_draft': const {},
        'longform_blueprint_draft': const {},
        'imported_assets': const [],
        'commit_proposals': const [],
        'accepted_commits': const [],
        'retrieval_ingestion_jobs': const [],
        'readiness_status': {
          'step_readiness': const {},
          'blocking_issues': const [],
          'warnings': const [],
        },
        'activated_story_session_id': null,
        'version': 1,
        'updated_at': updatedAt.toIso8601String(),
      };

      final workspace = RpSetupWorkspace.fromJson(json);

      expect(workspace.currentStage, isNull);
      expect(workspace.stagePlan, isEmpty);
      expect(workspace.stageStates, isEmpty);
      expect(workspace.stageDraftBlocks, isEmpty);
      expect(workspace.foundationDraft, isNotNull);
      expect(workspace.version, equals(1));
    });
  });
}
