/// MCP 工具集成测试（独立脚本）
/// 测试完整调用链：McpClientService → McpToolAdapter → HybridLangChainProvider
///
/// 运行方式：
/// flutter run -t tools/mcp_integration_test.dart -d windows

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:hive_flutter/hive_flutter.dart';

import '../lib/services/mcp_client_service.dart';
import '../lib/models/mcp/mcp_server_config.dart';
import '../lib/models/provider_config.dart';
import '../lib/models/model_config.dart';
import '../lib/adapters/hybrid_langchain_provider.dart';
import '../lib/adapters/mcp_tool_adapter.dart';
import '../lib/adapters/ai_provider.dart';

/// 测试配置
class TestConfig {
  // MCP 服务器配置
  static const mcpServerName = 'deepwiki';
  static const mcpServerUrl = 'https://mcp.deepwiki.com/mcp';
  static const mcpTransportType = 'http';

  // LLM 供应商配置
  static const providerName = 'Gemini Proxy';
  static const providerUrl = 'https://x666.me/v1/chat/completions';
  static const apiKey = 'sk-M1Gr4Tfu7fXUWyGptbWCngfBUkGbj8JFo8ovT82i5DOjl5SI';
  static const modelName = 'gemini-2.5-flash';

  // 测试提示词（触发工具调用）- 使用一个已被 DeepWiki 索引的仓库
  static const testPrompt =
      'Use the deepwiki ask_question tool to ask: "What testing frameworks does this project use and how are tests organized?" for the repository "vercel/next.js". Give me specific details from the documentation.';
}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Hive.initFlutter();

  runApp(const McpTestApp());
}

class McpTestApp extends StatelessWidget {
  const McpTestApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'MCP Integration Test',
      theme: ThemeData.dark(),
      home: const McpTestPage(),
    );
  }
}

class McpTestPage extends StatefulWidget {
  const McpTestPage({super.key});

  @override
  State<McpTestPage> createState() => _McpTestPageState();
}

class _McpTestPageState extends State<McpTestPage> {
  final _logs = <String>[];
  bool _isRunning = false;
  McpClientService? _mcpService;
  String? _testServerId;

  void _log(String message) {
    setState(() {
      _logs.add('[${DateTime.now().toString().substring(11, 19)}] $message');
    });
    debugPrint(message);
  }

  Future<void> _runTests() async {
    if (_isRunning) return;

    setState(() {
      _isRunning = true;
      _logs.clear();
    });

    try {
      _log('=' * 50);
      _log('MCP Integration Test');
      _log('=' * 50);

      // Phase 1
      await _testMcpConnection();

      // Phase 2
      await _testToolDiscovery();

      // Phase 3
      _testToolAdapter();

      // Phase 4
      _testProviderIntegration();

      // Phase 5
      await _testEndToEnd();

      _log('\n✅ All tests passed!');
    } catch (e, stack) {
      _log('\n❌ Test failed: $e');
      _log(stack.toString());
    } finally {
      // Cleanup
      if (_mcpService != null && _testServerId != null) {
        try {
          await _mcpService!.disconnect(_testServerId!);
          await _mcpService!.removeServer(_testServerId!);
        } catch (_) {}
      }

      setState(() {
        _isRunning = false;
      });
    }
  }

  Future<void> _testMcpConnection() async {
    _log('\n--- Phase 1: MCP Server Connection ---');

    // 注册 adapter
    if (!Hive.isAdapterRegistered(60)) {
      Hive.registerAdapter(McpServerConfigAdapter());
    }

    _mcpService = McpClientService();
    _testServerId = 'test_${DateTime.now().millisecondsSinceEpoch}';

    final config = McpServerConfig(
      id: _testServerId!,
      name: TestConfig.mcpServerName,
      transportType: TestConfig.mcpTransportType,
      url: TestConfig.mcpServerUrl,
      enabled: true,
      createdAt: DateTime.now(),
    );

    await _mcpService!.addServer(config);
    _log('  Server added: ${config.name}');

    _log('  Connecting to MCP server...');
    await _mcpService!.connect(_testServerId!);

    final status = _mcpService!.getStatus(_testServerId!);
    _log('  Connection status: $status');

    if (status != McpConnectionStatus.connected) {
      throw Exception('Expected connected status, got: $status');
    }

    _log('  ✓ MCP connection successful');
  }

  Future<void> _testToolDiscovery() async {
    _log('\n--- Phase 2: Tool Discovery ---');

    final tools = _mcpService!.getAllTools();
    _log('  Found ${tools.length} tools:');

    if (tools.isEmpty) {
      throw Exception('No tools discovered from MCP server');
    }

    for (final tool in tools) {
      final desc = tool.description.length > 50
          ? '${tool.description.substring(0, 50)}...'
          : tool.description;
      _log('    - ${tool.name}: $desc');
    }

    _log('  ✓ Tool discovery successful');
  }

