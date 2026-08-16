"""Import canonical Legal Pack DOCX content as reviewable Markdown sources.

The conversion intentionally preserves paragraph and table-cell text. It is an
offline release-maintenance tool; publishing remains controlled by the legal
content catalogue and its source-status tests.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


CANONICAL_DIRECTORY = Path(
    "/Users/politisltd/Desktop/Politis/"
    "Citizen_Centric_Legal_Pack_v1.0_2026-08-15"
)
OUTPUT_DIRECTORY = Path("app/legal_sources/canonical")

DOCUMENTS = {
    "privacy_notice_v1.md": "01_Citizen_Centric_Platform_Privacy_Notice_v1.0.docx",
    "accessibility_statement_v1.md": "02_Citizen_Centric_Accessibility_Statement_v1.0.docx",
    "terms_of_use_v1.md": "Citizen Centric Terms of Use - Revised.docx",
    "cookie_policy_v1.md": "Citizen Centric Cookie Policy - Revised.docx",
    "acceptable_use_v1.md": "Acceptable Use Policy for Citizen Centric - Revised.docx",
    "legal_information_v1.md": "Citizen Centric Legal Information - Revised.docx",
    "organisation_saas_terms_v1.md": "ORGANISATION SaaS TERMS AGREEMENT - Revised.docx",
    "dpa_article_28_v1.md": "03_Citizen_Centric_DPA_Article_28_Schedule_v1.0.docx",
    "subprocessor_schedule_v1.md": "04_Citizen_Centric_Subprocessor_Schedule_v1.0.docx",
    "ai_services_schedule_v1.md": "AI Services Schedule - Revised.docx",
    "participant_information_template_v1.md": "Participant Information Sheet and Consent Template - Revised.docx",
    "cookie_preference_wording_v1.md": "Cookie Banner and Preference Centre Wording for Citizen Centric - Revised.docx",
    "study_onboarding_questionnaire_v1.md": "Citizen Centric Study Data Protection and Customer Onboarding Questionnaire.docx",
}


def _row(cells: list[str]) -> str:
    return "| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |"


def convert(source: Path) -> str:
    document = Document(source)
    lines = [f"<!-- Canonical source: {source.name} -->", ""]
    for block in document.iter_inner_content():
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if text:
                lines.extend((text, ""))
        elif isinstance(block, Table):
            rows = [
                [" ".join(cell.text.split()) for cell in row.cells]
                for row in block.rows
            ]
            if rows:
                lines.append(_row(rows[0]))
                lines.append(_row(["---"] * len(rows[0])))
                lines.extend(_row(row) for row in rows[1:])
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    if not CANONICAL_DIRECTORY.is_dir():
        raise SystemExit(f"Canonical Legal Pack unavailable: {CANONICAL_DIRECTORY}")
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for destination, source_name in DOCUMENTS.items():
        source = CANONICAL_DIRECTORY / source_name
        if not source.is_file():
            raise SystemExit(f"Canonical source unavailable: {source}")
        (OUTPUT_DIRECTORY / destination).write_text(convert(source), encoding="utf-8")


if __name__ == "__main__":
    main()
