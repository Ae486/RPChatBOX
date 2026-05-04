import 'package:dio/dio.dart';

import '../models/rp_retrieval.dart';
import 'dio_service.dart';

class BackendRpRetrievalService {
  static const String defaultBaseUrl = 'http://localhost:8765';

  final Dio _controlDio;
  final String _baseUrl;

  BackendRpRetrievalService({Dio? dio, String? baseUrl})
    : _controlDio = dio ?? DioService().controlPlaneDio,
      _baseUrl = baseUrl ?? defaultBaseUrl;

  Future<RpRetrievalStoryMaintenanceSnapshot> getStoryMaintenance(
    String storyId,
  ) async {
    final response = await _controlDio.get(
      '$_baseUrl/api/rp/retrieval/stories/$storyId/maintenance',
    );
    _ensureSuccess(response, action: 'get retrieval story maintenance');
    return RpRetrievalStoryMaintenanceSnapshot.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<RpMemoryGraphMaintenanceSnapshot> getGraphMaintenance(
    String storyId,
  ) async {
    final response = await _controlDio.get(
      '$_baseUrl/api/rp/retrieval/stories/$storyId/graph/maintenance',
    );
    _ensureSuccess(response, action: 'get memory graph maintenance');
    return RpMemoryGraphMaintenanceSnapshot.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<RpMemoryGraphNeighborhoodResponse> getGraphNeighborhood(
    String storyId, {
    String? nodeId,
    int maxDepth = 1,
    int maxNodes = 30,
    int maxEdges = 50,
  }) async {
    final response = await _controlDio.get(
      '$_baseUrl/api/rp/retrieval/stories/$storyId/graph/neighborhood',
      queryParameters: {
        if (nodeId != null && nodeId.isNotEmpty) 'node_id': nodeId,
        'max_depth': maxDepth,
        'max_nodes': maxNodes,
        'max_edges': maxEdges,
      },
    );
    _ensureSuccess(response, action: 'get memory graph neighborhood');
    return RpMemoryGraphNeighborhoodResponse.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<List<RpRetrievalIndexJob>> reindexStory(
    String storyId, {
    String? collectionId,
    String? collectionKind,
  }) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/retrieval/stories/$storyId/reindex',
      data: {
        if (collectionId != null) 'collection_id': collectionId,
        if (collectionKind != null) 'collection_kind': collectionKind,
      },
    );
    _ensureSuccess(response, action: 'reindex retrieval story');
    return _parseJobListResponse(response.data);
  }

  Future<List<RpRetrievalIndexJob>> reindexCollection(
    String collectionId,
  ) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/retrieval/collections/$collectionId/reindex',
    );
    _ensureSuccess(response, action: 'reindex retrieval collection');
    return _parseJobListResponse(response.data);
  }

  Future<List<RpRetrievalIndexJob>> backfillStoryEmbeddings(
    String storyId,
  ) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/retrieval/stories/$storyId/backfill',
    );
    _ensureSuccess(response, action: 'backfill retrieval story embeddings');
    return _parseJobListResponse(response.data);
  }

  Future<List<RpRetrievalIndexJob>> backfillCollectionEmbeddings(
    String collectionId,
  ) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/retrieval/collections/$collectionId/backfill',
    );
    _ensureSuccess(
      response,
      action: 'backfill retrieval collection embeddings',
    );
    return _parseJobListResponse(response.data);
  }

  Future<RpRetrievalRetryBatchResult> retryFailedStoryJobs(
    String storyId, {
    String? collectionId,
    String? collectionKind,
    int? limit,
  }) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/retrieval/stories/$storyId/retry-failed',
      data: {
        if (collectionId != null) 'collection_id': collectionId,
        if (collectionKind != null) 'collection_kind': collectionKind,
        if (limit != null) 'limit': limit,
      },
    );
    _ensureSuccess(response, action: 'retry failed retrieval story jobs');
    return RpRetrievalRetryBatchResult.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<RpRetrievalRetryBatchResult> retryFailedCollectionJobs(
    String collectionId, {
    int? limit,
  }) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/retrieval/collections/$collectionId/retry-failed',
      data: {if (limit != null) 'limit': limit},
    );
    _ensureSuccess(response, action: 'retry failed retrieval collection jobs');
    return RpRetrievalRetryBatchResult.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<RpRetrievalIndexJob> retryJob(String jobId) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/retrieval/jobs/$jobId/retry',
    );
    _ensureSuccess(response, action: 'retry retrieval job');
    return RpRetrievalIndexJob.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  List<RpRetrievalIndexJob> _parseJobListResponse(dynamic data) {
    final payload = Map<String, dynamic>.from(data as Map);
    final items = payload['data'] as List? ?? const [];
    return items
        .whereType<Map>()
        .map(
          (item) =>
              RpRetrievalIndexJob.fromJson(Map<String, dynamic>.from(item)),
        )
        .toList();
  }

  void _ensureSuccess(Response response, {required String action}) {
    final statusCode = response.statusCode ?? 0;
    if (statusCode >= 200 && statusCode < 300) return;
    throw Exception('Failed to $action (HTTP $statusCode)');
  }
}
