import 'dart:io';

/// 附件文件模型
/// 用于多模态对话中的文件上传和管理
class AttachedFile {
  final String id;
  final String name;
  final String path;
  final String mimeType;
  final int sizeBytes;
  final FileType type;
  final DateTime uploadedAt;
  final String? thumbnail;
  final Map<String, dynamic> metadata;

  AttachedFile({
    required this.id,
    required this.name,
    required this.path,
    required this.mimeType,
    required this.sizeBytes,
    required this.type,
    DateTime? uploadedAt,
    this.thumbnail,
    Map<String, dynamic>? metadata,
  })  : uploadedAt = uploadedAt ?? DateTime.now(),
        metadata = metadata ?? {};

  /// 从JSON创建实例
  factory AttachedFile.fromJson(Map<String, dynamic> json) {
    return AttachedFile(
      id: json['id'] as String,
      name: json['name'] as String,
      path: json['path'] as String,
      mimeType: json['mimeType'] as String,
      sizeBytes: json['sizeBytes'] as int,
      type: FileType.values.firstWhere(
        (e) => e.name == json['type'],
        orElse: () => FileType.other,
      ),
      uploadedAt: DateTime.parse(json['uploadedAt'] as String),
      thumbnail: json['thumbnail'] as String?,
      metadata: Map<String, dynamic>.from(json['metadata'] ?? {}),
    );
  }

  /// 转换为JSON
  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'path': path,
      'mimeType': mimeType,
      'sizeBytes': sizeBytes,
      'type': type.name,
      'uploadedAt': uploadedAt.toIso8601String(),
      'thumbnail': thumbnail,
      'metadata': metadata,
    };
  }

  /// 从文件创建实例
  static Future<AttachedFile> fromFile(File file, String id) async {
    final stat = await file.stat();
    final mimeType = _getMimeType(file.path);
    final type = _getFileType(mimeType);

    return AttachedFile(
      id: id,
      name: file.path.split('/').last,
      path: file.path,
      mimeType: mimeType,
      sizeBytes: stat.size,
      type: type,
    );
  }

  /// 复制并修改部分字段
  AttachedFile copyWith({
    String? id,
    String? name,
    String? path,
    String? mimeType,
    int? sizeBytes,
    FileType? type,
    DateTime? uploadedAt,
    String? thumbnail,
    Map<String, dynamic>? metadata,
  }) {
    return AttachedFile(
      id: id ?? this.id,
      name: name ?? this.name,
      path: path ?? this.path,
      mimeType: mimeType ?? this.mimeType,
      sizeBytes: sizeBytes ?? this.sizeBytes,
      type: type ?? this.type,
      uploadedAt: uploadedAt ?? this.uploadedAt,
      thumbnail: thumbnail ?? this.thumbnail,
      metadata: metadata ?? this.metadata,
    );
  }

  /// 获取格式化的文件大小
  String get formattedSize {
    if (sizeBytes < 1024) return '$sizeBytes B';
    if (sizeBytes < 1024 * 1024) return '${(sizeBytes / 1024).toStringAsFixed(1)} KB';
    if (sizeBytes < 1024 * 1024 * 1024) {
      return '${(sizeBytes / (1024 * 1024)).toStringAsFixed(1)} MB';
    }
    return '${(sizeBytes / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB';
  }

  /// 获取文件扩展名
  String get extension {
    final parts = name.split('.');
    return parts.length > 1 ? parts.last.toLowerCase() : '';
  }

  /// 是否为图片文件
  bool get isImage => type == FileType.image;

  /// 是否为视频文件
  bool get isVideo => type == FileType.video;

  /// 是否为音频文件
  bool get isAudio => type == FileType.audio;

  /// 是否为文档文件
  bool get isDocument => type == FileType.document;

  /// 是否为代码文件
  bool get isCode => type == FileType.code;

  /// 获取文件对象
  File get file => File(path);

  /// 检查文件是否存在
  Future<bool> exists() async {
    return await file.exists();
  }

  /// 删除文件
  Future<void> delete() async {
    final f = file;
    if (await f.exists()) {
      await f.delete();
    }
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is AttachedFile && other.id == id;
  }

  @override
  int get hashCode => id.hashCode;

  /// 根据文件路径推断MIME类型
  static String _getMimeType(String path) {
    final ext = path.split('.').last.toLowerCase();
    final mimeTypes = {
      // 图片
      'jpg': 'image/jpeg',
      'jpeg': 'image/jpeg',
      'png': 'image/png',
      'gif': 'image/gif',
      'webp': 'image/webp',
      'svg': 'image/svg+xml',
      'bmp': 'image/bmp',
      // 视频
      'mp4': 'video/mp4',
      'mov': 'video/quicktime',
      'avi': 'video/x-msvideo',
      'webm': 'video/webm',
      'mkv': 'video/x-matroska',
      // 音频
      'mp3': 'audio/mpeg',
      'wav': 'audio/wav',
      'ogg': 'audio/ogg',
      'm4a': 'audio/mp4',
      'flac': 'audio/flac',
      // 文档
      'pdf': 'application/pdf',
      'doc': 'application/msword',
      'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'xls': 'application/vnd.ms-excel',
      'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'ppt': 'application/vnd.ms-powerpoint',
      'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      'txt': 'text/plain',
      'md': 'text/markdown',
      // 代码
      'js': 'text/javascript',
      'py': 'text/x-python',
      'java': 'text/x-java',
      'cpp': 'text/x-c++src',
      'c': 'text/x-csrc',
      'h': 'text/x-chdr',
      'cs': 'text/x-csharp',
      'go': 'text/x-go',
      'rs': 'text/x-rust',
      'swift': 'text/x-swift',
      'kt': 'text/x-kotlin',
      'dart': 'application/dart',
      'html': 'text/html',
      'css': 'text/css',
      'json': 'application/json',
      'xml': 'application/xml',
      'yaml': 'application/x-yaml',
      'yml': 'application/x-yaml',
    };

    return mimeTypes[ext] ?? 'application/octet-stream';
  }

  /// 根据MIME类型推断文件类型
  static FileType _getFileType(String mimeType) {
    if (mimeType.startsWith('image/')) return FileType.image;
    if (mimeType.startsWith('video/')) return FileType.video;
    if (mimeType.startsWith('audio/')) return FileType.audio;
    if (mimeType.startsWith('text/')) {
      if (mimeType.contains('javascript') ||
          mimeType.contains('python') ||
          mimeType.contains('java') ||
          mimeType.contains('c++') ||
          mimeType.contains('csrc') ||
          mimeType.contains('csharp') ||
          mimeType.contains('html') ||
          mimeType.contains('css')) {
        return FileType.code;
      }
      return FileType.document;
    }
    if (mimeType.contains('pdf') ||
        mimeType.contains('word') ||
        mimeType.contains('excel') ||
        mimeType.contains('powerpoint') ||
        mimeType.contains('markdown')) {
      return FileType.document;
    }
    if (mimeType.contains('json') || mimeType.contains('xml') || mimeType.contains('yaml')) {
      return FileType.code;
    }
    if (mimeType == 'application/dart') return FileType.code;

    return FileType.other;
  }
}

/// 文件类型枚举
enum FileType {
  image('图片'),
  video('视频'),
  audio('音频'),
  document('文档'),
  code('代码'),
  other('其他');

  final String displayName;

  const FileType(this.displayName);
}
