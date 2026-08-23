"""Versioned catalogue of approved, participant-facing legal sources.

The public Legal Centre and the generated Flutter fallback derive from the
same repository-native Markdown. DOCX files are reviewed during publication,
never converted by the deployed service.
"""

import re
from dataclasses import dataclass
from pathlib import Path

LEGAL_VERSION = "1.1"
LEGAL_EFFECTIVE_DATE = "18 August 2026"
LEGACY_VERSION = "1.0"
LEGACY_EFFECTIVE_DATE = "15 August 2026"
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
    anchor: str = ""
    level: int = 2


@dataclass(frozen=True)
class LegalDocument:
    document_id: str
    title: str
    summary: str
    audience: str
    publication_status: str
    source_file: str
    version: str = LEGACY_VERSION
    effective_date: str = LEGACY_EFFECTIVE_DATE
    sections: tuple[LegalSection, ...] = ()

    @property
    def is_published(self) -> bool:
        return self.publication_status == "published"


def _plain_markdown(value: str) -> str:
    """Remove presentation marks only; legal wording remains unchanged."""
    return value.replace("**", "").replace("`", "").strip()


def _is_editorial_or_incomplete(line: str) -> bool:
    return any(marker in line.upper() for marker in _EDITORIAL_MARKERS)


def _heading_details(line: str) -> tuple[str, int] | None:
    if line.startswith("### "):
        return _plain_markdown(line.removeprefix("### ")), 3
    if line.startswith("## "):
        return _plain_markdown(line.removeprefix("## ")), 2
    if bool(_NUMBERED_HEADING.match(line)) or line in {
        "About this policy", "App legal area",
    }:
        return _plain_markdown(line), 2
    return None


def _anchor(value: str, used: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "section"
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _sections_from_markdown(filename: str) -> tuple[LegalSection, ...]:
    """Build accessible sections from canonical text without inventing copy."""
    lines = (_SOURCE_DIRECTORY / filename).read_text(encoding="utf-8").splitlines()
    sections: list[LegalSection] = []
    heading = "About this document"
    heading_level = 2
    paragraphs: list[str] = []
    bullets: list[str] = []
    used_anchors: set[str] = set()

    def append_section() -> None:
        if paragraphs or bullets:
            sections.append(LegalSection(
                heading=heading,
                anchor=_anchor(heading, used_anchors),
                level=heading_level,
                paragraphs=tuple(paragraphs),
                bullets=tuple(bullets),
            ))

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(("<!--", "# ")):
            continue
        if _is_editorial_or_incomplete(stripped):
            continue
        heading_details = _heading_details(stripped)
        if heading_details:
            append_section()
            heading, heading_level = heading_details
            paragraphs = []
            bullets = []
        elif stripped.startswith(("- ", "• ")):
            bullets.append(_plain_markdown(stripped[2:]))
        elif stripped.startswith("> "):
            paragraphs.append(_plain_markdown(stripped[2:]))
        elif stripped.startswith("|"):
            if not re.fullmatch(r"\|[\s|:-]+\|", stripped):
                paragraphs.append(_plain_markdown(" · ".join(
                    cell.strip() for cell in stripped.strip("|").split("|")
                )))
        else:
            paragraphs.append(_plain_markdown(stripped))
    append_section()
    return tuple(sections)


def _source_document(*, document_id: str, title: str, summary: str, filename: str, audience: str, version: str = LEGACY_VERSION, effective_date: str = LEGACY_EFFECTIVE_DATE) -> LegalDocument:
    return LegalDocument(
        document_id=document_id, title=title, summary=summary, audience=audience,
        publication_status="published", source_file=f"app/legal_sources/{filename}", version=version, effective_date=effective_date,
        sections=_sections_from_markdown(filename),
    )


LEGAL_DOCUMENTS = {
    "privacy": _source_document(document_id="privacy", title="Platform Privacy Notice", summary="How Politis Ltd handles personal information when operating Citizen Centric.", filename="canonical/platform_privacy_notice_v1_1.md", audience="public and participant", version=LEGAL_VERSION, effective_date=LEGAL_EFFECTIVE_DATE),
    "data-rights": _source_document(document_id="data-rights", title="Data Rights Policy", summary="How to exercise data-protection rights and raise a complaint.", filename="canonical/data_rights_policy_v1_1.md", audience="public and participant", version=LEGAL_VERSION, effective_date=LEGAL_EFFECTIVE_DATE),
    "consent": _source_document(document_id="consent", title="Consent Notice", summary="How research participation consent is obtained, recorded and withdrawn.", filename="canonical/consent_notice_v1_1.md", audience="public and participant", version=LEGAL_VERSION, effective_date=LEGAL_EFFECTIVE_DATE),
    "terms": _source_document(document_id="terms", title="Terms of Use", summary="Terms for participant and public use of Citizen Centric.", filename="canonical/terms_of_use_v1.md", audience="public and participant"),
    "cookies": _source_document(document_id="cookies", title="Cookie and Similar Technologies Policy", summary="How cookies, app storage and similar technologies are used.", filename="canonical/cookie_policy_v1.md", audience="public and participant"),
    "accessibility": _source_document(document_id="accessibility", title="Accessibility Policy", summary="Our approach to accessible participation and reasonable adjustments.", filename="canonical/accessibility_policy_v1_1.md", audience="public and participant", version=LEGAL_VERSION, effective_date=LEGAL_EFFECTIVE_DATE),
    "acceptable-use": _source_document(document_id="acceptable-use", title="Acceptable Use Policy", summary="Standards for safe, lawful and respectful platform use.", filename="canonical/acceptable_use_v1.md", audience="public and participant"),
    "legal": _source_document(document_id="legal", title="Legal Information", summary="Corporate, contact and legal information for Citizen Centric.", filename="canonical/legal_information_v1.md", audience="public and participant"),
}

PARTICIPANT_POLICY_SLUGS = ("privacy", "data-rights", "accessibility", "consent")


def participant_policy_documents() -> tuple[LegalDocument, ...]:
    return tuple(LEGAL_DOCUMENTS[slug] for slug in PARTICIPANT_POLICY_SLUGS)

CUSTOMER_LEGAL_DOCUMENTS = {
    "saas-terms": _source_document(document_id="saas-terms", title="Organisation SaaS Terms Agreement", summary="Customer agreement template and contractual terms.", filename="canonical/organisation_saas_terms_v1.md", audience="customer"),
    "dpa": _source_document(document_id="dpa", title="Data Processing Agreement", summary="UK GDPR Article 28 schedule for Citizen Centric customers.", filename="canonical/dpa_article_28_v1_1.md", audience="customer", version="1.1", effective_date="18 August 2026"),
    "subprocessors": _source_document(document_id="subprocessors", title="Subprocessor Schedule", summary="Customer-facing schedule of Citizen Centric service providers.", filename="canonical/subprocessor_schedule_v1.md", audience="customer"),
    "ai-services": _source_document(document_id="ai-services", title="AI Services Schedule", summary="Customer contractual schedule for approved AI-assisted services.", filename="canonical/ai_services_schedule_v1.md", audience="customer"),
}


def public_legal_document(slug: str) -> LegalDocument | None:
    return LEGAL_DOCUMENTS.get(slug)


def customer_legal_document(slug: str) -> LegalDocument | None:
    return CUSTOMER_LEGAL_DOCUMENTS.get(slug)
