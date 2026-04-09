/// MCP 工具集成测试
/// 测试完整调用链：McpClientService → McpToolAdapter → HybridLangChainProvider
///
/// 运行方式：
/// flutter test test/integration/mcp_integration_test.dart --no-pub

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive_flutter/hive_flutter.dart';

import '../../lib/services/mcp_client_service.dart';
import '../../lib/models/mcp/mcp_server_config.dart';
import '../../lib/models/provider_config.dart';
import '../../lib/models/model_config.dart';
import '../../lib/adapters/hybrid_langchain_provider.dart';
import '../../lib/adapters/mcp_tool_adapter.dart';
import '../../lib/adapters/ai_provider.dart';

/// 测试配置
class TestConfig {
  // MCP 服务器配置
  static const mcpServerName = 'deepwiki';
  static const mcpServerUrl = 'https://mcp.deepwiki.com/mcp';
  static const mcpTransportType = 'http';

  // LLM 供应商配置
  static const providerName = 'Gemini Proxy';
  static const providerUrl = 'https://x666.me/v1/chat/completions';
  static const apiKey = 'sk-M1Gr4Tfu7fXUWyGptbWCngfBUkGbj8JFo8ovT82i5DOjI5SI';
  static const modelName = 'gemini-2.5-flash';

  // 测试提示词（触发工具调用）
  static const testPrompt =
      'Use the deepwiki tool to get documentation topics for the repository "anthropics/anthropic-cookbook". Just list the main topics briefly.';
}

void main() {
  late McpClientService mcpService;
  late String testServerId;

  setUpAll(() async {
    // 初始化 Hive
    await Hive.initFlutter();

    // 注册 adapter
    if (!Hive.isAdapterRegistered(60)) {
      Hive.registerAdapter(McpServerConfigAdapter());
    }
  });

  tearDownAll(() async {
    // 清理
    if (mcpService.serverIds.contains(testServerId)) {
      await mcpService.disconnect(testServerId);
      await mcpService.removeServer(testServerId);
    }
    await Hive.close();
  });

  group('MCP Integration Tests', () {
    test('Phase 1: MCP Server Connection', () async {
      debugPrint('\n--- Phase 1: MCP Server Connection ---');

      mcpService = McpClientService();
      testServerId = 'test_${DateTime.now().millisecondsSinceEpoch}';

      final config = McpServerConfig(
        id: testServerId,
        name: TestConfig.mcpServerName,
        transportType: TestConfig.mcpTransportType,
        url: TestConfig.mcpServerUrl,
        enabled: true,
        createdAt: DateTime.now(),
      );

      await mcpService.addServer(config);
      debugPrint('  Server added: ${config.name}');

      await mcpService.connect(testServerId);
      final status = mcpService.getStatus(testServerId);
      debugPrint('  Connection status: $status');

      expect(status, equals(McpConnectionStatus.connected));
      debugPrint('  ✓ MCP connection successful');
    });

    test('Phase 2: Tool Discovery', () async {
      debugPrint('\n--- Phase 2: Tool Discovery ---');

      final tools = mcpService.getAllTools();
      debugPrint('  Found ${tools.length} tools:');

      for (final tool in tools) {
        final desc = tool.description.length > 60
            ? '${tool.description.substring(0, 60)}...'
            : tool.description;
        debugPrint('    - ${tool.name}: $desc');
      }

      expect(tools, isNotEmpty);
      debugPrint('  ✓ Tool discovery successful');
    });

    test('Phase 3: Tool Adapter', () async {
      debugPrint('\n--- Phase 3: Tool Adapter ---');

      final adapter = McpToolAdapter(mcpService);
      final definitions = adapter.getToolDefinitions();

      debugPrint('  Generated ${definitions.length} OpenAI-format definitions:');
      for (final def in definitions) {
        final func = def['function'] as Map<String, dynamic>;
        debugPrint('    - ${func['name']}');
      }

      expect(definitions, isNotEmpty);
      expect(definitions.first['type'], equals('function'));
      debugPrint('  ✓ Tool adapter working correctly');
    });

    test('Phase 4: Provider Integration', () async {
      debugPrint('\n--- Phase 4: Provider Integration ---');

      final providerConfig = ProviderConfig(
        id: 'test_provider',
        name: TestConfig.providerName,
        type: ProviderType.gemini,
        apiKey: TestConfig.apiKey,
        apiUrl: TestConfig.providerUrl,
        isEnabled: true,
      );

      final provider = HybridLangChainProvider(providerConfig);
      final adapter = McpToolAdapter(mcpService);

      provider.setMcpAdapter(adapter, supportsTools: true);

      debugPrint('  hasMcpTools: ${provider.hasMcpTools}');
      expect(provider.hasMcpTools, isTrue);
      debugPrint('  ✓ Provider integration successful');
    });

    test('Phase 5: End-to-End LLM Call with Tools', () async {
      debugPrint('\n--- Phase 5: End-to-End Test ---');
      debugPrint('  Model: ${TestConfig.modelName}');
      debugPrint('  Prompt: ${TestConfig.testPrompt}');

      final providerConfig = ProviderConfig(
        id: 'test_provider',
        name: TestConfig.providerName,
        type: ProviderType.gemini,
        apiKey: TestConfig.apiKey,
        apiUrl: TestConfig.providerUrl,
        isEnabled: true,
      );

      final provider = HybridLangChainProvider(providerConfig);
      final adapter = McpToolAdapter(mcpService);
      provider.setMcpAdapter(adapter, supportsTools: true);

      // 收集工具调用事件
      final toolEvents = <String>[];
      provider.onToolCallEvent = (event) {
        debugPrint('  [ToolEvent] $event');
        toolEvents.add(event.toString());
      };
      provider.onToolCallData = (data) {
        debugPrint('  [ToolData] ${data.toolName} - ${data.status}');
      };

      final messages = [
        ChatMessage(role: 'user', content: TestConfig.testPrompt),
      ];

      final parameters = ModelParameters(
        temperature: 0.7,
        maxTokens: 1024,
      );

      debugPrint('\n  Sending request to LLM...');
      final buffer = StringBuffer();

      await for (final chunk in provider.sendMessageStream(
        model: TestConfig.modelName,
        messages: messages,
        parameters: parameters,
      )) {
        buffer.write(chunk);
      }

      final response = buffer.toString();
      debugPrint('\n--- Response (first 800 chars) ---');
      debugPrint(response.length > 800 ? '${response.substring(0, 800)}...' : response);

      debugPrint('\n--- Analysis ---');
      debugPrint('  Response length: ${response.length} chars');
      debugPrint('  Tool events: ${toolEvents.length}');

      expect(response, isNotEmpty);
      debugPrint('  ✓ End-to-end test completed');
    }, timeout: const Timeout(Duration(minutes: 2)));
  });
}
