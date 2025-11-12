// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'attached_file.dart';

// **************************************************************************
// TypeAdapterGenerator
// **************************************************************************

class AttachedFileSnapshotAdapter extends TypeAdapter<AttachedFileSnapshot> {
  @override
  final int typeId = 3;

  @override
  AttachedFileSnapshot read(BinaryReader reader) {
    final numOfFields = reader.readByte();
    final fields = <int, dynamic>{
      for (int i = 0; i < numOfFields; i++) reader.readByte(): reader.read(),
    };
    return AttachedFileSnapshot(
      id: fields[0] as String,
      name: fields[1] as String,
      path: fields[2] as String,
      mimeType: fields[3] as String,
      type: fields[4] as FileType,
    );
  }

  @override
  void write(BinaryWriter writer, AttachedFileSnapshot obj) {
    writer
      ..writeByte(5)
      ..writeByte(0)
      ..write(obj.id)
      ..writeByte(1)
      ..write(obj.name)
      ..writeByte(2)
      ..write(obj.path)
      ..writeByte(3)
      ..write(obj.mimeType)
      ..writeByte(4)
      ..write(obj.type);
  }

  @override
  int get hashCode => typeId.hashCode;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is AttachedFileSnapshotAdapter &&
          runtimeType == other.runtimeType &&
          typeId == other.typeId;
}

class FileTypeAdapter extends TypeAdapter<FileType> {
  @override
  final int typeId = 2;

  @override
  FileType read(BinaryReader reader) {
    switch (reader.readByte()) {
      case 0:
        return FileType.image;
      case 1:
        return FileType.video;
      case 2:
        return FileType.audio;
      case 3:
        return FileType.document;
      case 4:
        return FileType.code;
      case 5:
        return FileType.other;
      default:
        return FileType.image;
    }
  }

  @override
  void write(BinaryWriter writer, FileType obj) {
    switch (obj) {
      case FileType.image:
        writer.writeByte(0);
        break;
      case FileType.video:
        writer.writeByte(1);
        break;
      case FileType.audio:
        writer.writeByte(2);
        break;
      case FileType.document:
        writer.writeByte(3);
        break;
      case FileType.code:
        writer.writeByte(4);
        break;
      case FileType.other:
        writer.writeByte(5);
        break;
    }
  }

  @override
  int get hashCode => typeId.hashCode;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is FileTypeAdapter &&
          runtimeType == other.runtimeType &&
          typeId == other.typeId;
}
