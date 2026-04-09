// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'mcp_server_config.dart';

// **************************************************************************
// TypeAdapterGenerator
// **************************************************************************

class McpServerConfigAdapter extends TypeAdapter<McpServerConfig> {
  @override
  final int typeId = 60;

  @override
  McpServerConfig read(BinaryReader reader) {
    final numOfFields = reader.readByte();
    final fields = <int, dynamic>{
      for (int i = 0; i < numOfFields; i++) reader.readByte(): reader.read(),
    };
    return McpServerConfig(
      id: fields[0] as String,
      name: fields[1] as String,
      transportType: fields[2] as String,
      url: fields[3] as String?,
      command: fields[4] as String?,
      args: (fields[5] as List?)?.cast<String>(),
      env: (fields[6] as Map?)?.cast<String, String>(),
      enabled: fields[7] as bool,
      createdAt: fields[8] as DateTime,
      lastConnectedAt: fields[9] as DateTime?,
      headers: (fields[10] as Map?)?.cast<String, String>(),
      description: fields[11] as String?,
    );
  }

  @override
  void write(BinaryWriter writer, McpServerConfig obj) {
    writer
      ..writeByte(12)
      ..writeByte(0)
      ..write(obj.id)
      ..writeByte(1)
      ..write(obj.name)
      ..writeByte(2)
      ..write(obj.transportType)
      ..writeByte(3)
      ..write(obj.url)
      ..writeByte(4)
      ..write(obj.command)
      ..writeByte(5)
      ..write(obj.args)
      ..writeByte(6)
      ..write(obj.env)
      ..writeByte(7)
      ..write(obj.enabled)
      ..writeByte(8)
      ..write(obj.createdAt)
      ..writeByte(9)
      ..write(obj.lastConnectedAt)
      ..writeByte(10)
      ..write(obj.headers)
      ..writeByte(11)
      ..write(obj.description);
  }

  @override
  int get hashCode => typeId.hashCode;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is McpServerConfigAdapter &&
          runtimeType == other.runtimeType &&
          typeId == other.typeId;
}
