import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:participant_app/main.dart';
import 'package:shared_preferences/shared_preferences.dart';

Api get _api =>
    Api(Uri.parse('https://citizencentric.co.uk'), 'synthetic-token');

class _FailingSessionStore extends SessionStore {
  _FailingSessionStore() : super(const FlutterSecureStorage());

  @override
  Future<(String, String)?> read() async =>
      throw StateError('Keychain unavailable');

  @override
  Future<void> clear() async {}
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('photo is durable before upload and server acknowledgement clears only the queued copy', () async {
    final root = await Directory.systemTemp.createTemp('pcip-media-test-');
    addTearDown(() => root.delete(recursive: true));
    final source = File('${root.path}/camera-temporary.jpg');
    await source.writeAsBytes([1, 2, 3, 4], flush: true);

    final pending = await MediaQueue.enqueue(
      activityId: 41,
      sourcePath: source.path,
      filename: 'field-photo.jpg',
      kind: 'photo',
      supportDirectory: root,
    );
    await source.delete();

    expect(await File(pending.localPath).exists(), isTrue);
    expect(await MediaQueue.count(), 1);
    String? uploadedKey;
    final state = await MediaQueue.replay(
      _api,
      uploader: (item) async {
        uploadedKey = item.idempotencyKey;
        expect(item.activityId, 41);
        expect(item.contentType, 'image/jpeg');
        expect(await File(item.localPath).readAsBytes(), [1, 2, 3, 4]);
        return {
          'evidence': {
            'evidence_id': 81,
            'activity_id': 41,
            'original_name': item.filename,
            'content_type': item.contentType,
            'scan_status': 'pending',
          },
        };
      },
    );

    expect(state, SyncState.sent);
    expect(uploadedKey, pending.idempotencyKey);
    expect(await MediaQueue.count(), 0);
    expect(await File(pending.localPath).exists(), isFalse);
    expect(
      (await EvidenceReceiptStore.read()).single['scan_status'],
      'pending',
    );
  });

  test(
    'failed media retry keeps the durable file and reuses one idempotency key',
    () async {
      final root = await Directory.systemTemp.createTemp('pcip-media-retry-');
      addTearDown(() => root.delete(recursive: true));
      final source = File('${root.path}/voice.m4a');
      await source.writeAsBytes([5, 6, 7], flush: true);
      final pending = await MediaQueue.enqueue(
        activityId: 12,
        sourcePath: source.path,
        filename: 'voice-diary.m4a',
        kind: 'voice',
        supportDirectory: root,
      );
      final keys = <String>[];
      var fail = true;
      Future<Map<String, dynamic>> uploader(PendingMediaUpload item) async {
        keys.add(item.idempotencyKey);
        if (fail) throw const ApiError('Temporary upload failure.');
        return {
          'evidence': {
            'evidence_id': 9,
            'activity_id': 12,
            'original_name': item.filename,
            'content_type': item.contentType,
            'scan_status': 'clean',
          },
        };
      }

      expect(
        await MediaQueue.replay(_api, uploader: uploader),
        SyncState.waiting,
      );
      expect(await File(pending.localPath).exists(), isTrue);
      fail = false;
      expect(
        await MediaQueue.replay(
          _api,
          now: DateTime.now().add(const Duration(minutes: 5)),
          uploader: uploader,
        ),
        SyncState.sent,
      );
      expect(keys, [pending.idempotencyKey, pending.idempotencyKey]);
      expect(await MediaQueue.count(), 0);
    },
  );

  test(
    'security-rejected media fails closed without an automatic retry loop',
    () async {
      final root = await Directory.systemTemp.createTemp(
        'pcip-media-rejected-',
      );
      addTearDown(() => root.delete(recursive: true));
      final source = File('${root.path}/rejected.jpg');
      await source.writeAsBytes([8, 9], flush: true);
      await MediaQueue.enqueue(
        activityId: 18,
        sourcePath: source.path,
        filename: 'rejected.jpg',
        kind: 'photo',
        supportDirectory: root,
      );
      var calls = 0;
      Future<Map<String, dynamic>> rejected(PendingMediaUpload item) async {
        calls += 1;
        throw const ApiError('Security rejected.', retryable: false);
      }

      expect(
        await MediaQueue.replay(_api, uploader: rejected),
        SyncState.needsAttention,
      );
      expect(
        (await MediaQueue.read()).single.failureCategory,
        'security_rejected',
      );
      expect(
        await MediaQueue.replay(_api, uploader: rejected),
        SyncState.needsAttention,
      );
      expect(calls, 1);
    },
  );

  test('an already-submitted response remains protected without discarding pending media', () async {
    final root = await Directory.systemTemp.createTemp('pcip-media-final-');
    addTearDown(() => root.delete(recursive: true));
    final source = File('${root.path}/photo.jpg');
    await source.writeAsBytes([1, 2, 3], flush: true);
    final pending = await MediaQueue.enqueue(
      activityId: 27,
      sourcePath: source.path,
      filename: 'photo.jpg',
      kind: 'photo',
      supportDirectory: root,
    );

    final state = await MediaQueue.replay(
      _api,
      uploader: (_) async => throw const ApiError(
        'This activity has already been submitted.',
        retryable: false,
        category: 'already_submitted',
      ),
    );

    expect(state, SyncState.needsAttention);
    expect(
      (await MediaQueue.read()).single.idempotencyKey,
      pending.idempotencyKey,
    );
    expect(
      (await MediaQueue.read()).single.failureCategory,
      'already_submitted',
    );
    expect(await File(pending.localPath).exists(), isTrue);
  });

