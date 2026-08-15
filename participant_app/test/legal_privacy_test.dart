import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:participant_app/legal_privacy.dart';
import 'package:participant_app/main.dart';

void main() {
  testWidgets('legal and privacy centre exposes platform information and choices',
      (tester) async {
    var openedChoices = false;
    await tester.pumpWidget(
      MaterialApp(
        home: LegalPrivacyCentre(
          onOpenPrivacyChoices: () => openedChoices = true,
        ),
      ),
    );

    expect(find.text('Privacy at a glance'), findsOneWidget);
    expect(find.text('Withdrawal and data deletion'), findsOneWidget);

    await tester.tap(find.text('Read privacy at a glance'));
    await tester.pumpAndSettle();
    expect(
      find.text('A short explanation of how this app handles your information.'),
      findsOneWidget,
    );

    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.tap(find.text('Withdrawal and data deletion'));
    expect(openedChoices, isTrue);
  });

  testWidgets('consent links to participant information before acceptance',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(home: Consent(error: null, onAccept: () async {})),
    );

    await tester.tap(find.text('Read participant information'));
    await tester.pumpAndSettle();
    expect(find.text('Taking part through Citizen Centric'), findsOneWidget);
  });
}
