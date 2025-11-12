# Dio 网络请求优化方案

## 为什么要从 http 迁移到 dio？

### 当前问题（使用 http）
1. 每次请求都要手动设置 headers
2. 错误处理分散在各处
3. 没有统一的超时管理
4. 日志打印不统一
5. 无法方便地取消请求

### dio 的优势
- ✅ 拦截器（统一处理请求/响应/错误）
- ✅ 请求取消
- ✅ 超时重试
- ✅ FormData 文件上传
- ✅ 更好的流式支持

## 迁移步骤

### 1. 添加依赖

```yaml
dependencies:
  dio: ^5.4.0
```

### 2. 创建 Dio 服务类

`lib/services/dio_service.dart`

```dart
import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

class DioService {
  static final DioService _instance = DioService._internal();
  factory DioService() => _instance;
  
  late final Dio dio;
  
  DioService._internal() {
    dio = Dio(BaseOptions(
      connectTimeout: const Duration(seconds: 30),
      receiveTimeout: const Duration(seconds: 60),
      sendTimeout: const Duration(seconds: 60),
    ));
    
    // 添加拦截器
    dio.interceptors.add(_createInterceptor());
  }
  
  /// 创建拦截器
  Interceptor _createInterceptor() {
    return InterceptorsWrapper(
      onRequest: (options, handler) {
        // 请求前统一处理
        if (kDebugMode) {
          debugPrint('🚀 请求: ${options.method} ${options.uri}');
          debugPrint('📤 Headers: ${options.headers}');
          if (options.data != null) {
            debugPrint('📦 Data: ${options.data}');
          }
        }
        handler.next(options);
      },
      onResponse: (response, handler) {
        // 响应后统一处理
        if (kDebugMode) {
          debugPrint('✅ 响应: ${response.statusCode} ${response.requestOptions.uri}');
        }
        handler.next(response);
      },
      onError: (error, handler) {
        // 错误统一处理
        if (kDebugMode) {
          debugPrint('❌ 错误: ${error.requestOptions.uri}');
          debugPrint('   ${error.message}');
        }
        
        // 可以在这里统一处理常见错误
        if (error.type == DioExceptionType.connectionTimeout) {
          // 连接超时
        } else if (error.type == DioExceptionType.receiveTimeout) {
          // 接收超时
        }
        
        handler.next(error);
      },
    );
  }
  
  /// 取消令牌（用于取消请求）
  CancelToken createCancelToken() => CancelToken();
}
```

### 3. 改造 OpenAIProvider

`lib/adapters/openai_provider.dart`

```dart
import 'package:dio/dio.dart';
import '../services/dio_service.dart';

class OpenAIProvider extends AIProvider {
  final _dio = DioService().dio;
  CancelToken? _currentCancelToken;
  
  @override
  Stream<String> sendMessageStream({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
  }) async* {
    // 取消之前的请求
    _currentCancelToken?.cancel('新请求开始');
    _currentCancelToken = DioService().createCancelToken();
    
    try {
      final requestBody = await _buildRequestBody(
        model: model,
        messages: messages,
        parameters: parameters,
        stream: true,
        files: files,
      );
      
      // 使用 dio 发送流式请求
      final response = await _dio.post(
        _getApiUrl(),
        data: requestBody,
        options: Options(
          headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ${config.apiKey}',
          },
          responseType: ResponseType.stream, // 流式响应
        ),
        cancelToken: _currentCancelToken,
      );
      
      // 处理流式响应
      final stream = response.data.stream;
      await for (var chunk in stream) {
        final text = utf8.decode(chunk);
        final lines = text.split('\n');
        
        for (var line in lines) {
          if (line.startsWith('data: ')) {
            final data = line.substring(6).trim();
            if (data == '[DONE]') continue;
            
            try {
              final json = jsonDecode(data);
              final content = json['choices']?[0]?['delta']?['content'];
              if (content != null) {
                yield content as String;
              }
            } catch (e) {
              debugPrint('解析错误: $e');
            }
          }
        }
      }
    } on DioException catch (e) {
      if (e.type == DioExceptionType.cancel) {
        throw Exception('请求已取消');
      } else {
        throw Exception('网络错误: ${e.message}');
      }
    } catch (e) {
      throw Exception('未知错误: $e');
    } finally {
      _currentCancelToken = null;
    }
  }
  
  /// 手动取消请求
  void cancelRequest() {
    _currentCancelToken?.cancel('用户取消');
  }
}
```

### 4. 在 UI 中使用取消功能

`lib/widgets/conversation_view.dart`

```dart
// 停止按钮点击
void _onStopButtonPressed() {
  // 取消网络请求
  final provider = globalModelServiceManager.createProviderInstance(providerId);
  if (provider is OpenAIProvider) {
    provider.cancelRequest();
  }
  
  // 停止流式输出
  _streamController.stop();
}
```

## 优势对比

### 之前（使用 http）
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
  throw Exception('请求失败');
}

// 手动处理流式响应...
```

### 现在（使用 dio）
```dart
final response = await _dio.post(
  url,
  data: body,
  options: Options(
    headers: {'Authorization': 'Bearer $apiKey'},
    responseType: ResponseType.stream,
  ),
  cancelToken: cancelToken,
);

// dio 自动处理错误、超时、重试
```

## 进阶功能

### 1. 添加重试逻辑

```dart
dio.interceptors.add(
  RetryInterceptor(
    dio: dio,
    retries: 3, // 重试3次
    retryDelays: const [
      Duration(seconds: 1),
      Duration(seconds: 2),
      Duration(seconds: 3),
    ],
  ),
);
```

### 2. 上传进度监听

```dart
await _dio.post(
  url,
  data: formData,
  onSendProgress: (sent, total) {
    final progress = (sent / total * 100).toInt();
    debugPrint('上传进度: $progress%');
  },
);
```

### 3. 下载进度监听

```dart
await _dio.download(
  url,
  savePath,
  onReceiveProgress: (received, total) {
    final progress = (received / total * 100).toInt();
    debugPrint('下载进度: $progress%');
  },
);
```

## 测试方法

```bash
flutter pub get
flutter run
```

尝试：
1. 发送消息 - 应该更快更稳定
2. 点击停止按钮 - 立即停止（而不是等待超时）
3. 查看控制台日志 - 更清晰的请求/响应日志
