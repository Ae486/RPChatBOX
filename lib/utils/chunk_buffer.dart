import 'dart:async';
import 'package:flutter/material.dart';

class ChunkBuffer {
  final Function(String) onFlush;
  final Duration flushInterval;
  final int flushThreshold;
  final bool enableDebugLog;

  final StringBuffer _buffer = StringBuffer();
  Timer? _flushTimer;
  int _flushCount = 0;
  int _chunkCount = 0;

  ChunkBuffer({
    required this.onFlush,
    this.flushInterval = const Duration(milliseconds: 100),
    this.flushThreshold = 50,
    this.enableDebugLog = false,
  });

  void add(String chunk) {
    _buffer.write(chunk);
    _chunkCount++;

    if (enableDebugLog && _chunkCount % 10 == 0) {
      debugPrint('ChunkBuffer: Received $_chunkCount chunks, buffer size: ${_buffer.length}');
    }

    if (_buffer.length >= flushThreshold) {
      if (enableDebugLog) {
        debugPrint('ChunkBuffer: Flush triggered by threshold (${_buffer.length} >= $flushThreshold)');
      }
      flush();
      return;
    }

    _flushTimer?.cancel();
    _flushTimer = Timer(flushInterval, flush);
  }

  void flush() {
    if (_buffer.isEmpty) return;

    _flushTimer?.cancel();
    _flushCount++;

    if (enableDebugLog) {
      debugPrint('ChunkBuffer: Flush #$_flushCount - ${_buffer.length} chars');
    }

    onFlush(_buffer.toString());
    _buffer.clear();
  }

  void dispose() {
    if (enableDebugLog) {
      debugPrint('ChunkBuffer: Dispose - Total chunks: $_chunkCount, Total flushes: $_flushCount');
    }
    flush();
    _flushTimer?.cancel();
  }
}
