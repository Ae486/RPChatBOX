/// MCP Tool → LLM Function Call 适配器
import 'dart:convert';

import '../services/mcp_client_service.dart';
import '../models/mcp/mcp_tool_call.dart';

/// 工具风险等级
enum ToolRiskLevel {
  /// 安全（只读操作）
  safe,

  /// 中等（创建/修改数据）
  moderate,

  /// 危险（删除/执行/系统级）
  dangerous,
}

/// MCP Tool Adapter
/// 负责将 MCP 工具转换为 LLM function calling 格式
class McpToolAdapter {
  final McpClientService _mcpService;

  /// 是否使用命名空间（多服务器时自动启用）
  bool get useNamespace => _mcpService.serverCount > 1;

  McpToolAdapter(this._mcpService);

  /// 获取所有工具定义（OpenAI 格式）
  List<Map<String, dynamic>> getToolDefinitions() {
    final tools = _mcpService.getAllTools();
    return tools.map((tool) => _convertToOpenAIFormat(tool)).toList();
  }

  /// 获取主服务器的工具定义
  List<Map<String, dynamic>> getPrimaryToolDefinitions() {
    final tools = _mcpService.getPrimaryTools();
    return tools.map((tool) => _convertToOpenAIFormat(tool)).toList();
  }

  /// 转换为 OpenAI function calling 格式
  Map<String, dynamic> _convertToOpenAIFormat(McpToolInfo tool) {
    return {
      'type': 'function',
      'function': {
        'name': tool.qualifiedName(useNamespace),
        'description': tool.description.isNotEmpty
            ? tool.description
            : 'Tool: ${tool.name} from ${tool.serverName}',
        'parameters': _normalizeSchema(tool.inputSchema),
      },
    };
  }

  /// 规范化 JSON Schema
  Map<String, dynamic> _normalizeSchema(Map<String, dynamic>? schema) {
    if (schema == null) {
      return {'type': 'object', 'properties': {}, 'required': []};
    }

    // 移除 MCP 特有字段，保留 OpenAI 兼容字段
    final normalized = Map<String, dynamic>.from(schema);
    normalized.remove('\$schema');
    normalized.remove('additionalProperties');

    // 确保必要字段存在
    normalized['type'] ??= 'object';
    normalized['properties'] ??= {};

    return normalized;
  }

  /// 执行工具调用
  Future<ToolExecutionResult> executeTool({
    required String name,
    required Map<String, dynamic> arguments,
  }) async {
    final result = await _mcpService.callToolByQualifiedName(
      qualifiedName: name,
      arguments: arguments,
    );

    return ToolExecutionResult(
      isSuccess: result.isSuccess,
      content: result.content,
      errorCode: result.errorCode,
    );
  }

  /// 批量执行工具调用（并行）
  Future<List<ToolExecutionResult>> executeTools(
    List<({String name, Map<String, dynamic> arguments})> calls,
  ) async {
    return Future.wait(
      calls.map((call) => executeTool(
            name: call.name,
            arguments: call.arguments,
          )),
    );
  }

  /// 解码工具名称
  /// 返回 (serverId, toolName)
  (String? serverId, String toolName) decodeToolName(String encodedName) {
    final parts = encodedName.split('__');
    if (parts.length >= 2) {
      return (parts[0], parts.sublist(1).join('__'));
    }
    return (null, encodedName);
  }

  /// 推断工具风险等级
  static ToolRiskLevel inferRiskLevel(String toolName) {
    final name = toolName.toLowerCase();

    // 危险操作
    if (name.contains('delete') ||
        name.contains('remove') ||
        name.contains('execute') ||
        name.contains('run') ||
        name.contains('shell') ||
        name.contains('eval') ||
        name.contains('drop') ||
        name.contains('truncate')) {
      return ToolRiskLevel.dangerous;
    }

    // 中等风险操作
    if (name.contains('write') ||
        name.contains('create') ||
        name.contains('update') ||
        name.contains('insert') ||
        name.contains('modify') ||
        name.contains('edit') ||
        name.contains('set') ||
        name.contains('put') ||
        name.contains('post')) {
      return ToolRiskLevel.moderate;
    }

    // 安全操作
    return ToolRiskLevel.safe;
  }

  /// 检查工具是否需要用户确认
  static bool requiresConfirmation(String toolName, ToolRiskLevel minLevel) {
    final level = inferRiskLevel(toolName);
    switch (minLevel) {
      case ToolRiskLevel.safe:
        return true; // 所有工具都确认
      case ToolRiskLevel.moderate:
        return level == ToolRiskLevel.moderate ||
            level == ToolRiskLevel.dangerous;
      case ToolRiskLevel.dangerous:
        return level == ToolRiskLevel.dangerous;
    }
  }

  /// 创建 ToolCallData 从 LLM 响应
  static ToolCallData createToolCallData({
    required String callId,
    required String toolName,
    String? serverName,
    Map<String, dynamic>? arguments,
  }) {
    return ToolCallData(
      callId: callId,
      toolName: toolName,
      serverName: serverName,
      arguments: arguments,
      status: ToolCallStatus.pending,
    );
  }
}

/// 工具执行结果
class ToolExecutionResult {
  final bool isSuccess;
  final String content;
  final String? errorCode;

  ToolExecutionResult({
    required this.isSuccess,
    required this.content,
    this.errorCode,
  });

  /// 转换为 JSON 字符串（用于发送给 LLM）
  String toJsonString() {
    if (isSuccess) {
      return content;
    }
    return jsonEncode({
      'error': true,
      'code': errorCode,
      'message': content,
    });
  }
}
