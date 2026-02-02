/// Configuration for circuit breaker behavior.
///
/// Controls when to stop trying the proxy and fallback to direct connection.
class CircuitBreakerConfig {
  /// Number of failures before opening the circuit
  final int failureThreshold;

  /// Time window in milliseconds for counting failures
  final int windowMs;

  /// Duration in milliseconds to keep circuit open
  final int openMs;

  /// Maximum probe calls in half-open state
  final int halfOpenMaxCalls;

  const CircuitBreakerConfig({
    this.failureThreshold = 3,
    this.windowMs = 60000,
    this.openMs = 30000,
    this.halfOpenMaxCalls = 2,
  });

  factory CircuitBreakerConfig.fromJson(Map<String, dynamic> json) {
    return CircuitBreakerConfig(
      failureThreshold: json['failureThreshold'] as int? ?? 3,
      windowMs: json['windowMs'] as int? ?? 60000,
      openMs: json['openMs'] as int? ?? 30000,
      halfOpenMaxCalls: json['halfOpenMaxCalls'] as int? ?? 2,
    );
  }

  Map<String, dynamic> toJson() => {
        'failureThreshold': failureThreshold,
        'windowMs': windowMs,
        'openMs': openMs,
        'halfOpenMaxCalls': halfOpenMaxCalls,
      };

  CircuitBreakerConfig copyWith({
    int? failureThreshold,
    int? windowMs,
    int? openMs,
    int? halfOpenMaxCalls,
  }) {
    return CircuitBreakerConfig(
      failureThreshold: failureThreshold ?? this.failureThreshold,
      windowMs: windowMs ?? this.windowMs,
      openMs: openMs ?? this.openMs,
      halfOpenMaxCalls: halfOpenMaxCalls ?? this.halfOpenMaxCalls,
    );
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is CircuitBreakerConfig &&
        other.failureThreshold == failureThreshold &&
        other.windowMs == windowMs &&
        other.openMs == openMs &&
        other.halfOpenMaxCalls == halfOpenMaxCalls;
  }

  @override
  int get hashCode => Object.hash(
        failureThreshold,
        windowMs,
        openMs,
        halfOpenMaxCalls,
      );
}
