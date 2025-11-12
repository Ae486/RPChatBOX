# 应用优化建议

基于 Flutter 库文档和你当前应用的分析，提供以下优化建议：

## 📊 优先级分级

### 🔥 高优先级（建议立即实施）

| 库名 | 版本 | 用途 | 优化点 |
|------|------|------|--------|
| **dio** | ^5.4.0 | 网络请求 | 替换 http，统一请求处理、支持取消、重试 |
| **cached_network_image** | ^3.3.0 | 图片缓存 | 缓存对话中的图片，减少重复下载 |
| **flutter_spinkit** | ^5.2.0 | 加载动画 | 美化加载指示器 |
| **hive** | ^2.2.3 | 本地数据库 | 替换 SharedPreferences，提升性能 |

### ⭐ 中优先级（可选但推荐）

| 库名 | 版本 | 用途 | 优化点 |
|------|------|------|--------|
| **provider** 或 **get** | ^6.1.1 / ^4.6.6 | 状态管理 | 替换全局变量，更优雅的状态管理 |
| **intl** | ^0.18.1 | 国际化 | 多语言支持 |
| **flutter_image_compress** | ^2.1.0 | 图片压缩 | 上传前压缩图片 |
| **flutter_cache_manager** | ^3.3.1 | 文件缓存 | 管理PDF/Word缓存 |

### 💡 低优先级（锦上添花）

| 库名 | 版本 | 用途 | 优化点 |
|------|------|------|--------|
| **pull_to_refresh** | ^2.0.0 | 下拉刷新 | 对话列表刷新 |
| **flutter_screenutil** | ^5.9.0 | 屏幕适配 | 多设备适配 |
| **like_button** | ^2.0.5 | 动态按钮 | 点赞/收藏功能 |

---

## 🎯 针对性优化方案

### 1. 网络请求优化 - dio

**当前问题：**
- 代码冗长，每次都要手动设置 headers
- 错误处理分散
- 无法方便地取消请求

**优化方案：**
```yaml
dependencies:
  dio: ^5.4.0
```

**收益：**
- 减少 30% 的网络请求代码
- 统一的错误处理
- 支持请求取消（停止生成立即生效）
- 自动重试（网络不稳定时）

**详细文档：** `OPTIMIZATION_DIO.md`

---

### 2. 数据存储优化 - hive

**当前问题：**
- 使用 SharedPreferences 存储对话，性能差
- JSON 序列化/反序列化开销大
- 数据量大时加载慢

**优化方案：**
```yaml
dependencies:
  hive: ^2.2.3
  hive_flutter: ^1.1.0

dev_dependencies:
  hive_generator: ^2.0.1
  build_runner: ^2.4.6
```

**示例：**
```dart
// 定义数据模型
@HiveType(typeId: 0)
class Conversation extends HiveObject {
  @HiveField(0)
  String id;
  
  @HiveField(1)
  String title;
  
  @HiveField(2)
  List<Message> messages;
}

// 打开数据库
await Hive.initFlutter();
await Hive.openBox<Conversation>('conversations');

// 存储
final box = Hive.box<Conversation>('conversations');
await box.put(conversation.id, conversation);

// 读取
final conversation = box.get(conversationId);

// 监听变化
box.watch().listen((event) {
  // 自动更新 UI
});
```

**收益：**
- 读写速度提升 10-100 倍
- 支持复杂数据类型
- 自动监听数据变化
- 更小的内存占用

---

### 3. 图片处理优化

#### 3.1 图片缓存 - cached_network_image

```yaml
dependencies:
  cached_network_image: ^3.3.0
```

**使用：**
```dart
CachedNetworkImage(
  imageUrl: imageUrl,
  placeholder: (context, url) => CircularProgressIndicator(),
  errorWidget: (context, url, error) => Icon(Icons.error),
)
```

#### 3.2 图片压缩 - flutter_image_compress

```yaml
dependencies:
  flutter_image_compress: ^2.1.0
```

**使用：**
```dart
// 压缩图片
final compressedBytes = await FlutterImageCompress.compressWithFile(
  file.absolute.path,
  quality: 85,
  minWidth: 1920,
  minHeight: 1080,
);

// 控制文件大小（如限制 2MB）
final targetSize = 2 * 1024 * 1024; // 2MB
if (compressedBytes.length > targetSize) {
  // 进一步压缩
}
```

