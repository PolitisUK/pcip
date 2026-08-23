import 'package:flutter/material.dart';

import 'legal_content.dart';

class LegalPrivacyCentre extends StatelessWidget {
  const LegalPrivacyCentre({super.key, this.onOpenPrivacyChoices});

  final VoidCallback? onOpenPrivacyChoices;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Legal information')),
    body: ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Semantics(
          header: true,
          child: const Text(
            'Legal information',
            style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
          ),
        ),
        const SizedBox(height: 8),
        const Text(
          'Read the complete Citizen Centric platform policies. Your study provides its own participant information, privacy notice and consent statements.',
        ),
        const SizedBox(height: 20),
        for (final document in platformLegalDocuments)
          Card(
            child: ListTile(
              contentPadding: const EdgeInsets.all(16),
              title: Text(document.title),
              subtitle: Text(
                '${document.summary}\nVersion $legalPackVersion · Effective $legalPackEffectiveDate',
              ),
              isThreeLine: true,
              trailing: const Icon(Icons.chevron_right),
              onTap: () => _open(context, document),
            ),
          ),
        const SizedBox(height: 16),
        if (onOpenPrivacyChoices != null) ...[
          Semantics(
            header: true,
            child: const Text(
              'Your choices',
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
            ),
          ),
          Card(
            child: ListTile(
              contentPadding: const EdgeInsets.all(16),
              title: const Text('Withdrawal and data deletion'),
              subtitle: const Text(
                'Withdraw from a study, request deletion of active study data, or delete your account. These are separate choices.',
              ),
              trailing: const Icon(Icons.chevron_right),
              onTap: onOpenPrivacyChoices,
            ),
          ),
        ],
        const SizedBox(height: 16),
        Semantics(
          label:
              'Legal content version $legalPackVersion, effective $legalPackEffectiveDate',
          child: const Text(
            'Politis Ltd · Company No. 13661766 · ICO ZB738312\ninfo@politisconsulting.co.uk',
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

class LegalDocumentScreen extends StatefulWidget {
  const LegalDocumentScreen({super.key, required this.document});
  final LegalDocument document;
  @override
  State<LegalDocumentScreen> createState() => _LegalDocumentScreenState();
}

class _LegalDocumentScreenState extends State<LegalDocumentScreen> {
  late final List<GlobalKey> _sectionKeys;

  @override
  void initState() {
    super.initState();
    _sectionKeys = List<GlobalKey>.generate(
      widget.document.sections.length,
      (_) => GlobalKey(),
    );
  }

  void _goToSection(int index) {
    final target = _sectionKeys[index].currentContext;
    if (target != null) {
      Scrollable.ensureVisible(
        target,
        duration: const Duration(milliseconds: 250),
      );
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Text(widget.document.title),
      actions: [
        PopupMenuButton<int>(
          tooltip: 'Contents',
          icon: const Icon(Icons.format_list_bulleted),
          onSelected: _goToSection,
          itemBuilder: (context) => [
            for (
              var index = 0;
              index < widget.document.sections.length;
              index++
            )
              PopupMenuItem<int>(
                value: index,
                child: Text(widget.document.sections[index].heading),
              ),
          ],
        ),
      ],
    ),
    body: ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Semantics(
          header: true,
          child: Text(
            widget.document.title,
            style: const TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
          ),
        ),
        const SizedBox(height: 8),
        SelectableText(widget.document.summary),
        const SizedBox(height: 20),
        for (var index = 0; index < widget.document.sections.length; index++)
          _Section(
            key: _sectionKeys[index],
            section: widget.document.sections[index],
          ),
        const SizedBox(height: 16),
        const Divider(),
        const Text(
          'Related platform policies',
          style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
        ),
        for (final related in platformLegalDocuments.where(
          (item) => item.id != widget.document.id,
        ))
          TextButton(
            onPressed: () => Navigator.pushReplacement(
              context,
              MaterialPageRoute<void>(
                builder: (_) => LegalDocumentScreen(document: related),
              ),
            ),
            child: Text('Read ${related.title}'),
          ),
        const SizedBox(height: 12),
        Text('Version $legalPackVersion · Effective $legalPackEffectiveDate'),
      ],
    ),
  );
}

class _Section extends StatelessWidget {
  const _Section({super.key, required this.section});
  final LegalSection section;

  @override
  Widget build(BuildContext context) => Semantics(
    container: true,
    child: Padding(
      padding: EdgeInsets.only(top: section.level == 2 ? 28 : 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Semantics(
            header: true,
            child: Text(
              section.heading,
              style: TextStyle(
                fontSize: section.level == 2 ? 22 : 19,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          const SizedBox(height: 8),
          for (final paragraph in section.paragraphs) ...[
            SelectableText(paragraph),
            const SizedBox(height: 12),
          ],
          for (final bullet in section.bullets)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Padding(
                    padding: EdgeInsets.only(right: 8),
                    child: Text('•', semanticsLabel: 'Bullet'),
                  ),
                  Expanded(child: SelectableText(bullet)),
                ],
              ),
            ),
        ],
      ),
    ),
  );
}
