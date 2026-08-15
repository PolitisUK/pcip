import 'package:flutter/material.dart';

import 'legal_content.dart';

class LegalPrivacyCentre extends StatelessWidget {
  const LegalPrivacyCentre({super.key, required this.onOpenPrivacyChoices});

  final VoidCallback onOpenPrivacyChoices;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Legal and privacy')),
    body: ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Semantics(
          header: true,
          child: const Text(
            'Privacy at a glance',
            style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
          ),
        ),
        const SizedBox(height: 8),
        const Text(
          'A clear overview of how Citizen Centric supports your study and the choices available to you.',
        ),
        const SizedBox(height: 12),
        Card(
          child: ListTile(
            title: const Text('Read privacy at a glance'),
            subtitle: const Text(
              'Secure sessions, drafts, uploads and your choices',
            ),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => _open(context, privacyAtAGlanceDocument),
          ),
        ),
        const SizedBox(height: 20),
        Semantics(
          header: true,
          child: const Text(
            'Your choices',
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
          ),
        ),
        Card(
          child: ListTile(
            title: const Text('Withdrawal and data deletion'),
            subtitle: const Text('Make a request through the secure service'),
            trailing: const Icon(Icons.chevron_right),
            onTap: onOpenPrivacyChoices,
          ),
        ),
        const SizedBox(height: 20),
        Semantics(
          header: true,
          child: const Text(
            'Information',
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
          ),
        ),
        for (final document in participantLegalDocuments.where(
          (document) => document.id != privacyAtAGlanceDocument.id,
        ))
          Card(
            child: ListTile(
              title: Text(document.title),
              subtitle: Text(document.summary),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => _open(context, document),
            ),
          ),
        const SizedBox(height: 16),
        Semantics(
          label:
              'Legal content version $legalPackVersion, effective $legalPackEffectiveDate',
          child: Text(
            'Version $legalPackVersion · Effective $legalPackEffectiveDate\n$legalCompanyName · Company No. $legalCompanyNumber · ICO $legalIcoReference\n$legalContactEmail',
          ),
        ),
      ],
    ),
  );

  static void _open(BuildContext context, LegalDocument document) {
    Navigator.push(
      context,
      MaterialPageRoute<void>(
        builder: (_) => LegalDocumentScreen(document: document),
      ),
    );
  }
}

class LegalDocumentScreen extends StatelessWidget {
  const LegalDocumentScreen({super.key, required this.document});

  final LegalDocument document;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text(document.title)),
    body: ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Semantics(
          header: true,
          child: Text(
            document.title,
            style: const TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
          ),
        ),
        const SizedBox(height: 8),
        Text(document.summary),
        const SizedBox(height: 20),
        for (final section in document.sections) ...[
          Semantics(
            header: true,
            child: Text(
              section.heading,
              style: const TextStyle(fontSize: 21, fontWeight: FontWeight.bold),
            ),
          ),
          const SizedBox(height: 8),
          for (final paragraph in section.paragraphs) ...[
            Text(paragraph),
            const SizedBox(height: 12),
          ],
        ],
        const SizedBox(height: 12),
        Text('Version $legalPackVersion · Effective $legalPackEffectiveDate'),
      ],
    ),
  );
}
