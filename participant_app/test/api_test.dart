import 'package:flutter_test/flutter_test.dart';
import 'package:participant_app/main.dart';

void main() {
  test('non HTTPS endpoints fail closed before a request is sent', () async {
    await expectLater(
      Api(Uri.parse('http://example.invalid'), 'not-a-real-token').request('GET', '/session'),
      throwsA(isA<ApiError>()),
    );
  });

  test('queue backoff is bounded and increases after transient failures', () {
    expect(Queue.backoff(0), const Duration(seconds: 1));
    expect(Queue.backoff(3), const Duration(seconds: 8));
    expect(Queue.backoff(99), const Duration(seconds: 64));
  });
}
