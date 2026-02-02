/// Backend routing mode for LLM requests.
///
/// Controls whether requests are sent directly to LLM APIs or routed
/// through the Python backend proxy.
enum BackendMode {
  /// Direct connection to LLM API (default, existing behavior)
  direct,

  /// Route through Python backend proxy
  proxy,

  /// Prefer proxy, fallback to direct on failure
  auto,
}
