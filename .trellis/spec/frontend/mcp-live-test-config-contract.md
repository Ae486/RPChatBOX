# MCP Live Test Configuration Contract

## 1. Scope / Trigger

Applies to `test/integration/mcp_integration_test.dart` and `tools/mcp_integration_test.dart`. Live MCP tests use native plugins and an external model provider, so ordinary test runs must require explicit configuration before making those requests.

## 2. Signatures

- Automated test: `flutter test test/integration/mcp_integration_test.dart --no-pub --dart-define=CHATBOX_MCP_TEST_API_KEY=<your-key>`.
- Manual tool: `flutter run -t tools/mcp_integration_test.dart -d windows --dart-define=CHATBOX_MCP_TEST_API_KEY=<your-key>`.
- Both `TestConfig.apiKey` fields use `String.fromEnvironment('CHATBOX_MCP_TEST_API_KEY')`.

## 3. Contracts

- The key is a Dart compile-time define, not a runtime shell environment lookup. No credential literal or fallback key is allowed.
- With no key, automated `main()` registers one explicitly skipped test and returns before global setup, MCP connections, or model requests.
- With no key, manual `_runTests()` logs the configuration instruction and returns before changing `_isRunning` or connecting MCP. Ordinary app/Hive initialization still runs.
- With a key, preserve existing provider/model configuration and test assertions. Live calls can incur model charges; supplying a key does not prove integration success.

## 4. Validation & Error Matrix

| Configuration | Automated test | Manual tool |
| --- | --- | --- |
| Key missing or empty | Explicit skip with configuration instructions | Log instructions and remain idle |
| Key supplied | Execute existing live test path | Execute existing live test path |
| Invalid key, unavailable service, or plugin failure | Preserve existing failure behavior | Preserve existing failure behavior |

## 5. Good / Base / Bad Cases

- Good: explicitly configured native run exercises the existing assertions and reports actual provider results.
- Base: ordinary `flutter test --no-pub` reports the live test as skipped without opening external connections.
- Bad: embedding a key, silently passing unexecuted tests, or attempting a connection before checking configuration.

## 6. Verification Required

- Run the automated test without the define; assert an explicit skip and no setup/plugin/network execution.
- Statically verify the manual guard precedes `_isRunning` changes and connection calls.
- Keep existing live assertions intact. Record configured native/model verification separately; a skip or static review is not live acceptance.

## 7. Wrong vs Correct

- Wrong: a provider key stored as a source literal, or a missing-key return after MCP setup.
- Correct: `static const apiKey = String.fromEnvironment('CHATBOX_MCP_TEST_API_KEY');`, followed by an early missing-key guard before registering setup or starting a test run.
