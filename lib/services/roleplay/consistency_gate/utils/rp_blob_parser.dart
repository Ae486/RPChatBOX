/// Blob Parser Utilities
///
/// Provides safe JSON parsing utilities for RpEntryBlob.
/// POS: Services / Roleplay / Consistency Gate / Utils

import 'dart:convert';

import '../../../../models/roleplay/rp_entry_blob.dart';

/// Extension on RpEntryBlob for safe JSON parsing
extension RpEntryBlobParser on RpEntryBlob {
  /// Safely parse the blob content as JSON Map.
  ///
  /// Returns empty map if:
  /// - Content is empty
  /// - Content is not valid JSON
  /// - Content is not a Map
  Map<String, dynamic> safeParseJson() {
    try {
      if (contentJsonUtf8.isEmpty) return {};
      final content = utf8.decode(contentJsonUtf8);
      final decoded = jsonDecode(content);
      return decoded is Map<String, dynamic> ? decoded : {};
    } catch (_) {
      return {};
    }
  }

  /// Safely parse and get a typed value from the blob content.
  ///
  /// Returns null if the key doesn't exist or the value is not of type T.
  T? safeGetValue<T>(String key) {
    final data = safeParseJson();
    final value = data[key];
    return value is T ? value : null;
  }

  /// Safely parse and get a nested value using dot notation.
  ///
  /// Example: `blob.safeGetNested<String>('appearance.hair.color')`
  T? safeGetNested<T>(String path) {
    final keys = path.split('.');
    dynamic current = safeParseJson();

    for (final key in keys) {
      if (current is! Map<String, dynamic>) return null;
      current = current[key];
      if (current == null) return null;
    }

    return current is T ? current : null;
  }

  /// Safely parse and get a list from the blob content.
  ///
  /// Returns empty list if the key doesn't exist or the value is not a List.
  List<T> safeGetList<T>(String key) {
    final data = safeParseJson();
    final value = data[key];
    if (value is! List) return [];
    return value.whereType<T>().toList();
  }
}

/// Standalone function for parsing blob content (for use without extension)
Map<String, dynamic> parseBlobJson(RpEntryBlob blob) {
  return blob.safeParseJson();
}
