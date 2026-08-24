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
          home: Invite(error: null, onJoin: (code) async => submitted = code),
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
}

Future<void> _ignore(String _) async {}
