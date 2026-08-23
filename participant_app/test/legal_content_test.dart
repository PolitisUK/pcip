import 'package:flutter_test/flutter_test.dart';
import 'package:participant_app/legal_content.dart';

void main() {
  test('participant legal documents are versioned, complete and independently available', () {
    expect(legalPackVersion, '1.1');
    expect(legalPackEffectiveDate, '18 August 2026');
    expect(
      participantLegalDocuments.map((document) => document.id),
      orderedEquals(['privacy', 'data-rights', 'accessibility', 'consent']),
    );
    expect(
      platformPrivacyNoticeDocument.sections
          .expand((section) => [...section.paragraphs, ...section.bullets])
          .join(' '),
      contains('public or shared foundation models'),
    );
    expect(consentNoticeDocument.sections.length, greaterThan(8));
    expect(dataRightsPolicyDocument.sections.length, greaterThan(8));
    expect(accessibilityPolicyDocument.sections.length, greaterThan(7));
    expect(
      platformLegalDocuments
          .expand((document) => document.sections)
          .expand((section) => section.paragraphs)
          .join(' '),
      isNot(contains('Version 1.0')),
    );
  });
}
