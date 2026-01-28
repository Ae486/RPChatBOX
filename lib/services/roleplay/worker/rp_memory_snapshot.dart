/// 内存快照
///
/// 为 Worker Isolate 构建只读内存快照
/// POS: Services / Roleplay / Worker
library;

import 'dart:convert';
import 'dart:developer';

import '../../../models/roleplay/rp_entry_blob.dart';
import '../../../models/roleplay/rp_story_meta.dart';
import '../rp_memory_repository.dart';
import 'rp_version_gate.dart';
import 'rp_worker_protocol.dart';

/// 内存快照构建器
///
/// 从 RpMemoryRepository 提取 Worker 所需的数据
/// 转换为可跨 Isolate 传输的 JSON 格式
class RpMemorySnapshotBuilder {
  final RpMemoryRepository _repo;

  RpMemorySnapshotBuilder(this._repo);

  /// 构建快照
  ///
  /// [storyId] 故事 ID
  /// [branchId] 分支 ID
  /// [requiredDomains] 需要的领域列表（为空则获取全部）
  /// [recentMessages] 最近消息列表
  Future<Map<String, dynamic>> build({
    required String storyId,
    required String branchId,
    List<String>? requiredDomains,
    List<Map<String, dynamic>>? recentMessages,
  }) async {
    final snapshot = <String, dynamic>{};

    // 获取 StoryMeta
    final meta = await _repo.getStoryMeta(storyId);
    if (meta == null) {
      log('快照构建失败: 未找到 StoryMeta $storyId', name: 'RpMemorySnapshot');
      return snapshot;
    }

    snapshot['meta'] = _serializeMeta(meta);
    snapshot['version'] = RpVersionGate.getCurrentSnapshot(meta, branchId).toJson();

    // 添加最近消息
    if (recentMessages != null && recentMessages.isNotEmpty) {
      snapshot['recentMessages'] = recentMessages;
    }

    // 获取相关 Entries
    final entries = <String, List<Map<String, dynamic>>>{};
    // 空列表或 null 都回退到默认领域
    final domains = (requiredDomains == null || requiredDomains.isEmpty)
        ? _getDefaultDomains()
        : requiredDomains;

    for (final domain in domains) {
      final domainEntries = await _getEntriesByDomain(
        storyId,
        branchId,
        domain,
      );
      if (domainEntries.isNotEmpty) {
        entries[domain] = domainEntries;
      }
    }
    snapshot['entries'] = entries;

    // 检查快照大小
    final size = RpWorkerSerializer.estimateJsonSize(snapshot);
    if (size > RpWorkerSerializer.maxSnapshotSize) {
      log(
        '快照体积警告: ${(size / 1024).toStringAsFixed(1)}KB > 512KB',
        name: 'RpMemorySnapshot',
      );
      // 触发降级：只保留必要字段
      snapshot['entries'] = _trimEntries(entries, RpWorkerSerializer.maxSnapshotSize - 1024);
      snapshot['_trimmed'] = true;
    }

    log(
      '快照构建完成: ${(size / 1024).toStringAsFixed(1)}KB, domains=${entries.keys.toList()}',
      name: 'RpMemorySnapshot',
    );

    return snapshot;
  }

  /// 序列化 StoryMeta
  Map<String, dynamic> _serializeMeta(RpStoryMeta meta) {
    return {
      'storyId': meta.storyId,
      'schemaVersion': meta.schemaVersion,
      'activeBranchId': meta.activeBranchId,
      'sourceRev': meta.sourceRev,
      'updatedAtMs': meta.updatedAtMs,
      'heads': meta.heads
          .map((h) => {
                'scopeIndex': h.scopeIndex,
                'branchId': h.branchId,
                'rev': h.rev,
                'lastSnapshotRev': h.lastSnapshotRev,
              })
          .toList(),
      'modules': meta.modules
          .map((m) => {
                'moduleId': m.moduleId,
                'enabled': m.enabled,
                'lastDerivedSourceRev': m.lastDerivedSourceRev,
                'dirty': m.dirty,
                'dirtySinceSourceRev': m.dirtySinceSourceRev,
              })
          .toList(),
    };
  }

