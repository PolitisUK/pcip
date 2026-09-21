import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:participant_app/app_accessibility.dart';
import 'package:participant_app/app_design.dart';
import 'package:participant_app/main.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _ActivitiesApi extends Api {
  _ActivitiesApi()
    : super(Uri.parse('https://citizencentric.co.uk'), 'synthetic-token');

  @override
  Future<List<dynamic>> activities() async => [
    {
      'activity_id': 41,
      'title': 'Weekly reflection',
      'prompt': 'Tell us about this week.',
      'activity_type': 'long_text',
      'availability': {'status': 'Available'},
      'allow_multiple_entries': false,
    },
  ];
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('participant text-size choice is persisted and restored', () async {
    final controller = AppTextSizeController();
    await controller.select(AppTextSize.extraLarge);
    expect(controller.value, AppTextSize.extraLarge);

    final restored = AppTextSizeController();
    await restored.load();
    expect(restored.value, AppTextSize.extraLarge);
  });

  test('supplemental scaling retains and adds to device text scaling', () {
    const scaler = SupplementalTextScaler(TextScaler.linear(1.5), 1.3);
    expect(scaler.scale(20), 39);
    expect(scaler.clamp(maxScaleFactor: 1.75).scale(20), 35);
  });

  test('every supported activity has an icon and readable type label', () {
    const expected = {
      'short_text': 'Text response',
      'long_text': 'Text response',
      'single_choice': 'Choice',
      'multiple_choice': 'Choice',
      'rating': 'Rating',
      'slider': 'Scale',
      'photo': 'Photo',
      'audio': 'Voice',
      'video': 'Video',
      'gps': 'Location',
      'ranking': 'Ranking',
      'file': 'Document',
    };
    for (final entry in expected.entries) {
      final presentation = activityPresentation(entry.key);
      expect(presentation.label, entry.value);
      expect(presentation.icon, isNotNull);
    }
  });

  testWidgets('device and app scaling compose in the application builder', (
    tester,
  ) async {
    final controller = AppTextSizeController(initial: AppTextSize.large);
    late double renderedScale;
    await tester.pumpWidget(
      MaterialApp(
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context)
              .copyWith(textScaler: const TextScaler.linear(1.5)),
          child: Builder(
            builder: (context) => participantAccessibilityBuilder(
              context,
              Builder(
                builder: (context) {
                  renderedScale = MediaQuery.textScalerOf(context).scale(20);
                  return const Text('Readable content');
                },
              ),
              controller,
            ),
          ),
        ),
      ),
    );
    expect(renderedScale, closeTo(34.5, 0.001));
  });

  testWidgets('activity card exposes type and status without colour alone', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: buildParticipantTheme(),
        home: Activities(api: _ActivitiesApi(), studyId: 7),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Text response · Available'), findsOneWidget);
    expect(
      find.bySemanticsLabel(
        'Weekly reflection. Text response. Status: Available',
      ),
      findsOneWidget,
    );
    expect(find.byType(ActivityIcon), findsOneWidget);
  });

  testWidgets('activity list remains usable on a narrow large-text screen', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      MediaQuery(
        data: const MediaQueryData(textScaler: TextScaler.linear(2)),
        child: MaterialApp(
          theme: buildParticipantTheme(),
          home: Activities(api: _ActivitiesApi(), studyId: 7),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Weekly reflection'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('text response controls reflow on a narrow large-text screen', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      MediaQuery(
        data: const MediaQueryData(textScaler: TextScaler.linear(2)),
        child: MaterialApp(
          theme: buildParticipantTheme(),
          home: TextActivity(
            api: _ActivitiesApi(),
            studyId: 7,
            item: const {
              'activity_id': 41,
              'title': 'Weekly reflection',
              'prompt': 'Tell us about this week and anything that changed.',
              'activity_type': 'long_text',
              'allow_multiple_entries': false,
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    await tester.scrollUntilVisible(
      find.text('Submit response'),
      300,
      scrollable: find.byType(Scrollable).last,
    );
    expect(find.text('Submit response'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('theme provides at least 48 logical-pixel touch targets', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: buildParticipantTheme(),
        home: Scaffold(
          body: Center(
            child: FilledButton(
              onPressed: () {},
              child: const Text('Continue'),
            ),
          ),
        ),
      ),
    );
    expect(
      tester.getSize(find.byType(FilledButton)).height,
      greaterThanOrEqualTo(48),
    );
  });
}
