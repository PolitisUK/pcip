import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:participant_app/main.dart';

void main() {
  testWidgets(
    'onboarding uses the post-consent one-time app code and transparent branding',
    (tester) async {
      String? submitted;

      await tester.pumpWidget(
        MaterialApp(
          home: Invite(
            error: null,
            onJoin: (code) async => submitted = code,
            onPasswordLogin: _ignorePassword,
          ),
        ),
      );

      expect(find.text('Join your study'), findsOneWidget);
      expect(find.text('One-time app code'), findsOneWidget);
      expect(
        find.textContaining('After reviewing and consenting'),
        findsOneWidget,
      );
      expect(find.text('Secure service address'), findsNothing);
      expect(find.textContaining('service address'), findsNothing);
      expect(find.byType(TextField), findsOneWidget);
      expect(
        find.bySemanticsLabel('Citizen Centric by Politis'),
        findsOneWidget,
      );

      await tester.enterText(find.byType(TextField), 'CC-1234-5678-90AB-CDEF');
      await tester.tap(find.text('Continue securely'));
      await tester.pump();

      expect(submitted, 'CC-1234-5678-90AB-CDEF');
    },
  );

  testWidgets(
    'app-code failures use an accessible participant-facing message',
    (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Invite(
            error: 'This app code is invalid, expired or already used.',
            onJoin: _ignore,
            onPasswordLogin: _ignorePassword,
          ),
        ),
      );

      expect(
        find.text('This app code is invalid, expired or already used.'),
        findsOneWidget,
      );
      expect(
        tester.getSemantics(
          find.text('This app code is invalid, expired or already used.'),
        ),
        matchesSemantics(isLiveRegion: true),
      );
    },
  );

  testWidgets(
    'password mode exposes obscured credentials and never changes the default',
    (tester) async {
      String? username;
      String? password;
      await tester.pumpWidget(
        MaterialApp(
          home: Invite(
            error: null,
            onJoin: _ignore,
            onPasswordLogin: (value, secret) async {
              username = value;
              password = secret;
            },
          ),
        ),
      );

      expect(find.text('One-time app code'), findsOneWidget);
      expect(find.text('Username or email'), findsNothing);
      await tester.tap(find.text('Username & password'));
      await tester.pumpAndSettle();
      expect(find.text('Username or email'), findsOneWidget);
      final fields = tester
          .widgetList<TextField>(find.byType(TextField))
          .toList();
      expect(fields, hasLength(2));
      expect(fields.last.obscureText, isTrue);
      await tester.enterText(
        find.byType(TextField).at(0),
        'reviewer@example.org',
      );
      await tester.enterText(find.byType(TextField).at(1), 'Password123!');
      await tester.tap(find.text('Sign in'));
      await tester.pump();
      expect(username, 'reviewer@example.org');
      expect(password, 'Password123!');
    },
  );
}

Future<void> _ignore(String _) async {}
Future<void> _ignorePassword(String _, String password) async {}