  /// 获取指定领域的条目
  Future<List<Map<String, dynamic>>> _getEntriesByDomain(
    String storyId,
    String branchId,
    String domain,
  ) async {
    final allBlobs = await _repo.getBlobsByStory(storyId);
    final blobs = allBlobs
        .where((b) => b.branchId == branchId && b.domain == domain)
        .toList();

    return blobs.map(_serializeBlob).toList();
  }

  /// 序列化 EntryBlob
  Map<String, dynamic> _serializeBlob(RpEntryBlob blob) {
    return {
      'blobId': blob.blobId,
      'logicalId': blob.logicalId,
      'scopeIndex': blob.scopeIndex,
      'branchId': blob.branchId,
      'statusIndex': blob.statusIndex,
      'domain': blob.domain,
      'entryType': blob.entryType,
      'contentJson': blob.contentJson,
      'preview': blob.preview,
      'tags': blob.tags,
      'sourceRev': blob.sourceRev,
      'approxTokens': blob.approxTokens,
      'evidence': blob.evidence
          .map((e) => {
                'type': e.type,
                'refId': e.refId,
                'start': e.start,
                'end': e.end,
                'note': e.note,
              })
          .toList(),
    };
  }

  /// 默认领域列表
  List<String> _getDefaultDomains() {
    return [
      'scene',
      'character',
      'state',
      'goals',
      'foreshadow',
      'world',
      'timeline',
      'style',
      'mechanics',
    ];
  }

  /// 裁剪条目以控制大小
  Map<String, List<Map<String, dynamic>>> _trimEntries(
    Map<String, List<Map<String, dynamic>>> entries,
    int maxSize,
  ) {
    final result = <String, List<Map<String, dynamic>>>{};

    // 优先级：scene > character > state > 其他
    final priorityOrder = ['scene', 'character', 'state'];
    int currentSize = 0;

    // 先添加高优先级领域
    for (final domain in priorityOrder) {
      if (entries.containsKey(domain)) {
        final domainEntries = entries[domain]!;
        final domainJson = jsonEncode(domainEntries);
        final domainSize = utf8.encode(domainJson).length;

        if (currentSize + domainSize <= maxSize) {
          result[domain] = domainEntries;
          currentSize += domainSize;
        }
      }
    }

    // 再添加其他领域（如果有空间）
    for (final entry in entries.entries) {
      if (!priorityOrder.contains(entry.key) && !result.containsKey(entry.key)) {
        final domainJson = jsonEncode(entry.value);
        final domainSize = utf8.encode(domainJson).length;

        if (currentSize + domainSize <= maxSize) {
          result[entry.key] = entry.value;
          currentSize += domainSize;
        }
      }
    }

    return result;
  }
}

/// Worker 侧只读内存访问器
///
/// 在 Worker Isolate 中使用，提供对快照数据的只读访问
class RpWorkerMemoryReader {
  final Map<String, dynamic> _snapshot;

  RpWorkerMemoryReader(this._snapshot);

  /// 是否有效
  bool get isValid => _snapshot.isNotEmpty;

  /// 是否被裁剪
  bool get isTrimmed => _snapshot['_trimmed'] == true;

  /// 获取 meta 信息
  Map<String, dynamic>? get meta =>
      _snapshot['meta'] as Map<String, dynamic>?;

  /// 获取版本快照
  RpVersionSnapshot? get version {
    final v = _snapshot['version'] as Map<String, dynamic>?;
    return v != null ? RpVersionSnapshot.fromJson(v) : null;
  }

  /// 获取故事 ID
  String? get storyId => meta?['storyId'] as String?;

  /// 获取活动分支 ID
  String? get activeBranchId => meta?['activeBranchId'] as String?;

  /// 获取对话源版本号
  int get sourceRev => meta?['sourceRev'] as int? ?? 0;

