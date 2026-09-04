import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:participant_app/main.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _StatusClient extends http.BaseClient {
  _StatusClient(this.statusCode);
  final int statusCode;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async =>
      http.StreamedResponse(
        Stream.value(utf8.encode('{}')),
        statusCode,
        request: request,
      );
}

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

  test('the release build defaults to the approved PCIP HTTPS base', () {
    expect(configuredApiBase(), Uri.parse('https://citizencentric.co.uk'));
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

  test('a one-time app code is required before a session exchange', () {
    expect(
      invitationCodeError(''),
      'Enter your one-time app code to continue.',
    );
    expect(
      invitationCodeError('  '),
      'Enter your one-time app code to continue.',
    );
    expect(invitationCodeError('CC-1234-5678-90AB-CDEF'), isNull);
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

  test(
    'API error classification queues only transient server responses',
    () async {
      for (final status in [429, 500]) {
        final api = Api(
          Uri.parse('https://citizencentric.co.uk'),
          'synthetic',
          client: _StatusClient(status),
        );
        await expectLater(
          api.request('POST', '/api/v1/participant/activities/1/submit'),
          throwsA(
            isA<ApiError>()
                .having((error) => error.retryable, 'retryable', isTrue)
                .having((error) => error.statusCode, 'status', status),
          ),
        );
      }
    },
  );

  test('API error classification does not queue rejected requests', () async {
    for (final status in [400, 403, 404, 409, 422]) {
      final api = Api(
        Uri.parse('https://citizencentric.co.uk'),
        'synthetic',
        client: _StatusClient(status),
      );
      await expectLater(
        api.request('POST', '/api/v1/participant/activities/1/submit'),
        throwsA(
          isA<ApiError>()
              .having((error) => error.retryable, 'retryable', isFalse)
              .having((error) => error.statusCode, 'status', status),
        ),
      );
    }
  });

  test('oversized evidence is a permanent actionable rejection', () async {
    final directory = await Directory.systemTemp.createTemp('pcip-upload-413-');
    addTearDown(() => directory.delete(recursive: true));
    final file = File('${directory.path}/oversized.mp4');
    await file.writeAsBytes([1, 2, 3], flush: true);
    final api = Api(
      Uri.parse('https://citizencentric.co.uk'),
      'synthetic',
      client: _StatusClient(413),
    );

    await expectLater(
      api.uploadEvidence(
        1,
        file.path,
        'oversized.mp4',
        'video/mp4',
        'synthetic-key',
      ),
      throwsA(
        isA<ApiError>()
            .having((error) => error.retryable, 'retryable', isFalse)
            .having((error) => error.category, 'category', 'file_too_large')
            .having((error) => error.statusCode, 'status', 413),
      ),
    );
  });

  test('expired sessions remain non-retryable and require sign-in', () async {
    final api = Api(
      Uri.parse('https://citizencentric.co.uk'),
      'synthetic',
      client: _StatusClient(401),
    );
    await expectLater(
      api.request('POST', '/api/v1/participant/activities/1/submit'),
      throwsA(
        isA<ApiError>()
            .having((error) => error.category, 'category', 'session_ended')
            .having((error) => error.retryable, 'retryable', isFalse),
      ),
    );
  });

  test(
    'available-studies conflict has a safe, actionable participant message',
    () {
      expect(
        availableStudiesLoadError(
          const ApiError(
            'Internal detail must not reach participants.',
            retryable: false,
            statusCode: 409,
          ),
        ),
        'Your study access needs review. You can continue using your current study, but switching studies is temporarily unavailable. Please contact the research team.',
      );
      expect(
        availableStudiesLoadError(
          const ApiError('Temporary failure.', statusCode: 500),
        ),
        'Your available studies could not be loaded. You can keep using this study.',
      );
    },
  );

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