  void _testToolAdapter() {
    _log('\n--- Phase 3: Tool Adapter ---');

    final adapter = McpToolAdapter(_mcpService!);
    final definitions = adapter.getToolDefinitions();

    _log('  Generated ${definitions.length} OpenAI-format definitions:');

    if (definitions.isEmpty) {
      throw Exception('No tool definitions generated');
    }

    for (final def in definitions) {
      final func = def['function'] as Map<String, dynamic>;
      _log('    - ${func['name']}');

      if (def['type'] != 'function') {
        throw Exception('Invalid tool type: ${def['type']}');
      }
    }

    _log('  ✓ Tool adapter working correctly');
  }

  void _testProviderIntegration() {
    _log('\n--- Phase 4: Provider Integration ---');

    final providerConfig = ProviderConfig(
      id: 'test_provider',
      name: TestConfig.providerName,
      type: ProviderType.gemini,
      apiKey: TestConfig.apiKey,
      apiUrl: TestConfig.providerUrl,
      isEnabled: true,
    );

    final provider = HybridLangChainProvider(providerConfig);
    final adapter = McpToolAdapter(_mcpService!);

    provider.setMcpAdapter(adapter, supportsTools: true);

    _log('  hasMcpTools: ${provider.hasMcpTools}');

    if (!provider.hasMcpTools) {
      throw Exception('MCP tools should be enabled');
    }

    _log('  ✓ Provider integration successful');
  }

  Future<void> _testEndToEnd() async {
    _log('\n--- Phase 5: End-to-End Test ---');
    _log('  Model: ${TestConfig.modelName}');
    _log('  Prompt: ${TestConfig.testPrompt}');

    final providerConfig = ProviderConfig(
      id: 'test_provider',
      name: TestConfig.providerName,
      type: ProviderType.gemini,
      apiKey: TestConfig.apiKey,
      apiUrl: TestConfig.providerUrl,
      isEnabled: true,
    );

    final provider = HybridLangChainProvider(providerConfig);
    final adapter = McpToolAdapter(_mcpService!);
    provider.setMcpAdapter(adapter, supportsTools: true);

    // 收集工具调用事件
    final toolEvents = <String>[];
    provider.onToolCallEvent = (event) {
      _log('  [ToolEvent] $event');
      toolEvents.add(event.toString());
    };
    provider.onToolCallData = (data) {
      _log('  [ToolData] ${data.toolName} - ${data.status}');
    };

    final messages = [
      ChatMessage(role: 'user', content: TestConfig.testPrompt),
    ];

    final parameters = ModelParameters(
      temperature: 0.7,
      maxTokens: 1024,
    );

    _log('\n  Sending request to LLM...');
    final buffer = StringBuffer();

    try {
      await for (final chunk in provider.sendMessageStream(
        model: TestConfig.modelName,
        messages: messages,
        parameters: parameters,
      )) {
        buffer.write(chunk);
        // 实时更新 UI
        if (buffer.length % 100 == 0) {
          setState(() {});
        }
      }

      final response = buffer.toString();
      _log('\n--- Response ---');
      _log(response);  // 不截断，显示完整内容

      _log('\n--- Analysis ---');
      _log('  Response length: ${response.length} chars');
      _log('  Tool events: ${toolEvents.length}');

      if (response.isEmpty) {
        throw Exception('Empty response from LLM');
      }

      _log('  ✓ End-to-end test completed');
    } catch (e) {
      _log('  ✗ LLM request failed: $e');
      rethrow;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('MCP Integration Test'),
        actions: [
          IconButton(
            icon: const Icon(Icons.delete_outline),
            onPressed: () => setState(() => _logs.clear()),
          ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: ElevatedButton.icon(
              onPressed: _isRunning ? null : _runTests,
              icon: _isRunning
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.play_arrow),
              label: Text(_isRunning ? 'Running...' : 'Run Tests'),
              style: ElevatedButton.styleFrom(
                minimumSize: const Size(200, 48),
              ),
            ),
          ),
          const Divider(),
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(8),
              itemCount: _logs.length,
              itemBuilder: (context, index) {
                final log = _logs[index];
                Color? color;
                if (log.contains('✓')) {
                  color = Colors.green;
                } else if (log.contains('✗') || log.contains('❌')) {
                  color = Colors.red;
                } else if (log.contains('---')) {
                  color = Colors.cyan;
                }
                return Text(
                  log,
                  style: TextStyle(
                    fontFamily: 'monospace',
                    fontSize: 12,
                    color: color,
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
