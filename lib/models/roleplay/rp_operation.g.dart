// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'rp_operation.dart';

// **************************************************************************
// TypeAdapterGenerator
// **************************************************************************

class RpOperationAdapter extends TypeAdapter<RpOperation> {
  @override
  final int typeId = 55;

  @override
  RpOperation read(BinaryReader reader) {
    final numOfFields = reader.readByte();
    final fields = <int, dynamic>{
      for (int i = 0; i < numOfFields; i++) reader.readByte(): reader.read(),
    };
    return RpOperation(
      storyId: fields[0] as String,
      scopeIndex: fields[1] as int,
      branchId: fields[2] as String,
      rev: fields[3] as int,
      createdAtMs: fields[4] as int?,
      sourceRev: fields[5] as int,
      agent: fields[6] as String?,
      jobId: fields[7] as String?,
      changes: (fields[8] as List?)?.cast<RpEntryChange>(),
    );
  }

  @override
  void write(BinaryWriter writer, RpOperation obj) {
    writer
      ..writeByte(9)
      ..writeByte(0)
      ..write(obj.storyId)
      ..writeByte(1)
      ..write(obj.scopeIndex)
      ..writeByte(2)
      ..write(obj.branchId)
      ..writeByte(3)
      ..write(obj.rev)
      ..writeByte(4)
      ..write(obj.createdAtMs)
      ..writeByte(5)
      ..write(obj.sourceRev)
      ..writeByte(6)
      ..write(obj.agent)
      ..writeByte(7)
      ..write(obj.jobId)
      ..writeByte(8)
      ..write(obj.changes);
  }

  @override
  int get hashCode => typeId.hashCode;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is RpOperationAdapter &&
          runtimeType == other.runtimeType &&
          typeId == other.typeId;
}

class RpEntryChangeAdapter extends TypeAdapter<RpEntryChange> {
  @override
  final int typeId = 56;

  @override
  RpEntryChange read(BinaryReader reader) {
    final numOfFields = reader.readByte();
    final fields = <int, dynamic>{
      for (int i = 0; i < numOfFields; i++) reader.readByte(): reader.read(),
    };
    return RpEntryChange(
      logicalId: fields[0] as String,
      domain: fields[1] as String,
      beforeBlobId: fields[2] as String?,
      afterBlobId: fields[3] as String?,
      reasonKindIndex: fields[4] as int,
      evidence: (fields[5] as List?)?.cast<RpEvidenceRef>(),
      note: fields[6] as String?,
    );
  }

  @override
  void write(BinaryWriter writer, RpEntryChange obj) {
    writer
      ..writeByte(7)
      ..writeByte(0)
      ..write(obj.logicalId)
      ..writeByte(1)
      ..write(obj.domain)
      ..writeByte(2)
      ..write(obj.beforeBlobId)
      ..writeByte(3)
      ..write(obj.afterBlobId)
      ..writeByte(4)
      ..write(obj.reasonKindIndex)
      ..writeByte(5)
      ..write(obj.evidence)
      ..writeByte(6)
      ..write(obj.note);
  }

  @override
  int get hashCode => typeId.hashCode;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is RpEntryChangeAdapter &&
          runtimeType == other.runtimeType &&
          typeId == other.typeId;
}
