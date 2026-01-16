// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'rp_story_meta.dart';

// **************************************************************************
// TypeAdapterGenerator
// **************************************************************************

class RpStoryMetaAdapter extends TypeAdapter<RpStoryMeta> {
  @override
  final int typeId = 50;

  @override
  RpStoryMeta read(BinaryReader reader) {
    final numOfFields = reader.readByte();
    final fields = <int, dynamic>{
      for (int i = 0; i < numOfFields; i++) reader.readByte(): reader.read(),
    };
    return RpStoryMeta(
      storyId: fields[0] as String,
      schemaVersion: fields[1] as int,
      activeBranchId: fields[2] as String,
      sourceRev: fields[3] as int,
      heads: (fields[4] as List?)?.cast<RpHead>(),
      modules: (fields[5] as List?)?.cast<RpModuleState>(),
      moduleConfigJson: (fields[6] as Map?)?.cast<String, String>(),
      updatedAtMs: fields[7] as int?,
    );
  }

  @override
  void write(BinaryWriter writer, RpStoryMeta obj) {
    writer
      ..writeByte(8)
      ..writeByte(0)
      ..write(obj.storyId)
      ..writeByte(1)
      ..write(obj.schemaVersion)
      ..writeByte(2)
      ..write(obj.activeBranchId)
      ..writeByte(3)
      ..write(obj.sourceRev)
      ..writeByte(4)
      ..write(obj.heads)
      ..writeByte(5)
      ..write(obj.modules)
      ..writeByte(6)
      ..write(obj.moduleConfigJson)
      ..writeByte(7)
      ..write(obj.updatedAtMs);
  }

  @override
  int get hashCode => typeId.hashCode;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is RpStoryMetaAdapter &&
          runtimeType == other.runtimeType &&
          typeId == other.typeId;
}

class RpHeadAdapter extends TypeAdapter<RpHead> {
  @override
  final int typeId = 51;

  @override
  RpHead read(BinaryReader reader) {
    final numOfFields = reader.readByte();
    final fields = <int, dynamic>{
      for (int i = 0; i < numOfFields; i++) reader.readByte(): reader.read(),
    };
    return RpHead(
      scopeIndex: fields[0] as int,
      branchId: fields[1] as String,
      rev: fields[2] as int,
      lastSnapshotRev: fields[3] as int,
    );
  }

  @override
  void write(BinaryWriter writer, RpHead obj) {
    writer
      ..writeByte(4)
      ..writeByte(0)
      ..write(obj.scopeIndex)
      ..writeByte(1)
      ..write(obj.branchId)
      ..writeByte(2)
      ..write(obj.rev)
      ..writeByte(3)
      ..write(obj.lastSnapshotRev);
  }

  @override
  int get hashCode => typeId.hashCode;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is RpHeadAdapter &&
          runtimeType == other.runtimeType &&
          typeId == other.typeId;
}

class RpModuleStateAdapter extends TypeAdapter<RpModuleState> {
  @override
  final int typeId = 52;

  @override
  RpModuleState read(BinaryReader reader) {
    final numOfFields = reader.readByte();
    final fields = <int, dynamic>{
      for (int i = 0; i < numOfFields; i++) reader.readByte(): reader.read(),
    };
    return RpModuleState(
      moduleId: fields[0] as String,
      enabled: fields[1] as bool,
      lastDerivedSourceRev: fields[2] as int,
      dirty: fields[3] as bool,
      dirtySinceSourceRev: fields[4] as int,
      dirtyFromMessageId: fields[5] as String?,
      updatedAtMs: fields[6] as int?,
    );
  }

  @override
  void write(BinaryWriter writer, RpModuleState obj) {
    writer
      ..writeByte(7)
      ..writeByte(0)
      ..write(obj.moduleId)
      ..writeByte(1)
      ..write(obj.enabled)
      ..writeByte(2)
      ..write(obj.lastDerivedSourceRev)
      ..writeByte(3)
      ..write(obj.dirty)
      ..writeByte(4)
      ..write(obj.dirtySinceSourceRev)
      ..writeByte(5)
      ..write(obj.dirtyFromMessageId)
      ..writeByte(6)
      ..write(obj.updatedAtMs);
  }

  @override
  int get hashCode => typeId.hashCode;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is RpModuleStateAdapter &&
          runtimeType == other.runtimeType &&
          typeId == other.typeId;
}
