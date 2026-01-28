/// Timeline Validator
///
/// Heavy validator that detects timeline inconsistencies
/// (events not occurred, sequence errors, event conflicts).
/// POS: Services / Roleplay / Consistency Gate / Validators

import '../rp_validator.dart';
import '../rp_violation.dart';
import '../rp_validation_context.dart';
import '../utils/rp_blob_parser.dart';
import '../../../../models/roleplay/rp_entry_blob.dart';

/// Validates timeline consistency (Heavy - triggered only when needed)
class TimelineValidator extends RpValidator {
  @override
  String get id => 'timeline';

  @override
  String get displayName => 'Timeline Validator';

  @override
  ValidatorWeight get weight => ValidatorWeight.heavy;

  @override
  double get defaultThreshold => ValidatorThresholds.timeline;

  @override
  Future<List<RpViolation>> validate(RpValidationContext ctx) async {
    final violations = <RpViolation>[];
    final text = ctx.getTextForValidation();

    // Get timeline entries
    final timelineLogicalIds = ctx.memory.logicalIdsByDomain('tl').toList();

    final events = <_TimelineEvent>[];

    for (final logicalId in timelineLogicalIds) {
      final blob = await ctx.memory.getByLogicalId(logicalId);
      if (blob == null) continue;

      final eventData = blob.safeParseJson();
      if (eventData.isNotEmpty) {
        events.add(_TimelineEvent(
          logicalId: logicalId,
          name: eventData['name']?.toString() ?? '',
          description: eventData['description']?.toString() ?? '',
          occurred: eventData['occurred'] == true,
          sequence: eventData['sequence'] as int? ?? 0,
          keywords: _extractKeywords(eventData),
        ));
      }
    }

    if (events.isEmpty) {
      return []; // No timeline data to validate against
    }

    // Check for references to events that haven't occurred
    for (final event in events) {
      if (!event.occurred && _mentionsEvent(text, event)) {
        violations.add(RpViolation(
          code: ViolationCode.eventNotOccurred,
          severity: ViolationSeverity.warn,
          message: 'Output references event "${event.name}" '
              'which has not occurred yet',
          expected: 'Event has occurred',
          found: 'Event not yet occurred',
          confidence: 0.75,
          evidence: [
            RpEvidenceRef(
              type: 'validator',
              refId: event.logicalId,
              note: 'timeline.event',
            ),
          ],
          recommended: [
            ProposeMemoryPatch(
              domain: 'tl',
              logicalId: event.logicalId,
              patch: {'occurred': true},
              description: 'Mark event "${event.name}" as occurred',
            ),
            SuggestUserCorrection(
              'Event "${event.name}" has not happened yet in the story',
            ),
          ],
          validatorId: id,
          detectedAt: DateTime.now(),
        ));
      }
    }

    // Check for sequence violations (mentioning later events before earlier ones)
    final mentionedEvents = events.where((e) => _mentionsEvent(text, e)).toList();
    mentionedEvents.sort((a, b) => a.sequence.compareTo(b.sequence));

    for (int i = 0; i < mentionedEvents.length - 1; i++) {
      final current = mentionedEvents[i];
      final next = mentionedEvents[i + 1];

      // Check if current event is mentioned after next event in the text
      final currentPos = _findEventPosition(text, current);
      final nextPos = _findEventPosition(text, next);

      if (currentPos > nextPos && current.sequence < next.sequence) {
        violations.add(RpViolation(
          code: ViolationCode.timeSequenceError,
          severity: ViolationSeverity.info,
          message: 'Event sequence may be incorrect: "${current.name}" '
              'mentioned after "${next.name}" but occurred earlier',
          expected: 'Events mentioned in chronological order',
          found: 'Events mentioned out of order',
          confidence: 0.6,
          evidence: [
            RpEvidenceRef(
              type: 'validator',
              refId: current.logicalId,
              note: 'timeline.sequence',
            ),
            RpEvidenceRef(
              type: 'validator',
              refId: next.logicalId,
              note: 'timeline.sequence',
            ),
          ],
          recommended: [
            SuggestIgnore(
              'Event order in narration may be intentional for storytelling',
            ),
          ],
          validatorId: id,
          detectedAt: DateTime.now(),
        ));
      }
    }

    return filterByThreshold(violations);
  }

  /// Extract keywords from event data
  List<String> _extractKeywords(Map<String, dynamic> data) {
    final keywords = <String>[];

    if (data['keywords'] is List) {
      keywords.addAll((data['keywords'] as List).map((e) => e.toString()));
    }

    // Also use name and description as keywords
    if (data['name'] != null) {
      keywords.addAll(data['name'].toString().split(' '));
    }

    return keywords;
  }

  /// Check if text mentions an event
  bool _mentionsEvent(String text, _TimelineEvent event) {
    final textLower = text.toLowerCase();

    // Check name
    if (event.name.isNotEmpty &&
        textLower.contains(event.name.toLowerCase())) {
      return true;
    }

    // Check keywords
    for (final keyword in event.keywords) {
      if (keyword.length > 3 && textLower.contains(keyword.toLowerCase())) {
        return true;
      }
    }

    return false;
  }

  /// Find the position where an event is mentioned in text
  int _findEventPosition(String text, _TimelineEvent event) {
    final textLower = text.toLowerCase();

    // Try name first
    if (event.name.isNotEmpty) {
      final pos = textLower.indexOf(event.name.toLowerCase());
      if (pos >= 0) return pos;
    }

    // Try keywords
    for (final keyword in event.keywords) {
      if (keyword.length > 3) {
        final pos = textLower.indexOf(keyword.toLowerCase());
        if (pos >= 0) return pos;
      }
    }

    return -1;
  }
}

/// Internal class representing a timeline event
class _TimelineEvent {
  final String logicalId;
  final String name;
  final String description;
  final bool occurred;
  final int sequence;
  final List<String> keywords;

  const _TimelineEvent({
    required this.logicalId,
    required this.name,
    required this.description,
    required this.occurred,
    required this.sequence,
    required this.keywords,
  });
}
