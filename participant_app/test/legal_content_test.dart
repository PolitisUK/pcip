import 'package:flutter_test/flutter_test.dart';
import 'package:participant_app/legal_content.dart';

void main() {
  test(
    'participant legal documents are versioned and independently available',
    () {
      expect(legalPackVersion, '1.0');
      expect(legalPackEffectiveDate, '15 August 2026');
      expect(
        participantLegalDocuments.map((document) => document.id),
        containsAll([
          'privacy-at-a-glance',
          'privacy',
          'participant-information',
          'consent-information',
          'terms',
          'cookies',
          'accessibility',
          'acceptable-use',
          'data-rights',
          'legal-information',
        ]),
      );
      expect(
        privacyAtAGlanceDocument.sections
            .expand((section) => section.paragraphs)
            .join(' '),
        contains('public or shared foundation models'),
      );
    },
  );
}
