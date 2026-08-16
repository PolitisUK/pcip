"""Versioned catalogue of the approved Citizen Centric legal sources.

The legal centre is source-backed.  The Markdown files in
``legal_sources/canonical`` are faithful text extractions of the approved
Legal Pack v1.0 documents.  Editorial production notes and incomplete fields
are omitted from public rendering rather than shown to users.
"""

import re
from dataclasses import dataclass
from pathlib import Path

LEGAL_VERSION = "1.0"
LEGAL_EFFECTIVE_DATE = "15 August 2026"
CONTACT_EMAIL = "info@politisconsulting.co.uk"
COMPANY_NAME = "Politis Ltd"
COMPANY_NUMBER = "13661766"
ICO_REFERENCE = "ZB738312"
REGISTERED_OFFICE = "The Old Courthouse, Orsett Road, Grays, Essex, England, RM17 5DD"

_SOURCE_DIRECTORY = Path(__file__).with_name("legal_sources")
_NUMBERED_HEADING = re.compile(r"^\d+(?:\.\d+)*\.?\s+[A-Z]")
_EDITORIAL_MARKERS = ("[CLIENT INPUT REQUIRED", "[CONFIRM ")


@dataclass(frozen=True)
class LegalSection:
    heading: str
    paragraphs: tuple[str, ...] = ()
    bullets: tuple[str, ...] = ()


@dataclass(frozen=True)
class LegalDocument:
    document_id: str
    title: str
    summary: str
    audience: str
    publication_status: str
    source_file: str
    sections: tuple[LegalSection, ...] = ()

    @property
    def is_published(self) -> bool:
        return self.publication_status == "published"


def _plain_markdown(value: str) -> str:
    """Remove presentation marks only; legal wording remains unchanged."""
    return value.replace("**", "").replace("`", "").strip()


def _is_editorial_or_incomplete(line: str) -> bool:
    return any(marker in line.upper() for marker in _EDITORIAL_MARKERS)


def _is_heading(line: str) -> bool:
    return line.startswith("## ") or bool(_NUMBERED_HEADING.match(line)) or line in {
        "About this policy", "App legal area",
    }


def _sections_from_markdown(filename: str) -> tuple[LegalSection, ...]:
    """Build accessible sections from canonical text without inventing copy."""
    lines = (_SOURCE_DIRECTORY / filename).read_text(encoding="utf-8").splitlines()
    sections: list[LegalSection] = []
    heading = "About this document"
    paragraphs: list[str] = []
    bullets: list[str] = []

    def append_section() -> None:
        if paragraphs or bullets:
            sections.append(LegalSection(heading, tuple(paragraphs), tuple(bullets)))

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(("<!--", "# ")):
            continue
        if _is_editorial_or_incomplete(stripped):
            continue
        if _is_heading(stripped):
            append_section()
            heading = _plain_markdown(stripped.removeprefix("## "))
            paragraphs = []
            bullets = []
        elif stripped.startswith(("- ", "• ")):
            bullets.append(_plain_markdown(stripped[2:]))
        elif stripped.startswith("|"):
            if not re.fullmatch(r"\|[\s|:-]+\|", stripped):
                paragraphs.append(_plain_markdown(" · ".join(
                    cell.strip() for cell in stripped.strip("|").split("|")
                )))
        else:
            paragraphs.append(_plain_markdown(stripped))
    append_section()
    return tuple(sections)


def _source_document(*, document_id: str, title: str, summary: str, filename: str, audience: str) -> LegalDocument:
    return LegalDocument(
        document_id=document_id, title=title, summary=summary, audience=audience,
        publication_status="published", source_file=f"app/legal_sources/{filename}",
        sections=_sections_from_markdown(filename),
    )


LEGAL_DOCUMENTS = {
    "privacy": _source_document(document_id="privacy", title="Privacy Notice", summary="How Citizen Centric handles personal data.", filename="canonical/privacy_notice_v1.md", audience="public and participant"),
    "terms": _source_document(document_id="terms", title="Terms of Use", summary="Terms for participant and public use of Citizen Centric.", filename="canonical/terms_of_use_v1.md", audience="public and participant"),
    "cookies": _source_document(document_id="cookies", title="Cookie and Similar Technologies Policy", summary="How cookies, app storage and similar technologies are used.", filename="canonical/cookie_policy_v1.md", audience="public and participant"),
    "accessibility": _source_document(document_id="accessibility", title="Accessibility Statement", summary="Our current approach to accessible use of Citizen Centric.", filename="canonical/accessibility_statement_v1.md", audience="public and participant"),
    "acceptable-use": _source_document(document_id="acceptable-use", title="Acceptable Use Policy", summary="Standards for safe, lawful and respectful platform use.", filename="canonical/acceptable_use_v1.md", audience="public and participant"),
    "legal": _source_document(document_id="legal", title="Legal Information", summary="Corporate, contact and legal information for Citizen Centric.", filename="canonical/legal_information_v1.md", audience="public and participant"),
}

CUSTOMER_LEGAL_DOCUMENTS = {
    "saas-terms": _source_document(document_id="saas-terms", title="Organisation SaaS Terms Agreement", summary="Customer agreement template and contractual terms.", filename="canonical/organisation_saas_terms_v1.md", audience="customer"),
    "dpa": _source_document(document_id="dpa", title="Data Processing Agreement", summary="UK GDPR Article 28 schedule for Citizen Centric customers.", filename="canonical/dpa_article_28_v1.md", audience="customer"),
    "subprocessors": _source_document(document_id="subprocessors", title="Subprocessor Schedule", summary="Customer-facing schedule of Citizen Centric service providers.", filename="canonical/subprocessor_schedule_v1.md", audience="customer"),
    "ai-services": _source_document(document_id="ai-services", title="AI Services Schedule", summary="Customer contractual schedule for approved AI-assisted services.", filename="canonical/ai_services_schedule_v1.md", audience="customer"),
}


def public_legal_document(slug: str) -> LegalDocument | None:
    return LEGAL_DOCUMENTS.get(slug)


def customer_legal_document(slug: str) -> LegalDocument | None:
    return CUSTOMER_LEGAL_DOCUMENTS.get(slug)
