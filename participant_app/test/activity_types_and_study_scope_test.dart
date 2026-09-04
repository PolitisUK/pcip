import 'dart:convert';

// The nullable test fixture field is clearer as a conditional map entry.
// ignore_for_file: use_null_aware_elements

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:participant_app/main.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _locationChannel = MethodChannel('flutter.baseflow.com/geolocator');

class _RecordingApi extends Api {
  _RecordingApi({this.failRetryably = false})
    : super(Uri.parse('https://citizencentric.co.uk'), 'synthetic-token');

  final bool failRetryably;
  final List<Map<String, dynamic>> calls = [];

  @override
  Future<void> draftResponse(
    int id,
    String key, {
    String? answer,
    List<String> choices = const [],
    Map<String, dynamic>? location,
  }) async {
    calls.add({
      'action': 'draft',
      'activity_id': id,
      'key': key,
      'answer': answer,
      'choices': choices,
      'location': location,
    });
  }

  @override
  Future<void> submitResponse(
    int id,
    String key, {
    String? answer,
    List<String> choices = const [],
    Map<String, dynamic>? location,
  }) async {
    if (failRetryably) throw const ApiError('Temporary.', retryable: true);
    calls.add({
      'action': 'submit',
      'activity_id': id,
      'key': key,
      'answer': answer,
      'choices': choices,
      'location': location,
    });
  }
}

class _EvidenceApi extends _RecordingApi {
  @override
  Future<Map<String, dynamic>> evidenceStatus(int id) async => {
    'evidence': {'evidence_id': id, 'activity_id': 4, 'scan_status': 'clean'},
  };
}

