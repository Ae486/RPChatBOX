# 文件附件功能说明

## 概述

本应用支持在对话中上传并处理各种文件类型，AI 会自动提取文件内容并理解用户的问题。

## 支持的文件类型

### 1. 图片文件（直接视觉识别）
- **格式**：jpg, jpeg, png, gif, webp, bmp, svg
- **处理方式**：以 Base64 编码发送给支持视觉的模型（如 GPT-4 Vision、Claude 3）
- **用途**：图片理解、OCR、图表分析等

### 2. 文本文件（直接读取）
- **格式**：txt, md, csv, log
- **处理方式**：直接读取文本内容
- **用途**：代码分析、日志分析、数据分析

### 3. 代码文件（语法识别）
- **格式**：js, ts, dart, py, java, cpp, c, h, cs, php, rb, go, rs, swift, kt
- **格式**：html, css, json, xml, yaml, yml, toml, ini, sql, sh, bat
- **处理方式**：作为代码文本读取，保留格式
- **用途**：代码审查、问题诊断、重构建议

### 4. PDF 文档（文本提取）✨新增
- **格式**：pdf
- **处理方式**：使用 `syncfusion_flutter_pdf` 库提取文本
- **限制**：
  - 最多提取前 50 页
  - 扫描版 PDF（图片）无法提取文字
- **用途**：论文分析、合同审阅、文档总结

### 5. Word 文档（文本提取）✨新增
- **格式**：docx（✅支持）、doc（❌暂不支持）
- **处理方式**：解压 ZIP 格式的 .docx，提取 XML 中的文本
- **限制**：
  - 旧版 .doc 格式需要转换为 .docx
  - 不保留格式信息（字体、颜色等）
- **用途**：文档分析、内容总结、校对润色

### 6. 表格文件（结构化数据）
- **格式**：csv, xlsx（部分支持）
- **处理方式**：读取并格式化表格数据
- **限制**：CSV 最多显示前 100 行
- **用途**：数据分析、统计查询

### 7. HTML/XML 文件（标签处理）
- **格式**：html, htm, xml
- **处理方式**：HTML 会移除脚本和样式标签后提取文本
- **用途**：网页内容分析、XML 数据解析

## 使用方法

### 1. 上传文件

在对话输入框下方，点击**"+"按钮**（上传文件）：
- 可以一次上传**多个文件**
- 文件会显示在附件预览区域
- 点击文件卡片可以查看详情或删除

### 2. 发送消息

- 上传文件后，输入你的问题
- 点击**发送按钮**，AI 会：
  1. 自动提取文件内容（文档/代码）
  2. 将内容作为上下文发送给模型
  3. 基于文件内容回答你的问题

### 3. 示例场景

#### 场景 1：分析 PDF 论文
```
1. 上传 research_paper.pdf
2. 输入："请总结这篇论文的主要观点"
3. AI 会提取 PDF 文本并进行总结
```

#### 场景 2：审查代码
```
1. 上传 main.py, utils.py
2. 输入："这段代码有什么潜在问题？"
3. AI 会分析所有上传的代码文件
```

#### 场景 3：处理 Word 文档
```
1. 上传 report.docx
2. 输入："帮我润色这份报告"
3. AI 提取文档内容并提供改进建议
```

#### 场景 4：分析图片
```
1. 上传 chart.png（图表截图）
2. 输入："这张图表说明了什么？"
3. AI 使用视觉能力分析图片
```

## 技术实现

### 文件处理流程

```
用户上传文件
    ↓
AttachedFile 模型
    ↓
发送消息时
    ↓
FileContentService.extractTextContent()
    ├─ 图片 → Base64 编码
    ├─ 文本/代码 → 直接读取
    ├─ PDF → Syncfusion PDF 提取
    ├─ DOCX → ZIP 解压 + XML 解析
    └─ 其他 → 文件信息
    ↓
OpenAIProvider._convertMessages()
    ↓
将内容添加到用户消息
    ↓
发送给 AI 模型
```

### 核心服务

- **FileContentService**：`lib/services/file_content_service.dart`
  - 负责提取各种文件类型的文本内容
  - 支持 PDF、Word、CSV、JSON 等

- **OpenAIProvider**：`lib/adapters/openai_provider.dart`
  - 处理多模态消息格式
  - 将文件内容整合到 API 请求

### 依赖包

```yaml
dependencies:
  # PDF 文本提取
  syncfusion_flutter_pdf: ^27.2.5
  
  # ZIP/压缩文件处理（用于解析 .docx）
  archive: ^3.4.0
  
  # 文件选择器
  file_picker: ^6.1.1
```

## 注意事项

### 1. Token 消耗
- 文件内容会占用 token 配额
- 大文件建议分批处理或截断
- PDF 限制前 50 页，CSV 限制 100 行

### 2. 隐私安全
- 文件在本地处理，不会额外上传
- 内容随消息发送给 AI 模型
- 敏感信息请谨慎上传

### 3. 格式限制
- **PDF**：扫描版（图片 PDF）无法提取文字，建议使用 OCR 工具预处理
- **Word**：仅支持 .docx，.doc 格式需要转换
- **Excel**：xlsx 支持有限，建议导出为 CSV

### 4. 模型支持
- **图片识别**：需要支持 Vision 的模型（如 GPT-4 Vision, Claude 3 Opus/Sonnet）
- **文本内容**：所有模型都支持

## 故障排除

### 问题 1：PDF 提取为空
- **原因**：可能是扫描版 PDF（图片）
- **解决**：使用 OCR 工具（如 Adobe Acrobat）转换为可搜索的 PDF

### 问题 2：Word 文档提取失败
- **原因**：旧版 .doc 格式不支持
- **解决**：用 Word 另存为 .docx 格式

### 问题 3：文件太大
- **原因**：文件内容超过模型 token 限制
- **解决**：
  - 分段上传
  - 提取关键部分
  - 使用支持更大上下文的模型

## 未来改进

- [ ] 支持 Excel (.xlsx) 完整提取
- [ ] 支持旧版 Word (.doc) 格式
- [ ] 支持扫描版 PDF 的 OCR
- [ ] 添加文件大小限制和警告
- [ ] 支持 PPT 文档提取
- [ ] 添加文件预览功能

## 相关代码

- 附件模型：`lib/models/attached_file.dart`
- 内容提取：`lib/services/file_content_service.dart`
- 消息转换：`lib/adapters/openai_provider.dart`
- UI 组件：`lib/widgets/enhanced_input_area.dart`
