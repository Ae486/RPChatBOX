// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'mcp_tool_call.dart';

// **************************************************************************
// TypeAdapterGenerator
// **************************************************************************

class McpToolCallRecordAdapter extends TypeAdapter<McpToolCallRecord> {
  @override
  final int typeId = 61;

  @override
  McpToolCallRecord read(BinaryReader reader) {
    final numOfFields = reader.readByte();
    final fields = <int, dynamic>{
      for (int i = 0; i < numOfFields; i++) reader.readByte(): reader.read(),
    };
    return McpToolCallRecord(
      callId: fields[0] as String,
      messageId: fields[1] as String,
      toolName: fields[2] as String,
      serverName: fields[3] as String?,
      status: fields[4] as String,
      durationMs: fields[5] as int?,
      argumentsJson: fields[6] as String?,
      result: fields[7] as String?,
      errorMessage: fields[8] as String?,
      timestamp: fields[9] as DateTime,
    );
  }

  @override
  void write(BinaryWriter writer, McpToolCallRecord obj) {
    writer
      ..writeByte(10)
      ..writeByte(0)
      ..write(obj.callId)
      ..writeByte(1)
      ..write(obj.messageId)
      ..writeByte(2)
      ..write(obj.toolName)
      ..writeByte(3)
      ..write(obj.serverName)
      ..writeByte(4)
      ..write(obj.status)
      ..writeByte(5)
      ..write(obj.durationMs)
      ..writeByte(6)
      ..write(obj.argumentsJson)
      ..writeByte(7)
      ..write(obj.result)
      ..writeByte(8)
      ..write(obj.errorMessage)
      ..writeByte(9)
      ..write(obj.timestamp);
  }

  @override
  int get hashCode => typeId.hashCode;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is McpToolCallRecordAdapter &&
          runtimeType == other.runtimeType &&
          typeId == other.typeId;
}
