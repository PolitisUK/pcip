import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:participant_app/main.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _locationChannel = MethodChannel('flutter.baseflow.com/geolocator');

Api get _api =>
    Api(Uri.parse('https://citizencentric.co.uk'), 'synthetic-token');

class _StatusClient extends http.BaseClient {
  _StatusClient(this.statusCode);
  final int statusCode;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async =>
      http.StreamedResponse(
        Stream.value(const <int>[123, 125]),
        statusCode,
        request: request,
      );
}

Widget _activity({Api? api}) => MaterialApp(
  home: TextActivity(
    api: api ?? _api,
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

  testWidgets('transient server failure preserves the entry and queues it', (
    tester,
  ) async {
    await tester.pumpWidget(
      _activity(
        api: Api(
          Uri.parse('https://citizencentric.co.uk'),
          'synthetic',
          client: _StatusClient(500),
        ),
      ),
    );
    await tester.enterText(find.byType(TextField), 'A durable entry');
    await tester.tap(find.text('Submit response'));
    await tester.pumpAndSettle();

    expect(
      find.text('Saved on this device. We will retry when you reconnect.'),
      findsOneWidget,
    );
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getStringList('submission_queue'), hasLength(1));
  });

  testWidgets('server rejection leaves the draft but does not queue it', (
    tester,
  ) async {
    await tester.pumpWidget(
      _activity(
        api: Api(
          Uri.parse('https://citizencentric.co.uk'),
          'synthetic',
          client: _StatusClient(422),
        ),
      ),
    );
    await tester.enterText(find.byType(TextField), 'A valid local draft');
    await tester.tap(find.text('Submit response'));
    await tester.pumpAndSettle();

    expect(
      find.text(
        'We could not submit this entry. Please try again or contact your research team.',
      ),
      findsOneWidget,
    );
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getStringList('submission_queue'), isNull);
    expect(prefs.getString('draft_71'), contains('A valid local draft'));
  });

  testWidgets(
    'expired session does not queue and directs the participant to sign in',
    (tester) async {
      await tester.pumpWidget(
        _activity(
          api: Api(
            Uri.parse('https://citizencentric.co.uk'),
            'synthetic',
            client: _StatusClient(401),
          ),
        ),
      );
      await tester.enterText(find.byType(TextField), 'Session-protected entry');
      await tester.tap(find.text('Submit response'));
      await tester.pumpAndSettle();

      expect(
        find.text(
          'Your session has ended. Sign in again before submitting this entry.',
        ),
        findsOneWidget,
      );
      expect(
        (await SharedPreferences.getInstance()).getStringList(
          'submission_queue',
        ),
        isNull,
      );
    },
  );

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
