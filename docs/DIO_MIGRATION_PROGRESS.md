# Dio 迁移进度跟踪

## 📋 迁移策略

**原则：逐步迁移，保持向后兼容，不影响现有功能**

### 阶段划分

- ✅ **阶段 1**：添加 dio 依赖（完成）
- ✅ **阶段 2**：创建 DioService 封装层（完成）
- ⏳ **阶段 3**：测试 Provider 迁移（进行中）
- ⬜ **阶段 4**：全面迁移并测试
- ⬜ **阶段 5**：移除 http 依赖

---

## ✅ 已完成的工作

### 1. 添加依赖（2024-11-10）

**文件：** `pubspec.yaml`

**更改：**
```yaml
dependencies:
  http: ^1.2.0  # 保留，逐步迁移到 dio
  dio: ^5.4.0   # 新增：更强大的网络请求库
```

**状态：** ✅ 已安装，`flutter pub get` 成功

---

### 2. 创建 DioService（2024-11-10）

**文件：** `lib/services/dio_service.dart`

**功能：**
- ✅ 单例模式
- ✅ 统一的拦截器（请求/响应/错误）
- ✅ 取消令牌支持
- ✅ 通用方法封装（GET/POST/PUT/DELETE）
- ✅ 下载支持
- ✅ 详细的调试日志

**状态：** ✅ 已创建，`flutter analyze` 无错误

---

## ⏳ 进行中的工作

### 3. 创建测试 Provider

**目的：** 在不影响现有功能的情况下，测试 dio 的功能

**计划：**
1. 创建一个新的测试 Provider 类
2. 使用 dio 实现相同的功能
3. 对比测试结果
4. 确认无误后再迁移主 Provider

**文件：** `lib/adapters/openai_provider_dio.dart` （新建）

---

## 📊 迁移清单

### 需要迁移的文件

| 文件 | 当前状态 | 优先级 | 预计收益 |
|------|---------|-------|---------|
| `openai_provider.dart` | ⏳ 测试中 | 🔥 高 | 代码简化、请求取消 |
| 其他 Provider | ⬜ 未开始 | ⭐ 中 | 统一网络层 |

### 迁移前后对比

#### 之前（使用 http）

```dart
final response = await http.post(
  Uri.parse(url),
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer $apiKey',
  },
  body: jsonEncode(body),
).timeout(const Duration(seconds: 30));

if (response.statusCode != 200) {
  throw Exception('请求失败: ${response.statusCode}');
}
```

**问题：**
- ❌ 每次都要手动设置 headers
- ❌ 手动处理超时
- ❌ 错误处理繁琐
- ❌ 无法方便地取消请求

#### 之后（使用 dio）

```dart
final response = await DioService().post(
  url,
  data: body,
  options: Options(
    headers: {'Authorization': 'Bearer $apiKey'},
  ),
  cancelToken: _cancelToken,
);

if (response.statusCode != 200) {
  throw Exception('请求失败: ${response.statusCode}');
}
```

**优势：**
- ✅ 自动设置 Content-Type
- ✅ 内置超时管理
- ✅ 统一错误日志
- ✅ 支持请求取消
- ✅ 代码更简洁

---

## 🧪 测试计划

### 测试用例

| 功能 | 测试方法 | 预期结果 | 状态 |
|------|---------|---------|------|
| 普通对话 | 发送消息 | 正常回复 | ⬜ |
| 流式输出 | 发送消息 | 逐字显示 | ⬜ |
| 请求取消 | 点击停止按钮 | 立即停止 | ⬜ |
| 错误处理 | 无效 API Key | 显示错误 | ⬜ |
| 超时处理 | 网络慢 | 自动重试 | ⬜ |
| 文件上传 | 上传图片 | 正常发送 | ⬜ |

---

## 📝 注意事项

### 1. 向后兼容

- ✅ 保留 http 包
- ✅ 不修改现有代码
- ✅ 新功能使用 dio
- ✅ 测试通过后再迁移

### 2. 错误处理

**dio 错误类型：**
- `DioExceptionType.connectionTimeout` - 连接超时
- `DioExceptionType.sendTimeout` - 发送超时
- `DioExceptionType.receiveTimeout` - 接收超时
- `DioExceptionType.badResponse` - 响应错误
- `DioExceptionType.cancel` - 请求取消
- `DioExceptionType.unknown` - 未知错误

### 3. 流式响应处理

```dart
// dio 流式响应
final response = await DioService().dio.post(
  url,
  data: body,
  options: Options(
    responseType: ResponseType.stream,
    headers: headers,
  ),
  cancelToken: cancelToken,
);

// 处理 stream
final stream = response.data.stream;
await for (var chunk in stream) {
  // 处理每个数据块
}
```

---

## 🚀 下一步行动

### 立即执行

1. ✅ 创建 DioService（已完成）
2. ⏳ 创建测试 Provider
3. ⏳ 对比测试
4. ⏳ 迁移主 Provider

### 后续计划

- 添加重试机制
- 添加缓存功能
- 优化日志输出
- 性能监控

---

## 📚 参考资料

- [Dio 官方文档](https://pub.dev/packages/dio)
- [Dio 中文文档](https://github.com/cfug/dio/blob/main/README-ZH.md)
- [迁移指南](OPTIMIZATION_DIO.md)

---

## 🔄 更新日志

| 日期 | 更新内容 | 状态 |
|------|---------|------|
| 2024-11-10 | 添加 dio 依赖 | ✅ 完成 |
| 2024-11-10 | 创建 DioService | ✅ 完成 |
| 2024-11-10 | 创建迁移文档 | ✅ 完成 |

---

## ✅ 验证检查清单

迁移完成后需要验证：

- [ ] 所有现有功能正常工作
- [ ] 没有新的错误或警告
- [ ] 停止按钮立即生效
- [ ] 网络错误正确提示
- [ ] 日志输出清晰
- [ ] 性能无明显下降
- [ ] 可以安全移除 http 包
