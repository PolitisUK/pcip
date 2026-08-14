import 'package:flutter_test/flutter_test.dart';
import 'package:participant_app/main.dart';

void main() {
  test('non HTTPS endpoints fail closed before a request is sent', () async {
    await expectLater(
      Api(Uri.parse('http://example.invalid'), 'not-a-real-token').request('GET', '/session'),
      throwsA(isA<ApiException>()),
    );
  });
}