  testWidgets(
    'media-native activities do not use the generic submit-response screen',
    (tester) async {
      final photo = participantActivityPage(_api, {
        'activity_id': 10,
        'title': 'Street scene',
        'activity_type': 'photo',
      });
      final voice = participantActivityPage(_api, {
        'activity_id': 11,
        'title': 'Voice diary',
        'activity_type': 'audio',
      });

      expect(photo, isA<PhotoEvidence>());
      expect(voice, isA<VoiceDiary>());

      await tester.pumpWidget(MaterialApp(home: photo));
      await tester.pumpAndSettle();
      expect(find.text('Submit response'), findsNothing);
      expect(find.text('Take a photo'), findsOneWidget);
    },
  );

  testWidgets('submitted media activity does not offer another upload', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: participantActivityPage(_api, {
          'activity_id': 12,
          'title': 'Submitted photo',
          'activity_type': 'photo',
          'response': {'status': 'submitted'},
        }),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      find.text('Submitted activities cannot be changed.'),
      findsOneWidget,
    );
    expect(find.text('Take a photo'), findsNothing);
  });

  testWidgets('secure-storage recovery returns to the join screen', (
    tester,
  ) async {
    await tester.pumpWidget(ParticipantApp(store: _FailingSessionStore()));
    await tester.pumpAndSettle();
    expect(find.text('Join your study'), findsOneWidget);
    expect(find.bySemanticsLabel('Loading your secure session'), findsNothing);
  });

  testWidgets(
    'confirmed participant message appears immediately and retry does not change its key',
    (tester) async {
      final keys = <String>[];
      var first = true;
      await tester.pumpWidget(
        MaterialApp(
          home: Messages(
            api: _api,
            reader: () async => [],
            sender: (body, key) async {
              keys.add(key);
              if (first) {
                first = false;
                throw const ApiError('Temporary failure.');
              }
              return {
                'message': {
                  'message_id': 73,
                  'sender_type': 'participant',
                  'body': body,
                  'created_at': '2026-08-23T12:00:00Z',
                },
              };
            },
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Write message'));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byType(TextField),
        'A confirmed participant message',
      );
      await tester.tap(find.text('Send message'));
      await tester.pumpAndSettle();
      expect(
        find.text('We could not send your message. Please try again.'),
        findsOneWidget,
      );
      await tester.tap(find.text('Send message'));
      await tester.pumpAndSettle();

      expect(keys, hasLength(2));
      expect(keys.first, keys.last);
      expect(find.text('A confirmed participant message'), findsOneWidget);
      expect(find.text('You'), findsOneWidget);
    },
  );

  testWidgets(
    'history renders study context, answer, date and evidence security state',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: History(
            api: _api,
            reader: () async => [
              {
                'response_id': 1,
                'activity_id': 2,
                'activity_title': 'Evening reflection',
                'activity_prompt': 'What changed today?',
                'study_title': 'Rivermere diary',
                'project_title': 'Rivermere 2035',
                'answer':
                    'The bus stop felt safer after lighting was repaired.',
                'choices': <String>[],
                'evidence': [
                  {
                    'evidence_id': 3,
                    'original_name': 'voice-diary.m4a',
                    'content_type': 'audio/mp4',
                    'scan_status': 'pending',
                    'downloadable': false,
                    'created_at': '2026-08-23T12:00:00Z',
                  },
                ],
                'status': 'submitted',
                'submitted_at': '2026-08-23T12:00:00Z',
                'updated_at': '2026-08-23T12:00:00Z',
              },
            ],
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Rivermere 2035 • Rivermere diary'), findsOneWidget);
      expect(find.text('What changed today?'), findsOneWidget);
      expect(
        find.text('The bus stop felt safer after lighting was repaired.'),
        findsOneWidget,
      );
      expect(find.text('voice-diary.m4a'), findsOneWidget);
      expect(find.text('Security check'), findsOneWidget);
      expect(find.textContaining('Submitted • '), findsOneWidget);
    },
  );

  testWidgets('dashboard remains usable at compact iPhone width', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 780);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      MaterialApp(
        theme: participantTheme,
        home: Home(
          api: _api,
          name: 'Alex',
          onLogout: () async {},
          dashboardLoader: () async => {
            'study': {
              'title': 'Rivermere diary',
              'description': 'Everyday life in our town',
            },
            'activities': <Map<String, dynamic>>[],
            'messages': <Map<String, dynamic>>[],
            'pending_uploads': 0,
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.text('Welcome, Alex'), findsOneWidget);
    expect(find.text('Rivermere diary'), findsOneWidget);
    expect(find.text('Activities'), findsOneWidget);
  });
}
