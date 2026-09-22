import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:participant_app/main.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _MemorySessionStore extends SessionStore {
  _MemorySessionStore() : super(const FlutterSecureStorage());

  (String, String)? saved;

  @override
  Future<(String, String)?> read() async => saved;

  @override
  Future<void> save(String url, String token) async => saved = (url, token);

  @override
  Future<void> clear() async => saved = null;
}

class _ReviewerBackend {
  bool consented = false;
  int passwordLogins = 0;
  int portalLoads = 0;
}

class _ReviewerApi extends Api {
  _ReviewerApi(this.backend, String token)
    : super(Uri.parse('https://citizencentric.co.uk'), token);

  final _ReviewerBackend backend;

  Map<String, dynamic> get _session => {
    'participant': {
      'participant_id': 41,
      'display_name': 'Store Reviewer',
      'consent_status': backend.consented ? 'granted' : 'pending',
    },
    'invitation': {
      'invitation_id': 71,
      'study_id': 21,
      'accepted_at': backend.consented ? '2026-09-22T10:00:00Z' : null,
      'requires_study_documents': true,
    },
    'next_action': backend.consented ? 'portal' : 'consent_required',
  };

  @override
  Future<Map<String, dynamic>> passwordLogin(
    String username,
    String password,
  ) async {
    expect(username, 'store-reviewer');
    expect(password, 'review-password');
    backend.passwordLogins += 1;
    return {
      'session': {'access_token': 'reviewer-token-${backend.passwordLogins}'},
      ..._session,
    };
  }

  @override
  Future<Map<String, dynamic>> session() async => _session;

  @override
  Future<Map<String, dynamic>> legalDocuments() async => {
    'documents': [
      _document('participant_information', 'Participant information'),
      _document('privacy_notice', 'Privacy notice'),
      _document('consent_text', 'Consent text'),
    ],
  };

  Map<String, dynamic> _document(String type, String title) => {
    'document_type': type,
    'title': title,
    'version': 'review-1',
    'reference': 'STORE-$type',
    'effective_date': '22 September 2026',
    'content_sha256': 'hash-$type',
    'body': 'Synthetic $title for app-store review.',
  };

  @override
  Future<void> consent(Map<String, String> documentHashes) async {
    expect(documentHashes.keys, unorderedEquals({
      'participant_information',
      'privacy_notice',
      'consent_text',
    }));
    backend.consented = true;
  }

  @override
  Future<List<Map<String, dynamic>>> availableStudies() async => [
    {'study_id': 21, 'title': 'Fictional reviewer study'},
  ];

  @override
  Future<void> logout() async {}

  @override
  Future<Map<String, dynamic>> request(
    String method,
    String path, {
    Object? body,
    String? idempotencyKey,
  }) async {
    if (path == '/api/v1/participant/portal') {
      backend.portalLoads += 1;
      return {
        'study': {
          'title': 'Fictional reviewer study',
          'description': 'Safe store-review content',
        },
        'activities': <Map<String, dynamic>>[],
        'messages': <Map<String, dynamic>>[],
      };
    }
    throw StateError('Unexpected request: $method $path');
  }
}

void main() {
  testWidgets(
    'reusable reviewer login is consent-first and remains reusable after consent',
    (tester) async {
      tester.view.physicalSize = const Size(800, 1200);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      SharedPreferences.setMockInitialValues({
        'participant_text_size': 'extraLarge',
      });
      final backend = _ReviewerBackend();
      final store = _MemorySessionStore();
      ParticipantApi factory(String _, String? token) =>
          _ReviewerApi(backend, token ?? 'anonymous');

      await tester.pumpWidget(
        ParticipantApp(store: store, factory: factory),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Username & password'));
      await tester.pump();
      await tester.enterText(
        find.widgetWithText(TextField, 'Username or email'),
        'store-reviewer',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Password'),
        'review-password',
      );
      final firstSignIn = find.widgetWithText(FilledButton, 'Sign in');
      await tester.ensureVisible(firstSignIn);
      await tester.tap(firstSignIn);
      await tester.pumpAndSettle();

      expect(find.text('Before you begin'), findsOneWidget);
      expect(find.textContaining('Welcome, Store Reviewer'), findsNothing);
      expect(backend.portalLoads, 0);

      for (final title in [
        'Participant information',
        'Privacy notice',
        'Consent text',
      ]) {
        final link = find.text('Read $title (version review-1)');
        await tester.ensureVisible(link);
        await tester.tap(link);
        await tester.pumpAndSettle();
        expect(find.text('Synthetic $title for app-store review.'), findsOneWidget);
        await tester.pageBack();
        await tester.pumpAndSettle();
      }
      final consentCheckbox = find.text('I understand and agree to take part.');
      await tester.ensureVisible(consentCheckbox);
      await tester.tap(consentCheckbox);
      await tester.pump();
      final accept = find.widgetWithText(FilledButton, 'Accept and continue');
      await tester.ensureVisible(accept);
      await tester.tap(accept);
      await tester.pumpAndSettle();

      expect(backend.consented, isTrue);
      expect(find.text('Welcome, Store Reviewer'), findsOneWidget);
      expect(backend.portalLoads, 1);

      await tester.tap(find.byTooltip('Sign out'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Username & password'));
      await tester.pump();
      await tester.enterText(
        find.widgetWithText(TextField, 'Username or email'),
        'store-reviewer',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Password'),
        'review-password',
      );
      final secondSignIn = find.widgetWithText(FilledButton, 'Sign in');
      await tester.ensureVisible(secondSignIn);
      await tester.tap(secondSignIn);
      await tester.pumpAndSettle();

      expect(find.text('Welcome, Store Reviewer'), findsOneWidget);
      expect(find.text('Before you begin'), findsNothing);
      expect(backend.passwordLogins, 2);
      expect(backend.portalLoads, 2);
    },
  );
}
