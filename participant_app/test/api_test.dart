import 'package:flutter_test/flutter_test.dart';
import 'package:participant_app/main.dart';
import 'package:shared_preferences/shared_preferences.dart';

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

  test('logout cache cleanup retains no participant data', () async {
    SharedPreferences.setMockInitialValues({
      'cached_profile': '{"display_name":"Synthetic participant"}',
      'cached_history': '[]',
      'cached_messages': '[]',
      'submission_queue': <String>['{}'],
      'draft_12': 'Synthetic draft',
      'non_sensitive_setting': true,
    });
    final prefs = await SharedPreferences.getInstance();

    await clearParticipantCache(prefs);

    expect(prefs.containsKey('cached_profile'), isFalse);
    expect(prefs.containsKey('cached_history'), isFalse);
    expect(prefs.containsKey('cached_messages'), isFalse);
    expect(prefs.containsKey('submission_queue'), isFalse);
    expect(prefs.containsKey('draft_12'), isFalse);
    expect(prefs.getBool('non_sensitive_setting'), isTrue);
  });
}
