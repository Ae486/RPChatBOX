import '../models/provider_config.dart';

/// API地址处理辅助类
/// 处理API地址补全、规则解析等功能
class ApiUrlHelper {
  /// 获取实际使用的API地址
  /// 
  /// 规则：
  /// - 以 "#" 结尾：强制使用输入地址（去除#）
  /// - 以 "/" 结尾：忽略v1版本，直接补全路径（去除/）
  /// - 其他：正常补全
  static String getActualApiUrl(String inputUrl, ProviderType type) {
    final trimmed = inputUrl.trim();
    
    // 规则1：# 结尾 - 强制使用输入地址
    if (trimmed.endsWith('#')) {
      return trimmed.substring(0, trimmed.length - 1);
    }
    
    // 规则2：/ 结尾 - 忽略v1版本
    if (trimmed.endsWith('/')) {
      final baseUrl = trimmed.substring(0, trimmed.length - 1);
      final path = _getApiPath(type);
      if (path.isEmpty) return baseUrl;
      
      // 直接拼接路径，跳过版本号
      final pathWithoutVersion = path.startsWith('/v1/') 
          ? path.substring(3)  // 移除 /v1
          : path;
      return baseUrl + pathWithoutVersion;
    }
    
    // 规则3：正常补全
    final suffix = _getApiSuffix(type);
    if (suffix.isEmpty) return trimmed;

    final endpointPath = _getApiPathWithoutVersion(type);
    if (trimmed.endsWith(suffix) || trimmed.endsWith(endpointPath)) {
      return trimmed;
    }

    final versionPrefix = _getApiVersionPrefix(type);
    if (versionPrefix.isNotEmpty && trimmed.endsWith(versionPrefix)) {
      return trimmed + endpointPath;
    }

    return trimmed + suffix;
  }
  
  /// 获取API路径后缀（用于补全）
  static String _getApiSuffix(ProviderType type) {
    switch (type) {
      case ProviderType.openai:
        return '/v1/chat/completions';
      case ProviderType.claude:
        return '/v1/messages';
      case ProviderType.gemini:
      case ProviderType.deepseek:
        return ''; // 不补全
    }
  }
  
  /// 获取API路径（不含版本号）
  static String _getApiPath(ProviderType type) {
    switch (type) {
      case ProviderType.openai:
        return '/v1/chat/completions';
      case ProviderType.claude:
        return '/v1/messages';
      case ProviderType.gemini:
      case ProviderType.deepseek:
        return '';
    }
  }

  /// 获取不含版本号的 endpoint path
  static String _getApiPathWithoutVersion(ProviderType type) {
    final path = _getApiPath(type);
    if (path.startsWith('/v1/')) {
      return path.substring(3);
    }
    return path;
  }

  /// 获取版本前缀
  static String _getApiVersionPrefix(ProviderType type) {
    switch (type) {
      case ProviderType.openai:
      case ProviderType.claude:
        return '/v1';
      case ProviderType.gemini:
      case ProviderType.deepseek:
        return '';
    }
  }
  
  /// 获取显示用的完整API地址预览
  /// 
  /// 返回值：
  /// - 如果输入为空，返回仅路径部分（如 "/v1/chat/completions"）
  /// - 否则返回完整的实际使用地址
  static String getDisplayUrl(String inputUrl, ProviderType type) {
    final trimmed = inputUrl.trim();
    
    if (trimmed.isEmpty) {
      // 输入为空时，只显示路径部分
      return _getApiSuffix(type);
    }
    
    return getActualApiUrl(trimmed, type);
  }
  
  /// 获取提示文本
  static String getHintText(String inputUrl, ProviderType type) {
    final trimmed = inputUrl.trim();
    
    if (trimmed.endsWith('#')) {
      return '强制使用输入地址（不补全）';
    }
    
    if (trimmed.endsWith('/')) {
      return '忽略 v1 版本号';
    }
    
    final suffix = _getApiSuffix(type);
    if (suffix.isEmpty) {
      return '此服务商类型不自动补全';
    }
    
    return '自动补全路径';
  }
}
