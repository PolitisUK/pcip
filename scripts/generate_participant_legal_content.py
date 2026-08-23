"""Generate the Flutter offline legal fallback from canonical Markdown.

Run after an approved policy source changes. The generated Dart is committed so
participants can read the policies without an authenticated webview or network
connection.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    ("platformPrivacyNoticeDocument", "privacy", "Platform Privacy Notice", "How Politis Ltd handles personal information when operating Citizen Centric.", "platform_privacy_notice_v1_1.md"),
    ("dataRightsPolicyDocument", "data-rights", "Data Rights Policy", "How to exercise data-protection rights and raise a complaint.", "data_rights_policy_v1_1.md"),
    ("accessibilityPolicyDocument", "accessibility", "Accessibility Policy", "Our approach to accessible participation and reasonable adjustments.", "accessibility_policy_v1_1.md"),
    ("consentNoticeDocument", "consent", "Consent Notice", "How research participation consent is obtained, recorded and withdrawn.", "consent_notice_v1_1.md"),
)


def dart(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def parse(source: Path) -> list[tuple[str, int, list[str], list[str]]]:
    sections: list[tuple[str, int, list[str], list[str]]] = []
    heading = None
    level = 2
    paragraphs: list[str] = []
    bullets: list[str] = []

    def finish() -> None:
        if heading and (paragraphs or bullets):
            sections.append((heading, level, paragraphs[:], bullets[:]))

    for line in source.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("<!--"):
            continue
        if value.startswith(("### ", "## ")):
            finish()
            level = 3 if value.startswith("### ") else 2
            heading = value[4:] if level == 3 else value[3:]
            paragraphs = []
            bullets = []
        elif heading is not None:
            if value.startswith("- "):
                bullets.append(value[2:])
            elif value.startswith("> "):
                paragraphs.append(value[2:])
            else:
                paragraphs.append(value)
    finish()
    return sections


def main() -> None:
    output = ["// GENERATED FILE - do not edit by hand.", "", "class LegalDocument {", "  const LegalDocument({required this.id, required this.title, required this.summary, required this.sections});", "  final String id;", "  final String title;", "  final String summary;", "  final List<LegalSection> sections;", "}", "", "class LegalSection {", "  const LegalSection(this.heading, this.paragraphs, {this.bullets = const [], this.level = 2});", "  final String heading;", "  final List<String> paragraphs;", "  final List<String> bullets;", "  final int level;", "}", "", "const legalPackVersion = '1.1';", "const legalPackEffectiveDate = '18 August 2026';", "const legalContactEmail = 'info@politisconsulting.co.uk';", "const legalCompanyName = 'Politis Ltd';", "const legalCompanyNumber = '13661766';", "const legalIcoReference = 'ZB738312';", ""]
    for variable, document_id, title, summary, filename in SOURCES:
        output.extend((f"const {variable} = LegalDocument(", f"  id: {dart(document_id)},", f"  title: {dart(title)},", f"  summary: {dart(summary)},", "  sections: ["))
        for heading, level, paragraphs, bullets in parse(ROOT / "app/legal_sources/canonical" / filename):
            output.extend((f"    LegalSection({dart(heading)}, [", *(f"      {dart(value)}," for value in paragraphs), "    ],"))
            if bullets:
                output.extend(("      bullets: [", *(f"        {dart(value)}," for value in bullets), "      ],"))
            output.extend((f"      level: {level},", "    ),"))
        output.extend(("  ],", ");", ""))
    output.extend(("const platformLegalDocuments = [", *(f"  {item[0]}," for item in SOURCES), "];", ""))
    (ROOT / "participant_app/lib/legal_content.generated.dart").write_text("\n".join(output), encoding="utf-8")


if __name__ == "__main__":
    main()
