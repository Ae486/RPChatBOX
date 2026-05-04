import 'package:chatboxapp/models/rp_retrieval.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('RpMemoryGraphMaintenanceSnapshot', () {
    test('parses graph counts, config status, and recent jobs', () {
      final snapshot = RpMemoryGraphMaintenanceSnapshot.fromJson({
        'story_id': 'story-1',
        'graph_backend': 'postgres_lightweight',
        'graph_extraction_enabled': true,
        'graph_extraction_configured': true,
        'graph_extraction_model_config_ref': 'graph:provider:model',
        'graph_extraction_provider_id': 'provider-graph',
        'graph_extraction_model_id': 'model-graph',
        'maintenance_warnings': ['mapped_to_related_to'],
        'source_layers': ['archival'],
        'node_count': 2,
        'edge_count': 1,
        'evidence_count': 3,
        'job_count': 4,
        'queued_job_count': 1,
        'running_job_count': 0,
        'completed_job_count': 2,
        'failed_job_count': 1,
        'skipped_job_count': 0,
        'cancelled_job_count': 0,
        'retryable_job_ids': ['job-failed'],
        'warning_code_counts': {'mapped_to_related_to': 2},
        'error_code_counts': {'provider_unavailable': 1},
        'recent_jobs': [
          {
            'graph_job_id': 'job-failed',
            'story_id': 'story-1',
            'workspace_id': 'workspace-1',
            'session_id': null,
            'commit_id': 'commit-1',
            'source_layer': 'archival',
            'source_asset_id': 'asset-1',
            'chunk_id': 'chunk-1',
            'section_id': 'section-1',
            'input_fingerprint': 'fp',
            'status': 'failed',
            'attempt_count': 2,
            'model_config_ref': 'graph:provider:model',
            'provider_id': 'provider-graph',
            'model_id': 'model-graph',
            'extraction_schema_version': 'graph_extraction.v1',
            'taxonomy_version': 'graph_taxonomy.v1',
            'token_usage': {'total_tokens': 128},
            'warning_codes': ['mapped_to_related_to'],
            'error_code': 'provider_unavailable',
            'error_message': 'provider offline',
            'queued_reason': 'manual_retry',
            'retry_after': null,
            'created_at': '2026-05-01T00:00:00Z',
            'updated_at': '2026-05-01T00:01:00Z',
            'completed_at': null,
          },
        ],
      });

      expect(snapshot.storyId, 'story-1');
      expect(snapshot.graphExtractionConfigured, isTrue);
      expect(snapshot.nodeCount, 2);
      expect(snapshot.edgeCount, 1);
      expect(snapshot.evidenceCount, 3);
      expect(snapshot.retryableJobIds, ['job-failed']);
      expect(snapshot.warningCodeCounts['mapped_to_related_to'], 2);
      expect(snapshot.errorCodeCounts['provider_unavailable'], 1);
      expect(snapshot.recentJobs, hasLength(1));
      expect(snapshot.recentJobs.single.isFailed, isTrue);
      expect(snapshot.recentJobs.single.tokenUsage['total_tokens'], 128);
    });
  });

  group('RpMemoryGraphNeighborhoodResponse', () {
    test('parses nodes, edges, evidence, warnings, and bounded flags', () {
      final neighborhood = RpMemoryGraphNeighborhoodResponse.fromJson({
        'story_id': 'story-1',
        'graph_backend': 'postgres_lightweight',
        'source_layer': 'archival',
        'anchor_node_id': 'node-1',
        'max_depth': 1,
        'truncated': true,
        'warnings': ['graph_neighborhood_truncated'],
        'nodes': [
          {
            'id': 'node-1',
            'label': 'Aileen',
            'type': 'character',
            'story_id': 'story-1',
            'workspace_id': 'workspace-1',
            'session_id': null,
            'source_layer': 'archival',
            'source_status': 'source_reference',
            'confidence': 0.82,
            'aliases': ['Ail'],
            'description': 'Source-grounded character note.',
            'first_seen_source_ref': 'setup_commit:commit-1:aileen',
            'entity_schema_version': 'entity.v1',
            'normalization_key': 'character:aileen',
            'metadata': {'domain': 'character'},
            'created_at': '2026-05-01T00:00:00Z',
            'updated_at': '2026-05-01T00:01:00Z',
          },
          {
            'id': 'node-2',
            'label': 'Order of Dawn',
            'type': 'faction_or_org',
            'story_id': 'story-1',
            'workspace_id': 'workspace-1',
            'session_id': null,
            'source_layer': 'archival',
            'source_status': 'source_reference',
            'confidence': 0.74,
            'aliases': [],
            'description': null,
            'first_seen_source_ref': null,
            'entity_schema_version': 'entity.v1',
            'normalization_key': 'faction:order-of-dawn',
            'metadata': {},
            'created_at': '2026-05-01T00:00:00Z',
            'updated_at': '2026-05-01T00:01:00Z',
          },
        ],
        'edges': [
          {
            'id': 'edge-1',
            'story_id': 'story-1',
            'workspace_id': 'workspace-1',
            'session_id': null,
            'source': 'node-1',
            'target': 'node-2',
            'source_entity_name': 'Aileen',
            'target_entity_name': 'Order of Dawn',
            'label': 'affiliated_with',
            'relation_family': 'stable_setup',
            'relation_schema_version': 'relation.v1',
            'raw_relation_text': 'protected by the Order',
            'source_layer': 'archival',
            'source_status': 'source_reference',
            'confidence': 0.74,
            'direction': 'directed',
            'valid_from': null,
            'valid_to': null,
            'branch_id': null,
            'canon_status': 'source_reference',
            'evidence_count': 2,
            'metadata': {'raw': true},
            'created_at': '2026-05-01T00:00:00Z',
            'updated_at': '2026-05-01T00:01:00Z',
          },
        ],
        'evidence': [
          {
            'id': 'evidence-edge',
            'story_id': 'story-1',
            'workspace_id': 'workspace-1',
            'node_id': null,
            'edge_id': 'edge-1',
            'source_layer': 'archival',
            'source_family': 'setup_source',
            'source_type': 'foundation_entry',
            'import_event': 'setup.commit_ingest',
            'source_ref': 'setup_commit:commit-1:aileen',
            'source_asset_id': 'asset-1',
            'collection_id': 'collection-1',
            'parsed_document_id': 'doc-1',
            'chunk_id': 'chunk-1',
            'section_id': 'section-1',
            'domain': 'character',
            'domain_path': 'foundation.character.aileen',
            'commit_id': 'commit-1',
            'step_id': 'foundation',
            'char_start': 0,
            'char_end': 43,
            'excerpt': 'Aileen is protected by the Order.',
            'metadata': {'page_ref': 'p1'},
            'created_at': '2026-05-01T00:00:00Z',
            'updated_at': '2026-05-01T00:01:00Z',
          },
          {
            'id': 'evidence-node',
            'story_id': 'story-1',
            'workspace_id': 'workspace-1',
            'node_id': 'node-1',
            'edge_id': null,
            'source_layer': 'archival',
            'source_family': 'setup_source',
            'source_type': 'foundation_entry',
            'import_event': 'setup.commit_ingest',
            'source_ref': 'setup_commit:commit-1:aileen',
            'source_asset_id': 'asset-1',
            'collection_id': 'collection-1',
            'parsed_document_id': 'doc-1',
            'chunk_id': 'chunk-1',
            'section_id': 'section-1',
            'domain': 'character',
            'domain_path': 'foundation.character.aileen',
            'commit_id': 'commit-1',
            'step_id': 'foundation',
            'char_start': null,
            'char_end': null,
            'excerpt': 'Aileen appears in the setup source.',
            'metadata': {},
            'created_at': '2026-05-01T00:00:00Z',
            'updated_at': '2026-05-01T00:01:00Z',
          },
        ],
      });

      expect(neighborhood.storyId, 'story-1');
      expect(neighborhood.anchorNodeId, 'node-1');
      expect(neighborhood.truncated, isTrue);
      expect(neighborhood.warnings, ['graph_neighborhood_truncated']);
      expect(neighborhood.nodes, hasLength(2));
      expect(neighborhood.nodes.first.aliases, ['Ail']);
      expect(neighborhood.edges.single.label, 'affiliated_with');
      expect(neighborhood.edges.single.evidenceCount, 2);
      expect(neighborhood.evidenceForEdge('edge-1').single.chunkId, 'chunk-1');
      expect(
        neighborhood.evidenceForNode('node-1').single.excerpt,
        'Aileen appears in the setup source.',
      );
    });
  });
}
