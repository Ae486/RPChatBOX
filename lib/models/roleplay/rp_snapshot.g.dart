// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'rp_snapshot.dart';

// **************************************************************************
// TypeAdapterGenerator
// **************************************************************************

class RpSnapshotAdapter extends TypeAdapter<RpSnapshot> {
  @override
  final int typeId = 57;

  @override
  RpSnapshot read(BinaryReader reader) {
    final numOfFields = reader.readByte();
    final fields = <int, dynamic>{
      for (int i = 0; i < numOfFields; i++) reader.readByte(): reader.read(),
    };
    return RpSnapshot(
      storyId: fields[0] as String,
      scopeIndex: fields[1] as int,
      branchId: fields[2] as String,
      rev: fields[3] as int,
      createdAtMs: fields[4] as int?,
      sourceRev: fields[5] as int,
      pointers: (fields[6] as Map?)?.cast<String, String>(),
      byDomain: (fields[7] as Map?)?.map((dynamic k, dynamic v) =>
          MapEntry(k as String, (v as List).cast<String>())),
    );
  }

  @override
  void write(BinaryWriter writer, RpSnapshot obj) {
    writer
      ..writeByte(8)
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
      ..write(obj.pointers)
      ..writeByte(7)
      ..write(obj.byDomain);
  }

  @override
  int get hashCode => typeId.hashCode;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is RpSnapshotAdapter &&
          runtimeType == other.runtimeType &&
          typeId == other.typeId;
}
