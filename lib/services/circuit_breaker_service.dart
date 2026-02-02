import '../models/circuit_breaker_config.dart';

/// Circuit breaker states
enum CircuitState {
  /// Normal operation, requests flow through
  closed,

  /// Circuit is open, requests are blocked
  open,

  /// Testing if the circuit can be closed again
  halfOpen,
}

/// Circuit breaker for managing proxy failures and fallback.
///
/// Tracks failures and automatically opens when threshold is reached,
/// preventing cascading failures and enabling graceful degradation.
class CircuitBreaker {
  final CircuitBreakerConfig config;

  CircuitState _state = CircuitState.closed;
  int _failureCount = 0;
  DateTime? _lastFailure;
  DateTime? _openedAt;
  int _halfOpenCalls = 0;
  int _halfOpenSuccesses = 0;

  CircuitBreaker({CircuitBreakerConfig? config})
      : config = config ?? const CircuitBreakerConfig();

  /// Current circuit state
  CircuitState get state => _state;

  /// Whether the circuit is currently open (blocking requests)
  bool get isOpen => _state == CircuitState.open;

  /// Whether requests should fallback to direct connection
  bool get shouldFallback {
    _checkStateTransition();
    return _state == CircuitState.open;
  }

  /// Whether a probe request is allowed in half-open state
  bool get allowProbe {
    _checkStateTransition();
    if (_state == CircuitState.halfOpen) {
      return _halfOpenCalls < config.halfOpenMaxCalls;
    }
    return _state == CircuitState.closed;
  }

  /// Record a successful request
  void recordSuccess() {
    switch (_state) {
      case CircuitState.closed:
        // Reset failure count on success
        _failureCount = 0;
        _lastFailure = null;
        break;

      case CircuitState.halfOpen:
        _halfOpenSuccesses++;
        if (_halfOpenSuccesses >= config.halfOpenMaxCalls) {
          // Enough successful probes, close the circuit
          _transitionToClosed();
        }
        break;

      case CircuitState.open:
        // Shouldn't happen, but handle gracefully
        break;
    }
  }

  /// Record a failed request
  void recordFailure() {
    final now = DateTime.now();

    switch (_state) {
      case CircuitState.closed:
        // Check if failure is within the window
        if (_lastFailure != null) {
          final windowStart =
              now.subtract(Duration(milliseconds: config.windowMs));
          if (_lastFailure!.isBefore(windowStart)) {
            // Outside window, reset count
            _failureCount = 0;
          }
        }

        _failureCount++;
        _lastFailure = now;

        if (_failureCount >= config.failureThreshold) {
          _transitionToOpen();
        }
        break;

      case CircuitState.halfOpen:
        // Any failure in half-open state reopens the circuit
        _transitionToOpen();
        break;

      case CircuitState.open:
        // Already open, update opened time
        _openedAt = now;
        break;
    }
  }

  /// Reset the circuit breaker to closed state
  void reset() {
    _transitionToClosed();
  }

  void _checkStateTransition() {
    if (_state == CircuitState.open && _openedAt != null) {
      final now = DateTime.now();
      final openDuration = now.difference(_openedAt!).inMilliseconds;

      if (openDuration >= config.openMs) {
        _transitionToHalfOpen();
      }
    }
  }

  void _transitionToOpen() {
    _state = CircuitState.open;
    _openedAt = DateTime.now();
    _halfOpenCalls = 0;
    _halfOpenSuccesses = 0;
  }

  void _transitionToHalfOpen() {
    _state = CircuitState.halfOpen;
    _halfOpenCalls = 0;
    _halfOpenSuccesses = 0;
  }

  void _transitionToClosed() {
    _state = CircuitState.closed;
    _failureCount = 0;
    _lastFailure = null;
    _openedAt = null;
    _halfOpenCalls = 0;
    _halfOpenSuccesses = 0;
  }

  /// Increment half-open call count (call before making request)
  void incrementHalfOpenCalls() {
    if (_state == CircuitState.halfOpen) {
      _halfOpenCalls++;
    }
  }
}

/// Registry for circuit breakers, keyed by proxy URL
class CircuitBreakerRegistry {
  static final CircuitBreakerRegistry _instance = CircuitBreakerRegistry._();
  factory CircuitBreakerRegistry() => _instance;
  CircuitBreakerRegistry._();

  final Map<String, CircuitBreaker> _breakers = {};

  /// Get or create a circuit breaker for a given proxy URL
  CircuitBreaker getBreaker(String proxyUrl, {CircuitBreakerConfig? config}) {
    return _breakers.putIfAbsent(
      proxyUrl,
      () => CircuitBreaker(config: config),
    );
  }

  /// Reset all circuit breakers
  void resetAll() {
    for (final breaker in _breakers.values) {
      breaker.reset();
    }
  }

  /// Clear all circuit breakers
  void clear() {
    _breakers.clear();
  }
}
