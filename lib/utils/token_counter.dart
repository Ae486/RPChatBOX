/// Token 计数和费用估算工具
class TokenCounter {
  /// 粗略估算文本的 token 数量
  /// 英文：1 token ≈ 4 字符
  /// 中文：1 token ≈ 1.5 字符
  static int estimateTokens(String text) {
    if (text.isEmpty) return 0;

    // 统计中英文字符
    int chineseChars = 0;
    int otherChars = 0;

    for (int i = 0; i < text.length; i++) {
      final code = text.codeUnitAt(i);
      // 中文字符范围：0x4E00-0x9FFF
      if (code >= 0x4E00 && code <= 0x9FFF) {
        chineseChars++;
      } else {
        otherChars++;
      }
    }

    // 估算 token 数
    final chineseTokens = (chineseChars / 1.5).ceil();
    final otherTokens = (otherChars / 4).ceil();

    return chineseTokens + otherTokens;
  }

  /// 估算消息列表的总 token 数
  static int estimateMessagesTokens(List<dynamic> messages) {
    int total = 0;
    for (var msg in messages) {
      if (msg is Map && msg.containsKey('content')) {
        total += estimateTokens(msg['content'].toString());
      }
    }
    return total;
  }

  /// 计算费用（美元）
  /// 参考价格（2024年）：
  /// - gpt-3.5-turbo: 输入 $0.0005/1K tokens, 输出 $0.0015/1K tokens
  /// - gpt-4: 输入 $0.03/1K tokens, 输出 $0.06/1K tokens
  static double estimateCost(int tokens, String model, {bool isOutput = false}) {
    double pricePerK = 0;

    if (model.contains('gpt-4-turbo') || model.contains('gpt-4-1106')) {
      pricePerK = isOutput ? 0.03 : 0.01;
    } else if (model.contains('gpt-4')) {
      pricePerK = isOutput ? 0.06 : 0.03;
    } else if (model.contains('gpt-3.5-turbo')) {
      pricePerK = isOutput ? 0.0015 : 0.0005;
    } else {
      // 默认使用 gpt-3.5-turbo 价格
      pricePerK = isOutput ? 0.0015 : 0.0005;
    }

    return (tokens / 1000) * pricePerK;
  }

  /// 格式化 token 数量显示
  static String formatTokens(int tokens) {
    if (tokens < 1000) {
      return '$tokens';
    } else if (tokens < 1000000) {
      return '${(tokens / 1000).toStringAsFixed(1)}K';
    } else {
      return '${(tokens / 1000000).toStringAsFixed(2)}M';
    }
  }

  /// 格式化费用显示（美元）
  static String formatCost(double cost) {
    if (cost < 0.01) {
      return '\$${(cost * 100).toStringAsFixed(3)}¢';
    } else if (cost < 1) {
      return '\$${cost.toStringAsFixed(3)}';
    } else {
      return '\$${cost.toStringAsFixed(2)}';
    }
  }

  /// 格式化费用显示（人民币）
  static String formatCostCNY(double costUSD, {double exchangeRate = 7.2}) {
    final costCNY = costUSD * exchangeRate;
    if (costCNY < 0.01) {
      return '¥${costCNY.toStringAsFixed(4)}';
    } else {
      return '¥${costCNY.toStringAsFixed(2)}';
    }
  }
}

/// Token 使用统计模型
class TokenUsage {
  int inputTokens;
  int outputTokens;
  double totalCost;

  TokenUsage({
    this.inputTokens = 0,
    this.outputTokens = 0,
    this.totalCost = 0.0,
  });

  int get totalTokens => inputTokens + outputTokens;

  void addUsage(int input, int output, double cost) {
    inputTokens += input;
    outputTokens += output;
    totalCost += cost;
  }

  void reset() {
    inputTokens = 0;
    outputTokens = 0;
    totalCost = 0.0;
  }

  Map<String, dynamic> toJson() {
    return {
      'inputTokens': inputTokens,
      'outputTokens': outputTokens,
      'totalCost': totalCost,
    };
  }

  factory TokenUsage.fromJson(Map<String, dynamic> json) {
    return TokenUsage(
      inputTokens: json['inputTokens'] as int? ?? 0,
      outputTokens: json['outputTokens'] as int? ?? 0,
      totalCost: (json['totalCost'] as num?)?.toDouble() ?? 0.0,
    );
  }
}

