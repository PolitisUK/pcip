import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:participant_app/main.dart';

void main() {
  testWidgets(
    'onboarding uses invitation code only and retains approved branding',
    (tester) async {
      String? submitted;

      await tester.pumpWidget(
        MaterialApp(
          home: Invite(error: null, onJoin: (code) async => submitted = code),
        ),
      );

      expect(find.text('Join your study'), findsOneWidget);
      expect(find.text('Invitation code'), findsOneWidget);
      expect(find.text('Secure service address'), findsNothing);
      expect(find.textContaining('service address'), findsNothing);
      expect(find.byType(TextField), findsOneWidget);
      expect(
        find.bySemanticsLabel('Citizen Centric by Politis'),
        findsOneWidget,
      );

      await tester.enterText(
        find.byType(TextField),
        'synthetic-invitation-token',
      );
      await tester.tap(find.text('Continue'));
      await tester.pump();

      expect(submitted, 'synthetic-invitation-token');
    },
  );

  testWidgets(
    'invitation failures use an accessible participant-facing message',
    (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Invite(
            error: 'This invitation is invalid or has expired.',
            onJoin: _ignore,
          ),
        ),
      );

      expect(
        find.text('This invitation is invalid or has expired.'),
        findsOneWidget,
      );
      expect(
        tester.getSemantics(
          find.text('This invitation is invalid or has expired.'),
        ),
        matchesSemantics(isLiveRegion: true),
      );
    },
  );
}

Future<void> _ignore(String _) async {}
