import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:participant_app/legal_privacy.dart';
import 'package:participant_app/main.dart';

void main() {
  testWidgets(
    'legal information centre exposes the four complete platform policies and choices',
    (tester) async {
      var openedChoices = false;
      await tester.pumpWidget(
        MaterialApp(
          home: LegalPrivacyCentre(
            onOpenPrivacyChoices: () => openedChoices = true,
          ),
        ),
      );

      expect(find.text('Platform Privacy Notice'), findsOneWidget);
      expect(find.text('Data Rights Policy'), findsOneWidget);
      expect(find.text('Accessibility Policy'), findsOneWidget);
      await tester.tap(find.text('Platform Privacy Notice'));
      await tester.pumpAndSettle();
      expect(
        find.text(
          'How Politis Ltd handles personal information when operating Citizen Centric.',
        ),
        findsOneWidget,
      );
      expect(find.byTooltip('Contents'), findsOneWidget);

      await tester.pageBack();
      await tester.pumpAndSettle();
      await tester.dragUntilVisible(
        find.text('Consent Notice'),
        find.byType(Scrollable).first,
        const Offset(0, -300),
      );
      expect(find.text('Consent Notice'), findsOneWidget);
      expect(find.text('Withdrawal and data deletion'), findsOneWidget);
      await tester.tap(find.text('Withdrawal and data deletion'));
      expect(openedChoices, isTrue);
    },
  );

  testWidgets(
    'consent requires review of the exact study-bound documents before acceptance',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(home: Consent(error: null, documents: const [
          {
            'document_type': 'participant_information',
            'title': 'Participant information',
            'version': '7.2',
            'reference': 'PI-7.2',
            'effective_date': '18 August 2026',
            'content_sha256': 'synthetic-hash',
            'body': 'Exact study-specific participant information.',
          },
        ], onAccept: (_) async {})),
      );

      expect(find.text('Read Participant information (version 7.2)'), findsOneWidget);
      await tester.tap(find.text('Read Participant information (version 7.2)'));
      await tester.pumpAndSettle();
      expect(find.text('Exact study-specific participant information.'), findsOneWidget);
    },
  );

  testWidgets(
    'privacy choices distinguish withdrawal, study deletion and account deletion',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: PrivacyChoices(
            api: Api(
              Uri.parse('https://citizencentric.co.uk'),
              'synthetic-token',
            ),
            onSessionEnded: () async {},
          ),
        ),
      );

      expect(find.text('Withdraw from this study'), findsOneWidget);
      expect(find.text('Withdraw and delete my data'), findsOneWidget);
      expect(find.text('Delete my Citizen Centric account'), findsOneWidget);
    },
  );
}
