import 'dart:convert';
import 'dart:typed_data';

import 'package:chatboxapp/services/backend_rp_retrieval_service.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('BackendRpRetrievalService graph endpoints', () {
    test('getGraphMaintenance parses maintenance snapshot', () async {
      final adapter = _GraphRetrievalAdapter();
      final dio = Dio()..httpClientAdapter = adapter;
      final service = BackendRpRetrievalService(
        dio: dio,
        baseUrl: 'http://example.test',
      );

      final snapshot = await service.getGraphMaintenance('story-1');

      expect(
        adapter.paths,
        contains('/api/rp/retrieval/stories/story-1/graph/maintenance'),
      );
      expect(snapshot.storyId, 'story-1');
      expect(snapshot.graphBackend, 'postgres_lightweight');
      expect(snapshot.nodeCount, 2);
      expect(snapshot.graphExtractionConfigured, isFalse);
      expect(snapshot.maintenanceWarnings, ['model_config_missing']);
    });

    test('getGraphNeighborhood sends bounds and parses response', () async {
      final adapter = _GraphRetrievalAdapter();
      final dio = Dio()..httpClientAdapter = adapter;
      final service = BackendRpRetrievalService(
        dio: dio,
        baseUrl: 'http://example.test',
      );

      final neighborhood = await service.getGraphNeighborhood(
        'story-1',
        nodeId: 'node-1',
        maxDepth: 1,
        maxNodes: 10,
        maxEdges: 12,
      );

      expect(
        adapter.paths,
        contains('/api/rp/retrieval/stories/story-1/graph/neighborhood'),
      );
      expect(adapter.lastQueryParameters['node_id'], 'node-1');
      expect(adapter.lastQueryParameters['max_depth'], 1);
      expect(adapter.lastQueryParameters['max_nodes'], 10);
      expect(adapter.lastQueryParameters['max_edges'], 12);
      expect(neighborhood.storyId, 'story-1');
      expect(neighborhood.maxDepth, 1);
      expect(neighborhood.nodes, isEmpty);
      expect(neighborhood.edges, isEmpty);
      expect(neighborhood.evidence, isEmpty);
    });
  });
}

class _GraphRetrievalAdapter implements HttpClientAdapter {
  final List<String> paths = [];
  Map<String, dynamic> lastQueryParameters = const {};

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    paths.add(options.uri.path);
    lastQueryParameters = Map<String, dynamic>.from(options.queryParameters);

    if (options.uri.path.endsWith('/graph/maintenance')) {
      return _jsonResponse({
        'story_id': 'story-1',
        'graph_backend': 'postgres_lightweight',
        'graph_extraction_enabled': true,
        'graph_extraction_configured': false,
        'graph_extraction_model_config_ref': null,
        'graph_extraction_provider_id': null,
        'graph_extraction_model_id': null,
        'maintenance_warnings': ['model_config_missing'],
        'source_layers': ['archival'],
        'node_count': 2,
        'edge_count': 1,
        'evidence_count': 1,
        'job_count': 0,
        'queued_job_count': 0,
        'running_job_count': 0,
        'completed_job_count': 0,
        'failed_job_count': 0,
        'skipped_job_count': 0,
        'cancelled_job_count': 0,
        'retryable_job_ids': [],
        'warning_code_counts': {},
        'error_code_counts': {},
        'recent_jobs': [],
      });
    }

    if (options.uri.path.endsWith('/graph/neighborhood')) {
      return _jsonResponse({
        'story_id': 'story-1',
        'graph_backend': 'postgres_lightweight',
        'source_layer': 'archival',
        'anchor_node_id': options.queryParameters['node_id'],
        'max_depth': options.queryParameters['max_depth'],
        'truncated': false,
        'warnings': [],
        'nodes': [],
        'edges': [],
        'evidence': [],
      });
    }

    return _jsonResponse({'error': 'not found'}, statusCode: 404);
  }

  ResponseBody _jsonResponse(
    Map<String, dynamic> body, {
    int statusCode = 200,
  }) {
    return ResponseBody.fromString(
      jsonEncode(body),
      statusCode,
      headers: {
        Headers.contentTypeHeader: ['application/json'],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}
