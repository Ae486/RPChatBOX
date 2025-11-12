# 测试说明

## 修复内容

已修复 PDF 和 Word 文档无法提取内容的问题。

### 问题原因

`FileContentService.isTextProcessable()` 方法中缺少 PDF 和 Word 文件的扩展名和 MIME 类型判断，导致这些文件被判断为"暂不支持内容提取"。

### 修复方案

在 `lib/services/file_content_service.dart` 中添加：

**MIME 类型：**
- `application/pdf` - PDF 文档
- `application/msword` - Word .doc 格式
- `application/vnd.openxmlformats-officedocument.wordprocessingml.document` - Word .docx 格式

**文件扩展名：**
- `.pdf`
- `.doc`
- `.docx`

## 测试步骤

### 1. 运行应用

```bash
flutter run
```

### 2. 测试 PDF 文件

1. 点击输入框下方的 **"+"** 按钮
2. 选择一个 PDF 文件（建议选择有文字内容的 PDF，非扫描版）
3. 文件上传后，在输入框输入："请总结这个文档的内容"
4. 点击发送

**预期结果：**
- PDF 文本被成功提取
- AI 能够基于 PDF 内容回答问题
- 在调试控制台可以看到提取的文本内容

### 3. 测试 Word 文档

1. 点击 **"+"** 按钮
2. 选择一个 `.docx` 文件
3. 输入问题："帮我总结一下这份文档"
4. 点击发送

**预期结果：**
- Word 文档文本被成功提取
- AI 能够理解并回答文档相关问题

### 4. 测试代码文件

1. 上传一个 `.py`、`.js` 或其他代码文件
2. 输入："这段代码有什么问题？"
3. 发送

**预期结果：**
- 代码内容被读取
- AI 能够分析代码

## 查看调试信息

在控制台（运行 `flutter run` 的终端）中，你可以看到：

```
║ 📤 完整请求体:
║   {
║     "model": "gpt-4",
║     "messages": [
║       {
║         "role": "user",
║         "content": [
║           {
║             "type": "text",
║             "text": "以下是文件 \"document.pdf\" (application/pdf) 的内容:\n---\n[提取的PDF文本内容]\n---\n\n请基于上述文件内容回答用户的问题。\n\n---\n\n请总结这个文档的内容"
║           }
║         ]
║       }
║     ],
║     "stream": true
║   }
```

### 成功标志

如果看到类似上述格式，说明文件内容已成功提取并发送给 AI。

### 失败标志

如果看到：
```
"// 文件 xxx.pdf (application/pdf) 暂不支持内容提取"
```

说明问题未解决，需要进一步排查。

## 已知限制

### PDF
- ✅ 支持可搜索的 PDF（包含文本层）
- ❌ 不支持扫描版 PDF（纯图片）
- ⚠️ 最多提取前 50 页

### Word
- ✅ 支持 `.docx` 格式
- ❌ 不支持 `.doc` 格式（需要转换）
- ⚠️ 不保留格式（字体、颜色等）

## 故障排除

### 1. PDF 提取为空

**可能原因：**
- PDF 是扫描版（图片）
- PDF 使用了特殊加密

**解决方法：**
- 使用 Adobe Acrobat 或其他工具将 PDF 转为可搜索格式
- 或使用 OCR 工具

### 2. Word 文档提取失败

**可能原因：**
- 文件是 `.doc` 格式（不支持）
- 文件损坏

**解决方法：**
- 使用 Microsoft Word 打开并另存为 `.docx`

### 3. 依赖包问题

如果遇到编译错误，运行：

```bash
flutter pub get
flutter clean
flutter pub get
```

## 相关文件

- `lib/services/file_content_service.dart` - 文件内容提取服务
- `lib/adapters/openai_provider.dart` - API 请求处理
- `pubspec.yaml` - 依赖配置

## 依赖版本

```yaml
syncfusion_flutter_pdf: ^27.2.5  # PDF 提取
archive: ^3.4.0                   # ZIP 解压（用于 .docx）
path: ^1.9.0                      # 文件路径工具
```