**收益：**
- 减少网络传输时间
- 节省 token 消耗
- 提升用户体验

---

### 4. 状态管理优化 - Provider

**当前问题：**
```dart
// 使用全局变量
late ModelServiceManager globalModelServiceManager;

// 到处引用
import '../main.dart' show globalModelServiceManager;
```

**优化方案：**
```yaml
dependencies:
  provider: ^6.1.1
```

**示例：**
```dart
// main.dart
void main() {
  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => ModelServiceManager()),
        ChangeNotifierProvider(create: (_) => ThemeManager()),
      ],
      child: MyApp(),
    ),
  );
}

// 使用
class ChatPage extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final modelManager = Provider.of<ModelServiceManager>(context);
    
    return Scaffold(
      // ...
    );
  }
}

// 或使用 Consumer
Consumer<ModelServiceManager>(
  builder: (context, manager, child) {
    return Text(manager.currentModel);
  },
)
```

**收益：**
- 更清晰的依赖关系
- 自动UI更新
- 更容易测试

---

### 5. UI 优化

#### 5.1 加载动画 - flutter_spinkit

```yaml
dependencies:
  flutter_spinkit: ^5.2.0
```

**使用：**
```dart
SpinKitFadingCircle(
  color: Colors.blue,
  size: 50.0,
)

// 或其他动画
SpinKitRipple()
SpinKitDoubleBounce()
SpinKitWave()
```

#### 5.2 下拉刷新 - pull_to_refresh

```yaml
dependencies:
  pull_to_refresh: ^2.0.0
```

**使用：**
```dart
SmartRefresher(
  controller: _refreshController,
  onRefresh: _onRefresh,
  onLoading: _onLoading,
  child: ListView.builder(
    itemCount: conversations.length,
    itemBuilder: (context, index) => ConversationCard(),
  ),
)
```

---

## 🚀 实施计划

### 第一阶段（1-2天）- 核心优化
1. ✅ 迁移到 dio（网络请求）
2. ✅ 添加 cached_network_image（图片缓存）
3. ✅ 使用 flutter_spinkit（加载动画）

### 第二阶段（3-5天）- 性能优化
4. ✅ 迁移到 hive（数据库）
5. ✅ 添加 flutter_image_compress（图片压缩）
6. ✅ 重构状态管理（Provider）

### 第三阶段（可选）- 体验优化
7. 添加国际化支持
8. 添加下拉刷新
9. 优化 UI 动画

---

## 📈 预期收益

| 优化项 | 提升指标 |
|--------|---------|
| 网络请求（dio） | 代码量减少 30%，请求速度提升 20% |
| 数据存储（hive） | 读写速度提升 10-100倍 |
| 图片缓存 | 重复图片加载时间减少 90% |
| 图片压缩 | Token 消耗减少 50%，上传速度提升 60% |
| 状态管理 | 代码可维护性提升 40% |

---

## 🛠️ 开始实施

### 1. 安装依赖

```bash
# 添加到 pubspec.yaml
dependencies:
  dio: ^5.4.0
  cached_network_image: ^3.3.0
  flutter_spinkit: ^5.2.0
  hive: ^2.2.3
  hive_flutter: ^1.1.0
  provider: ^6.1.1

dev_dependencies:
  hive_generator: ^2.0.1
  build_runner: ^2.4.6
```

### 2. 安装

```bash
flutter pub get
```

### 3. 生成 Hive 适配器

```bash
flutter packages pub run build_runner build
```

### 4. 运行测试

```bash
flutter run
```

---

## 📚 参考资料

- [Dio 官方文档](https://pub.dev/packages/dio)
- [Hive 官方文档](https://docs.hivedb.dev/)
- [Provider 官方文档](https://pub.dev/packages/provider)
- [Flutter 性能优化指南](https://flutter.dev/docs/perf)

---

## 💬 需要帮助？

如果在实施过程中遇到问题，可以：
1. 查看 `OPTIMIZATION_DIO.md` 详细文档
2. 参考各库的官方示例
3. 提问具体的问题
