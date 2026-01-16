// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'rp_entry_blob.dart';

// **************************************************************************
// TypeAdapterGenerator
// **************************************************************************

class RpEntryBlobAdapter extends TypeAdapter<RpEntryBlob> {
  @override
  final int typeId = 53;

  @override
  RpEntryBlob read(BinaryReader reader) {
    final numOfFields = reader.readByte();
    final fields = <int, dynamic>{
      for (int i = 0; i < numOfFields; i++) reader.readByte(): reader.read(),
    };
    return RpEntryBlob(
      blobId: fields[0] as String,
      storyId: fields[1] as String,
      logicalId: fields[2] as String,
      scopeIndex: fields[3] as int,
      branchId: fields[4] as String,
      statusIndex: fields[5] as int,
      domain: fields[6] as String,
      entryType: fields[7] as String,
      contentJsonUtf8: fields[8] as Uint8List,
      preview: fields[9] as String?,
      tags: (fields[10] as List?)?.cast<String>(),
      evidence: (fields[11] as List?)?.cast<RpEvidenceRef>(),
      createdAtMs: fields[12] as int?,
      sourceRev: fields[13] as int,
      approxTokens: fields[14] as int?,
    );
  }

  @override
  void write(BinaryWriter writer, RpEntryBlob obj) {
    writer
      ..writeByte(15)
      ..writeByte(0)
      ..write(obj.blobId)
      ..writeByte(1)
      ..write(obj.storyId)
      ..writeByte(2)
      ..write(obj.logicalId)
      ..writeByte(3)
      ..write(obj.scopeIndex)
      ..writeByte(4)
      ..write(obj.branchId)
      ..writeByte(5)
      ..write(obj.statusIndex)
      ..writeByte(6)
      ..write(obj.domain)
      ..writeByte(7)
      ..write(obj.entryType)
      ..writeByte(8)
      ..write(obj.contentJsonUtf8)
      ..writeByte(9)
      ..write(obj.preview)
      ..writeByte(10)
      ..write(obj.tags)
      ..writeByte(11)
      ..write(obj.evidence)
      ..writeByte(12)
      ..write(obj.createdAtMs)
      ..writeByte(13)
      ..write(obj.sourceRev)
      ..writeByte(14)
      ..write(obj.approxTokens);
  }

  @override
  int get hashCode => typeId.hashCode;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is RpEntryBlobAdapter &&
          runtimeType == other.runtimeType &&
          typeId == other.typeId;
}

class RpEvidenceRefAdapter extends TypeAdapter<RpEvidenceRef> {
  @override
  final int typeId = 54;

  @override
  RpEvidenceRef read(BinaryReader reader) {
    final numOfFields = reader.readByte();
    final fields = <int, dynamic>{
      for (int i = 0; i < numOfFields; i++) reader.readByte(): reader.read(),
    };
    return RpEvidenceRef(
      type: fields[0] as String,
      refId: fields[1] as String,
      start: fields[2] as int?,
      end: fields[3] as int?,
      note: fields[4] as String?,
    );
  }

  @override
  void write(BinaryWriter writer, RpEvidenceRef obj) {
    writer
      ..writeByte(5)
      ..writeByte(0)
      ..write(obj.type)
      ..writeByte(1)
      ..write(obj.refId)
      ..writeByte(2)
      ..write(obj.start)
      ..writeByte(3)
      ..write(obj.end)
      ..writeByte(4)
      ..write(obj.note);
  }

  @override
  int get hashCode => typeId.hashCode;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is RpEvidenceRefAdapter &&
          runtimeType == other.runtimeType &&
          typeId == other.typeId;
}
