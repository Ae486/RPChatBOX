// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'rp_proposal.dart';

// **************************************************************************
// TypeAdapterGenerator
// **************************************************************************

class RpProposalAdapter extends TypeAdapter<RpProposal> {
  @override
  final int typeId = 58;

  @override
  RpProposal read(BinaryReader reader) {
    final numOfFields = reader.readByte();
    final fields = <int, dynamic>{
      for (int i = 0; i < numOfFields; i++) reader.readByte(): reader.read(),
    };
    return RpProposal(
      proposalId: fields[0] as String,
      storyId: fields[1] as String,
      branchId: fields[2] as String,
      createdAtMs: fields[3] as int?,
      kindIndex: fields[4] as int,
      domain: fields[5] as String,
      policyTierIndex: fields[6] as int,
      target: fields[7] as RpProposalTarget,
      payloadJsonUtf8: fields[8] as Uint8List,
      evidence: (fields[9] as List?)?.cast<RpEvidenceRef>(),
      reason: fields[10] as String,
      sourceRev: fields[11] as int,
      expectedFoundationRev: fields[12] as int,
      expectedStoryRev: fields[13] as int,
      decisionIndex: fields[14] as int,
      decidedAtMs: fields[15] as int?,
      decidedBy: fields[16] as String?,
      decisionNote: fields[17] as String?,
    );
  }

  @override
  void write(BinaryWriter writer, RpProposal obj) {
    writer
      ..writeByte(18)
      ..writeByte(0)
      ..write(obj.proposalId)
      ..writeByte(1)
      ..write(obj.storyId)
      ..writeByte(2)
      ..write(obj.branchId)
      ..writeByte(3)
      ..write(obj.createdAtMs)
      ..writeByte(4)
      ..write(obj.kindIndex)
      ..writeByte(5)
      ..write(obj.domain)
      ..writeByte(6)
      ..write(obj.policyTierIndex)
      ..writeByte(7)
      ..write(obj.target)
      ..writeByte(8)
      ..write(obj.payloadJsonUtf8)
      ..writeByte(9)
      ..write(obj.evidence)
      ..writeByte(10)
      ..write(obj.reason)
      ..writeByte(11)
      ..write(obj.sourceRev)
      ..writeByte(12)
      ..write(obj.expectedFoundationRev)
      ..writeByte(13)
      ..write(obj.expectedStoryRev)
      ..writeByte(14)
      ..write(obj.decisionIndex)
      ..writeByte(15)
      ..write(obj.decidedAtMs)
      ..writeByte(16)
      ..write(obj.decidedBy)
      ..writeByte(17)
      ..write(obj.decisionNote);
  }

  @override
  int get hashCode => typeId.hashCode;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is RpProposalAdapter &&
          runtimeType == other.runtimeType &&
          typeId == other.typeId;
}

class RpProposalTargetAdapter extends TypeAdapter<RpProposalTarget> {
  @override
  final int typeId = 59;

  @override
  RpProposalTarget read(BinaryReader reader) {
    final numOfFields = reader.readByte();
    final fields = <int, dynamic>{
      for (int i = 0; i < numOfFields; i++) reader.readByte(): reader.read(),
    };
    return RpProposalTarget(
      scopeIndex: fields[0] as int,
      branchId: fields[1] as String,
      statusIndex: fields[2] as int,
      logicalId: fields[3] as String,
    );
  }

  @override
  void write(BinaryWriter writer, RpProposalTarget obj) {
    writer
      ..writeByte(4)
      ..writeByte(0)
      ..write(obj.scopeIndex)
      ..writeByte(1)
      ..write(obj.branchId)
      ..writeByte(2)
      ..write(obj.statusIndex)
      ..writeByte(3)
      ..write(obj.logicalId);
  }

  @override
  int get hashCode => typeId.hashCode;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is RpProposalTargetAdapter &&
          runtimeType == other.runtimeType &&
          typeId == other.typeId;
}
