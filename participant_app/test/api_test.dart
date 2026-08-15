import 'package:flutter_test/flutter_test.dart';
import 'package:participant_app/main.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  test('non HTTPS endpoints fail closed before a request is sent', () async {
    await expectLater(
      Api(
        Uri.parse('http://example.invalid'),
        'not-a-real-token',
      ).request('GET', '/session'),
      throwsA(isA<ApiError>()),
    );
  });

  test('unconfigured or arbitrary endpoints fail closed', () {
    expect(allowsApiBase(Uri.parse('http://localhost:8001')), isFalse);
    expect(allowsApiBase(Uri.parse('http://10.0.2.2:8001')), isFalse);
    expect(allowsApiBase(Uri.parse('http://example.invalid')), isFalse);
    expect(allowsApiBase(Uri.parse('https://example.invalid')), isFalse);
  });

  test('a debug override is never selected in a release build', () {
    expect(
      selectedApiBaseValue(
        debugMode: false,
        releaseValue: 'https://participant.example.test',
        debugValue: 'http://10.0.2.2:8000',
      ),
      'https://participant.example.test',
    );
    expect(
      selectedApiBaseValue(
        debugMode: true,
        releaseValue: 'https://participant.example.test',
        debugValue: 'http://10.0.2.2:8000',
      ),
      'http://10.0.2.2:8000',
    );
  });

  test('an invitation code is required before a session exchange', () {
    expect(invitationCodeError(''), 'Enter your invitation code to continue.');
    expect(
      invitationCodeError('  '),
      'Enter your invitation code to continue.',
    );
    expect(invitationCodeError('synthetic-invitation-token'), isNull);
  });

  test('participant timestamps are readable and fail safely', () {
    expect(
      participantDateTime('2026-08-15T09:36:08.177087Z'),
      matches(RegExp(r'^15/08/2026 at \d{2}:\d{2}$')),
    );
    expect(participantDateTime('not-a-date'), 'Date unavailable');
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

  test(
    'malformed read caches are removed instead of blocking recovery',
    () async {
      SharedPreferences.setMockInitialValues({
        'cached_profile': 'not-json',
        'cached_history': '{"not":"a list"}',
      });

      expect(await cachedObject('cached_profile'), isNull);
      expect(await cachedList('cached_history'), isNull);
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.containsKey('cached_profile'), isFalse);
      expect(prefs.containsKey('cached_history'), isFalse);
    },
  );

  test('corrupt queued material is retained and needs attention', () async {
    SharedPreferences.setMockInitialValues({
      'submission_queue': <String>['not-json'],
    });

    final state = await Queue.replay(
      Api(Uri.parse('https://example.invalid'), 'synthetic'),
    );

    expect(state, SyncState.needsAttention);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getStringList('submission_queue'), <String>['not-json']);
  });
}
