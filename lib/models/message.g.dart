// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'message.dart';

// **************************************************************************
// TypeAdapterGenerator
// **************************************************************************

class MessageAdapter extends TypeAdapter<Message> {
  @override
  final int typeId = 1;

  @override
  Message read(BinaryReader reader) {
    final numOfFields = reader.readByte();
    final fields = <int, dynamic>{
      for (int i = 0; i < numOfFields; i++) reader.readByte(): reader.read(),
    };
    return Message(
      id: fields[0] as String,
      content: fields[1] as String,
      isUser: fields[2] as bool,
      timestamp: fields[3] as DateTime,
      inputTokens: fields[4] as int?,
      outputTokens: fields[5] as int?,
      modelName: fields[6] as String?,
      providerName: fields[7] as String?,
      attachedFiles: (fields[8] as List?)?.cast<AttachedFileSnapshot>(),
      parentId: fields[9] as String?,
      editedAt: fields[10] as DateTime?,
      thinkingDurationSeconds: fields[11] as int?,
    );
  }

  @override
  void write(BinaryWriter writer, Message obj) {
    writer
      ..writeByte(12)
      ..writeByte(0)
      ..write(obj.id)
      ..writeByte(1)
      ..write(obj.content)
      ..writeByte(2)
      ..write(obj.isUser)
      ..writeByte(3)
      ..write(obj.timestamp)
      ..writeByte(4)
      ..write(obj.inputTokens)
      ..writeByte(5)
      ..write(obj.outputTokens)
      ..writeByte(6)
      ..write(obj.modelName)
      ..writeByte(7)
      ..write(obj.providerName)
      ..writeByte(8)
      ..write(obj.attachedFiles)
      ..writeByte(9)
      ..write(obj.parentId)
      ..writeByte(10)
      ..write(obj.editedAt)
      ..writeByte(11)
      ..write(obj.thinkingDurationSeconds);
  }

  @override
  int get hashCode => typeId.hashCode;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is MessageAdapter &&
          runtimeType == other.runtimeType &&
          typeId == other.typeId;
}