Map<String, dynamic> _activity(
  String type, {
  int id = 41,
  List<String>? options,
  bool required = true,
}) => {
  'activity_id': id,
  'title': '$type activity',
  'prompt': 'Complete this activity.',
  'activity_type': type,
  'required': required,
  'allow_multiple_entries': false,
  if (options != null) 'options': options,
};

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => SharedPreferences.setMockInitialValues({}));
  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(_locationChannel, null);
  });

  test('every backend activity type maps to a dedicated safe renderer', () {
    final api = _RecordingApi();
    final expected = <String, Type>{
      'short_text': TextActivity,
      'long_text': TextActivity,
      'single_choice': ChoiceActivity,
      'multiple_choice': ChoiceActivity,
      'rating': RatingActivity,
      'slider': SliderActivity,
      'photo': PhotoEvidence,
      'audio': VoiceDiary,
      'video': VideoEvidence,
      'gps': LocationActivity,
      'ranking': RankingActivity,
      'file': DocumentEvidence,
    };

    for (final entry in expected.entries) {
      expect(
        participantActivityPage(
          api,
          _activity(entry.key, options: const ['1', '2', '3']),
          studyId: 7,
        ).runtimeType,
        entry.value,
        reason: entry.key,
      );
    }
    expect(
      participantActivityPage(api, _activity('future_type')),
      isA<UnsupportedActivity>(),
    );
  });

  testWidgets('unknown activity fails closed without an editable response', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: participantActivityPage(
          _RecordingApi(),
          _activity('future_type'),
        ),
      ),
    );
    expect(
      find.text(
        "This activity type isn't supported by this version of the app.",
      ),
      findsOneWidget,
    );
    expect(find.byType(TextField), findsNothing);
    expect(find.text('Submit response'), findsNothing);
  });

  testWidgets(
    'rating uses configured values and submits one structured answer',
    (tester) async {
      final api = _RecordingApi();
      await tester.pumpWidget(
        MaterialApp(
          home: participantActivityPage(
            api,
            _activity('rating', options: const ['Low', 'Medium', 'High']),
            studyId: 9,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(TextField), findsNothing);
      expect(find.text('Low'), findsOneWidget);
      expect(find.text('High'), findsOneWidget);

      await tester.tap(find.text('High'));
      await tester.tap(find.text('Submit response'));
      await tester.pumpAndSettle();

      expect(api.calls.single['answer'], 'High');
      expect(api.calls.single['choices'], isEmpty);
      expect(find.text('Submitted successfully.'), findsOneWidget);
    },
  );

  testWidgets(
    'rating restores its study-scoped draft and rejects no selection',
    (tester) async {
      SharedPreferences.setMockInitialValues({
        'draft_study_3_activity_41': jsonEncode({
          'answer': '2',
          'choices': <String>[],
          'idempotency_key': 'stable-rating-key',
        }),
      });
      final api = _RecordingApi();
      await tester.pumpWidget(
        MaterialApp(
          home: RatingActivity(
            api: api,
            item: _activity('rating', options: const ['1', '2', '3']),
            studyId: 3,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<ChoiceChip>(find.widgetWithText(ChoiceChip, '2'))
            .selected,
        isTrue,
      );

      await tester.tap(find.text('Submit response'));
      await tester.pumpAndSettle();
      expect(api.calls.single['key'], 'stable-rating-key');

      SharedPreferences.setMockInitialValues({});
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpWidget(
        MaterialApp(
          home: RatingActivity(
            api: _RecordingApi(),
            item: _activity('rating', options: const ['1', '2']),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Submit response'));
      await tester.pump();
      expect(find.text('Choose a rating before submitting.'), findsOneWidget);
    },
  );

  testWidgets('ranking supports accessible reordering and ordered submission', (
    tester,
  ) async {
    final api = _RecordingApi();
    await tester.pumpWidget(
      MaterialApp(
        home: RankingActivity(
          api: api,
          item: _activity('ranking', options: const ['Bus', 'Train', 'Walk']),
          studyId: 12,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byTooltip('Move Train up'), findsOneWidget);
    await tester.tap(find.byTooltip('Move Train up'));
    await tester.tap(find.text('Save draft'));
    await tester.pumpAndSettle();
    expect(api.calls.single['choices'], ['Train', 'Bus', 'Walk']);

    await tester.tap(find.text('Submit response'));
    await tester.pumpAndSettle();
    expect(api.calls.last['choices'], ['Train', 'Bus', 'Walk']);
  });

  testWidgets('multiple choice and slider submit their configured shapes', (
    tester,
  ) async {
    final choicesApi = _RecordingApi();
    await tester.pumpWidget(
      MaterialApp(
        home: ChoiceActivity(
          api: choicesApi,
          item: _activity(
            'multiple_choice',
            options: const ['Bus', 'Train', 'Walk'],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Bus'));
    await tester.tap(find.text('Walk'));
    await tester.tap(find.text('Submit response'));
    await tester.pumpAndSettle();
    expect(choicesApi.calls.single['answer'], isNull);
    expect(choicesApi.calls.single['choices'], ['Bus', 'Walk']);

    await tester.pumpWidget(const SizedBox.shrink());
    final sliderApi = _RecordingApi();
    await tester.pumpWidget(
      MaterialApp(
        home: SliderActivity(
          api: sliderApi,
          item: _activity('slider', options: const ['1', '2', '3']),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.drag(find.byType(Slider), const Offset(300, 0));
    await tester.tap(find.text('Submit response'));
    await tester.pumpAndSettle();
    expect(sliderApi.calls.single['answer'], '3');
    expect(sliderApi.calls.single['choices'], isEmpty);
  });

  testWidgets('GPS activity submits structured device location without text', (
    tester,
  ) async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(_locationChannel, (call) async {
          if (call.method == 'isLocationServiceEnabled') return true;
          if (call.method == 'checkPermission') return 2;
          if (call.method == 'getCurrentPosition') {
            return {
              'latitude': 51.5074,
              'longitude': -0.1278,
              'timestamp': 0,
              'accuracy': 8.0,
              'altitude': 0.0,
              'altitude_accuracy': 0.0,
              'heading': 0.0,
              'heading_accuracy': 0.0,
              'speed': 0.0,
              'speed_accuracy': 0.0,
              'is_mocked': false,
            };
          }
          throw MissingPluginException();
        });
    final api = _RecordingApi();
    await tester.pumpWidget(
      MaterialApp(
        home: LocationActivity(api: api, item: _activity('gps'), studyId: 22),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byType(TextField), findsNothing);
    await tester.tap(find.text('Use my current location'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Submit response'));
    await tester.pumpAndSettle();
    final location = api.calls.single['location'] as Map<String, dynamic>;
    expect(api.calls.single['answer'], '');
    expect(location['latitude'], 51.5074);
    expect(location['accuracy_metres'], 8.0);
    expect(location['source'], 'device');
  });

  testWidgets('submitted structured activity is read-only', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: participantActivityPage(_RecordingApi(), {
          ..._activity('ranking', options: const ['A', 'B']),
          'response': {'status': 'submitted'},
        }),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('already been submitted'), findsOneWidget);
    expect(find.text('Submit response'), findsOneWidget);
    expect(
      tester
          .widget<FilledButton>(
            find.widgetWithText(FilledButton, 'Submit response'),
          )
          .onPressed,
      isNull,
    );
  });

  testWidgets('structured transient failure queues the exact scoped payload', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: ChoiceActivity(
          api: _RecordingApi(failRetryably: true),
          item: _activity('single_choice', options: const ['Yes', 'No']),
          studyId: 18,
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Yes'));
    await tester.tap(find.text('Submit response'));
    await tester.pumpAndSettle();

    final raw = (await SharedPreferences.getInstance())
        .getStringList('submission_queue')!
        .single;
    final queued = jsonDecode(raw) as Map<String, dynamic>;
    expect(queued['study_id'], 18);
    expect(queued['activity_id'], 41);
    expect(queued['choices'], ['Yes']);
    expect(queued['answer'], isNull);
  });

  test('draft, cache and retry state are isolated by study', () async {
    expect(activityDraftKey(4, 10), isNot(activityDraftKey(4, 11)));
    expect(studyCacheKey('cached_messages', 10), 'cached_messages_study_10');
    await Queue.add({
      'study_id': 10,
      'activity_id': 4,
      'answer': 'Study A',
      'choices': <String>[],
      'idempotency_key': 'aaaaaaaa',
    });
    await Queue.add({
      'study_id': 11,
      'activity_id': 5,
      'answer': 'Study B',
      'choices': <String>[],
      'idempotency_key': 'bbbbbbbb',
    });
    final api = _RecordingApi();
    expect(await Queue.replay(api, studyId: 10), SyncState.sent);
    expect(api.calls.single['answer'], 'Study A');
    expect(await Queue.count(studyId: 10), 0);
    expect(await Queue.count(studyId: 11), 1);
  });

  test('evidence status refresh preserves its study boundary', () async {
    await EvidenceReceiptStore.record(4, {
      'evidence_id': 81,
      'scan_status': 'pending',
    }, studyId: 10);
    await EvidenceReceiptStore.record(5, {
      'evidence_id': 82,
      'scan_status': 'pending',
    }, studyId: 11);

    final refreshed = await EvidenceReceiptStore.refresh(
      _EvidenceApi(),
      studyId: 10,
    );
    expect(
      refreshed.singleWhere((row) => row['evidence_id'] == 81),
      containsPair('study_id', 10),
    );
    expect(
      refreshed.singleWhere((row) => row['evidence_id'] == 82),
      containsPair('study_id', 11),
    );
    expect((await EvidenceReceiptStore.read(studyId: 10)).length, 1);
    expect((await EvidenceReceiptStore.read(studyId: 11)).length, 1);
  });

  testWidgets(
    'one study stays simple while multiple studies expose My studies',
    (tester) async {
      Future<Map<String, dynamic>> dashboard() async => {
        'study': {'title': 'Study A'},
        'activities': <Object>[],
        'messages': <Object>[],
      };
      await tester.pumpWidget(
        MaterialApp(
          home: Home(
            api: _RecordingApi(),
            name: 'Participant',
            activeStudyId: 1,
            studies: const [
              {'study_id': 1, 'title': 'Study A'},
            ],
            onLogout: () async {},
            onSwitchStudy: (_) async {},
            dashboardLoader: dashboard,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byTooltip('Switch study'), findsNothing);

      await tester.pumpWidget(
        MaterialApp(
          home: Home(
            api: _RecordingApi(),
            name: 'Participant',
            activeStudyId: 1,
            studies: const [
              {'study_id': 1, 'title': 'Study A'},
              {'study_id': 2, 'title': 'Study B'},
            ],
            onLogout: () async {},
            onSwitchStudy: (_) async {},
            dashboardLoader: dashboard,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byTooltip('Switch study'), findsOneWidget);
      expect(find.text('My studies'), findsOneWidget);
    },
  );
}