  /// 获取所有可用领域
  List<String> get availableDomains {
    final entries = _snapshot['entries'] as Map<String, dynamic>?;
    return entries?.keys.toList() ?? [];
  }

  /// 获取指定领域的条目
  List<Map<String, dynamic>> getEntriesByDomain(String domain) {
    final entries = _snapshot['entries'] as Map<String, dynamic>?;
    if (entries == null) return [];

    final domainEntries = entries[domain];
    if (domainEntries == null) return [];

    return (domainEntries as List).cast<Map<String, dynamic>>();
  }

  /// 获取指定 logicalId 的条目
  Map<String, dynamic>? getEntryByLogicalId(String logicalId) {
    final entries = _snapshot['entries'] as Map<String, dynamic>?;
    if (entries == null) return null;

    for (final domainEntries in entries.values) {
      for (final entry in (domainEntries as List)) {
        if (entry['logicalId'] == logicalId) {
          return entry as Map<String, dynamic>;
        }
      }
    }
    return null;
  }

  /// 获取模块状态
  Map<String, dynamic>? getModuleState(String moduleId) {
    final modules = meta?['modules'] as List?;
    if (modules == null) return null;

    for (final m in modules) {
      if ((m as Map)['moduleId'] == moduleId) {
        return m as Map<String, dynamic>;
      }
    }
    return null;
  }

  /// 检查模块是否启用
  bool isModuleEnabled(String moduleId) {
    final state = getModuleState(moduleId);
    return state?['enabled'] as bool? ?? false;
  }

  /// 获取 head 信息
  Map<String, dynamic>? getHead(int scopeIndex, String branchId) {
    final heads = meta?['heads'] as List?;
    if (heads == null) return null;

    for (final h in heads) {
      final head = h as Map<String, dynamic>;
      if (head['scopeIndex'] == scopeIndex && head['branchId'] == branchId) {
        return head;
      }
    }
    return null;
  }

  /// 解析条目内容 JSON
  Map<String, dynamic>? parseEntryContent(Map<String, dynamic> entry) {
    final contentJson = entry['contentJson'] as String?;
    if (contentJson == null) return null;

    try {
      return jsonDecode(contentJson) as Map<String, dynamic>;
    } catch (e) {
      return null;
    }
  }

  /// 获取所有条目的预览列表（用于调试）
  List<String> getEntryPreviews() {
    final previews = <String>[];
    final entries = _snapshot['entries'] as Map<String, dynamic>?;
    if (entries == null) return previews;

    for (final domainEntry in entries.entries) {
      for (final entry in (domainEntry.value as List)) {
        final e = entry as Map<String, dynamic>;
        final preview = e['preview'] as String? ?? e['logicalId'] as String?;
        if (preview != null) {
          previews.add('[${domainEntry.key}] $preview');
        }
      }
    }
    return previews;
  }

  /// 获取当前场景
  Map<String, dynamic>? getCurrentScene() {
    final sceneEntries = getEntriesByDomain('scene');
    if (sceneEntries.isEmpty) return null;

    // 返回最新的场景条目
    final latest = sceneEntries.last;
    final content = parseEntryContent(latest);
    return content ?? {
      'location': latest['preview'],
    };
  }

  /// 获取角色列表
  List<Map<String, dynamic>> getCharacters() {
    final characterEntries = getEntriesByDomain('character');
    return characterEntries.map((entry) {
      final content = parseEntryContent(entry);
      return content ?? {
        'name': entry['preview'] ?? entry['logicalId'],
        'description': '',
      };
    }).toList();
  }

  /// 获取最近消息
  List<Map<String, dynamic>> getRecentMessages({int limit = 10}) {
    // 从 inputs 中获取消息（如果有）
    final messages = _snapshot['recentMessages'] as List?;
    if (messages == null) return [];

    final result = messages
        .take(limit)
        .map((m) => m as Map<String, dynamic>)
        .toList();
    return result;
  }
}
