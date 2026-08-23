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
        ], documentsRequired: false, documentsLoading: false, documentsError: null, onRetry: () async {}, onAccept: (_) async {})),
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

  test('invitation workflow state takes precedence over participant-wide consent', () {
    final session = <String, dynamic>{
      'participant': {'consent_status': 'granted'},
      'next_action': 'consent_required',
      'invitation': {'accepted_at': null, 'requires_study_documents': true},
    };

    expect(invitationRequiresConsent(session), isTrue);
    expect(invitationRequiresStudyDocuments(session), isTrue);
  });

  testWidgets('bound document load failure is recoverable and cannot submit consent', (tester) async {
    var loaded = false;
    Map<String, String>? acceptedHashes;
    const documents = [
      {'document_type': 'participant_information', 'title': 'Study B information', 'version': 'B1', 'reference': 'B-PI', 'effective_date': '18 August 2026', 'content_sha256': 'hash-information', 'body': 'Study B information.'},
      {'document_type': 'privacy_notice', 'title': 'Study B privacy', 'version': 'B1', 'reference': 'B-PN', 'effective_date': '18 August 2026', 'content_sha256': 'hash-privacy', 'body': 'Study B privacy.'},
      {'document_type': 'consent_text', 'title': 'Study B consent', 'version': 'B1', 'reference': 'B-CT', 'effective_date': '18 August 2026', 'content_sha256': 'hash-consent', 'body': 'Study B consent.'},
    ];

    await tester.pumpWidget(StatefulBuilder(builder: (context, setState) => MaterialApp(home: Consent(
      error: null,
      documents: loaded ? documents : const [],
      documentsRequired: true,
      documentsLoading: false,
      documentsError: loaded ? null : 'We could not load this study’s consent documents. Your consent has not been submitted.',
      onRetry: () async => setState(() => loaded = true),
      onAccept: (hashes) async => acceptedHashes = hashes,
    ))));

    expect(find.text('Try again'), findsOneWidget);
    await tester.tap(find.text('I understand and agree to take part.'));
    expect(tester.widget<FilledButton>(find.byType(FilledButton)).onPressed, isNull);
    await tester.tap(find.text('Try again'));
    await tester.pump();
    expect(find.text('Read Study B information (version B1)'), findsOneWidget);
    for (final label in ['Read Study B information (version B1)', 'Read Study B privacy (version B1)', 'Read Study B consent (version B1)']) {
      await tester.tap(find.text(label));
      await tester.pumpAndSettle();
      await tester.pageBack();
      await tester.pumpAndSettle();
    }
    await tester.tap(find.text('I understand and agree to take part.'));
    await tester.tap(find.text('Accept and continue'));
    await tester.pump();
    expect(acceptedHashes, {
      'participant_information': 'hash-information',
      'privacy_notice': 'hash-privacy',
      'consent_text': 'hash-consent',
    });
  });
}
