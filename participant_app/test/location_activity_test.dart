import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:participant_app/main.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _locationChannel = MethodChannel('flutter.baseflow.com/geolocator');

Api get _api =>
    Api(Uri.parse('https://citizencentric.co.uk'), 'synthetic-token');

Widget _activity() => MaterialApp(
  home: TextActivity(
    api: _api,
    item: const {
      'activity_id': 71,
      'title': 'Optional location diary',
      'prompt': 'Share an observation.',
      'allow_participant_location': true,
    },
  ),
);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(_locationChannel, null);
  });

  testWidgets('permission denial is non-blocking and attaches no location', (
    tester,
  ) async {
    var requests = 0;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(_locationChannel, (call) async {
          if (call.method == 'isLocationServiceEnabled') return true;
          if (call.method == 'checkPermission') return 0; // denied
          if (call.method == 'requestPermission') {
            requests += 1;
            return 0;
          }
          throw MissingPluginException();
        });
    await tester.pumpWidget(_activity());
    await tester.tap(find.text('Use my current location'));
    await tester.pumpAndSettle();

    expect(requests, 1);
    expect(
      find.text('Location was not added. You can still submit this entry.'),
      findsOneWidget,
    );
    expect(find.text('Location added'), findsNothing);
    expect(find.text('Submit response'), findsOneWidget);
  });

  testWidgets('permanently denied permission does not request again', (
    tester,
  ) async {
    var requests = 0;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(_locationChannel, (call) async {
          if (call.method == 'isLocationServiceEnabled') return true;
          if (call.method == 'checkPermission') return 1; // deniedForever
          if (call.method == 'requestPermission') requests += 1;
          throw MissingPluginException();
        });
    await tester.pumpWidget(_activity());
    await tester.tap(find.text('Use my current location'));
    await tester.pumpAndSettle();

    expect(requests, 0);
    expect(
      find.text('Location was not added. You can still submit this entry.'),
      findsOneWidget,
    );
    expect(find.text('Submit response'), findsOneWidget);
  });

  testWidgets('location acquisition failure is non-blocking', (tester) async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(_locationChannel, (call) async {
          if (call.method == 'isLocationServiceEnabled') return true;
          if (call.method == 'checkPermission') return 2; // whileInUse
          if (call.method == 'getCurrentPosition') {
            throw PlatformException(code: 'unavailable');
          }
          throw MissingPluginException();
        });
    await tester.pumpWidget(_activity());
    await tester.tap(find.text('Use my current location'));
    await tester.pumpAndSettle();

    expect(
      find.text(
        'Location could not be added. You can still submit this entry.',
      ),
      findsOneWidget,
    );
    expect(find.text('Location added'), findsNothing);
    expect(find.text('Save draft'), findsOneWidget);
  });

  testWidgets(
    'successful capture persists location and removal clears the draft',
    (tester) async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(_locationChannel, (call) async {
            if (call.method == 'isLocationServiceEnabled') return true;
            if (call.method == 'checkPermission') return 2; // whileInUse
            if (call.method == 'getCurrentPosition') {
              return {
                'latitude': 51.5074,
                'longitude': -0.1278,
                'timestamp': 0,
                'accuracy': 12.5,
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
      await tester.pumpWidget(_activity());
      await tester.tap(find.text('Use my current location'));
      await tester.pumpAndSettle();

      expect(find.text('Location added'), findsOneWidget);
      expect(find.text('Approximate accuracy: 13 m'), findsOneWidget);
      final prefs = await SharedPreferences.getInstance();
      final stored =
          jsonDecode(prefs.getString('draft_71')!) as Map<String, dynamic>;
      expect((stored['location'] as Map)['latitude'], 51.5074);
      expect((stored['location'] as Map)['accuracy_metres'], 12.5);
      expect(stored['idempotency_key'], isNotEmpty);

      await tester.tap(find.text('Remove'));
      await tester.pumpAndSettle();
      final removed =
          jsonDecode(prefs.getString('draft_71')!) as Map<String, dynamic>;
      expect(removed.containsKey('location'), isFalse);
      expect(find.text('Location removed from this entry.'), findsOneWidget);
      expect(find.text('Submit response'), findsOneWidget);
    },
  );
}
