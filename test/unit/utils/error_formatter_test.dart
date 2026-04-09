import 'package:chatboxapp/utils/error_formatter.dart' as err;
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('requestAborted returns reusable error info', () {
    final errorInfo = err.ErrorFormatter.requestAborted();

    expect(errorInfo.brief, err.ErrorFormatter.requestAbortedMessage);
    expect(errorInfo.details, err.ErrorFormatter.requestAbortedMessage);
    expect(
      errorInfo.toErrorTag(),
      contains('brief="${err.ErrorFormatter.requestAbortedMessage}"'),
    );
    expect(
      errorInfo.toErrorTag(),
      contains('>${err.ErrorFormatter.requestAbortedMessage}</error>'),
    );
  });

  test('parse accepts ErrorInfo directly', () {
    final aborted = err.ErrorFormatter.requestAborted();

    final parsed = err.ErrorFormatter.parse(aborted);

    expect(parsed, same(aborted));
  });
}
