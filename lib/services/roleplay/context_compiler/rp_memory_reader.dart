/// Memory Reader Interface
///
/// Provides read-only access to roleplay memory entries via snapshot pointers.
/// POS: Services / Roleplay / Context Compiler

import '../../../models/roleplay/rp_entry_blob.dart';
import '../../../models/roleplay/rp_snapshot.dart';
import '../rp_memory_repository.dart';

/// Abstract interface for reading memory entries
abstract class RpMemoryReader {
  /// Get entry blob by logical ID
  Future<RpEntryBlob?> getByLogicalId(String logicalId);

  /// Get all logical IDs for a domain
  Iterable<String> logicalIdsByDomain(String domain);

  /// Current foundation scope revision
  int get foundationRev;

  /// Current story scope revision
  int get storyRev;

  /// Current branch ID
  String get branchId;

  /// Story ID
  String get storyId;
}

/// Implementation backed by RpSnapshot and RpMemoryRepository
class RpMemoryReaderImpl implements RpMemoryReader {
  final RpMemoryRepository _repository;
  final RpSnapshot _snapshot;

  RpMemoryReaderImpl({
    required RpMemoryRepository repository,
    required RpSnapshot snapshot,
  })  : _repository = repository,
        _snapshot = snapshot;

  @override
  Future<RpEntryBlob?> getByLogicalId(String logicalId) async {
    final blobId = _snapshot.getBlobId(logicalId);
    if (blobId == null) return null;
    return _repository.getBlob(blobId);
  }

  @override
  Iterable<String> logicalIdsByDomain(String domain) {
    return _snapshot.getLogicalIdsByDomain(domain);
  }

  @override
  int get foundationRev => _snapshot.rev;

  @override
  int get storyRev => _snapshot.sourceRev;

  @override
  String get branchId => _snapshot.branchId;

  @override
  String get storyId => _snapshot.storyId;
}

/// Merged reader that combines foundation and story snapshots
class RpMergedMemoryReader implements RpMemoryReader {
  final RpMemoryRepository _repository;
  final RpSnapshot? _foundationSnapshot;
  final RpSnapshot? _storySnapshot;

  RpMergedMemoryReader({
    required RpMemoryRepository repository,
    RpSnapshot? foundationSnapshot,
    RpSnapshot? storySnapshot,
  })  : _repository = repository,
        _foundationSnapshot = foundationSnapshot,
        _storySnapshot = storySnapshot;

  @override
  Future<RpEntryBlob?> getByLogicalId(String logicalId) async {
    // Story scope takes precedence
    final storyBlobId = _storySnapshot?.getBlobId(logicalId);
    if (storyBlobId != null) {
      return _repository.getBlob(storyBlobId);
    }

    // Fallback to foundation
    final foundationBlobId = _foundationSnapshot?.getBlobId(logicalId);
    if (foundationBlobId != null) {
      return _repository.getBlob(foundationBlobId);
    }

    return null;
  }

  @override
  Iterable<String> logicalIdsByDomain(String domain) {
    final foundationIds = _foundationSnapshot?.getLogicalIdsByDomain(domain) ?? [];
    final storyIds = _storySnapshot?.getLogicalIdsByDomain(domain) ?? [];

    // Merge and dedupe (story overrides foundation)
    final merged = <String>{...foundationIds, ...storyIds};
    return merged;
  }

  @override
  int get foundationRev => _foundationSnapshot?.rev ?? 0;

  @override
  int get storyRev => _storySnapshot?.rev ?? 0;

  @override
  String get branchId => _storySnapshot?.branchId ?? _foundationSnapshot?.branchId ?? '';

  @override
  String get storyId => _storySnapshot?.storyId ?? _foundationSnapshot?.storyId ?? '';
}
