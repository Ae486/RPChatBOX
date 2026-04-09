import 'dart:async';

import 'package:flutter/foundation.dart';

import '../models/provider_config.dart';
import '../models/model_config.dart';
import '../services/circuit_breaker_service.dart';
import '../services/fallback_policy.dart';
import 'ai_provider.dart';

/// Provider that routes requests through proxy with automatic fallback.
///
/// Implements the 'auto' backend mode:
/// - Primary: Route through Python backend proxy
/// - Fallback: Direct connection to LLM API on proxy failure
/// - Circuit breaker: Prevent repeated failures
class BackendRoutingProvider extends AIProvider {
  final AIProvider directProvider;
  final AIProvider proxyProvider;
  final CircuitBreaker circuitBreaker;
  final bool fallbackEnabled;

  BackendRoutingProvider({
    required ProviderConfig config,
    required this.directProvider,
    required this.proxyProvider,
    required this.circuitBreaker,
    this.fallbackEnabled = true,
  }) : super(config);

  @override
  Future<ProviderTestResult> testConnection() async {
    // Try proxy first
    if (!circuitBreaker.isOpen) {
      final proxyResult = await proxyProvider.testConnection();
      if (proxyResult.success) {
        circuitBreaker.recordSuccess();
        return proxyResult;
      }
      circuitBreaker.recordFailure();
    }

    // Fallback to direct
    if (fallbackEnabled) {
      return directProvider.testConnection();
    }

    return ProviderTestResult.failure(
      'Proxy unavailable and fallback disabled',
    );
  }

  @override
  Future<List<String>> listAvailableModels() async {
    // Try proxy first
    if (!circuitBreaker.isOpen) {
      try {
        final models = await proxyProvider.listAvailableModels();
        if (models.isNotEmpty) {
          circuitBreaker.recordSuccess();
          return models;
        }
      } catch (e) {
        circuitBreaker.recordFailure();
      }
    }

    // Fallback to direct
    if (fallbackEnabled) {
      return directProvider.listAvailableModels();
    }

    return [];
  }

  @override
  Stream<String> sendMessageStream({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
    String? modelId,
  }) async* {
    // Check circuit breaker state
    if (circuitBreaker.shouldFallback && fallbackEnabled) {
      debugPrint('[ROUTE] Auto 模式 → 熔断器开启，回退直连');
      // Circuit is open, go directly to fallback
      yield* directProvider.sendMessageStream(
        model: model,
        messages: messages,
        parameters: parameters,
        files: files,
        modelId: modelId,
      );
      return;
    }

    bool hasEmittedChunk = false;

    try {
      // Handle half-open state
      if (circuitBreaker.state == CircuitState.halfOpen) {
        if (!circuitBreaker.allowProbe) {
          // Max probes reached, use fallback
          if (fallbackEnabled) {
            yield* directProvider.sendMessageStream(
              model: model,
              messages: messages,
              parameters: parameters,
              files: files,
              modelId: modelId,
            );
            return;
          }
        }
        circuitBreaker.incrementHalfOpenCalls();
      }

      // Try proxy
      debugPrint('[ROUTE] Auto 模式 → 尝试 Python 后端代理');
      await for (final chunk in proxyProvider.sendMessageStream(
        model: model,
        messages: messages,
        parameters: parameters,
        files: files,
        modelId: modelId,
      )) {
        hasEmittedChunk = true;
        circuitBreaker.recordSuccess();
        yield chunk;
      }
    } catch (e) {
      circuitBreaker.recordFailure();

      // Check if we should fallback
      if (FallbackPolicy.shouldFallback(e, hasEmittedChunk) &&
          fallbackEnabled) {
        debugPrint('[ROUTE] Auto 模式 → 代理失败($e)，回退直连');
        // Fallback to direct connection
        yield* directProvider.sendMessageStream(
          model: model,
          messages: messages,
          parameters: parameters,
          files: files,
          modelId: modelId,
        );
      } else {
        // Can't fallback, rethrow the error
        rethrow;
      }
    }
  }

  @override
  Future<String> sendMessage({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
    String? modelId,
  }) async {
    // Check circuit breaker state
    if (circuitBreaker.shouldFallback && fallbackEnabled) {
      return directProvider.sendMessage(
        model: model,
        messages: messages,
        parameters: parameters,
        files: files,
        modelId: modelId,
      );
    }

    try {
      // Handle half-open state
      if (circuitBreaker.state == CircuitState.halfOpen) {
        if (!circuitBreaker.allowProbe) {
          if (fallbackEnabled) {
            return directProvider.sendMessage(
              model: model,
              messages: messages,
              parameters: parameters,
              files: files,
              modelId: modelId,
            );
          }
        }
        circuitBreaker.incrementHalfOpenCalls();
      }

      final result = await proxyProvider.sendMessage(
        model: model,
        messages: messages,
        parameters: parameters,
        files: files,
        modelId: modelId,
      );

      circuitBreaker.recordSuccess();
      return result;
    } catch (e) {
      circuitBreaker.recordFailure();

      // Non-streaming always fallbacks on error (no partial content)
      if (FallbackPolicy.shouldFallback(e, false) && fallbackEnabled) {
        return directProvider.sendMessage(
          model: model,
          messages: messages,
          parameters: parameters,
          files: files,
          modelId: modelId,
        );
      }

      rethrow;
    }
  }
}
