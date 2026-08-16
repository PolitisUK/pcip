"""Versioned public legal-content catalogue.

Only a source-complete, owner-approved document may be rendered as policy
content. Study-specific notices remain controller supplied and are served via
the consent-document evidence model instead of this platform catalogue.
"""

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
    source_file: str | None
    sections: tuple[LegalSection, ...] = ()

    @property
    def is_published(self) -> bool:
        return self.publication_status == "published"


def _plain_markdown(value: str) -> str:
    """Remove only Markdown presentation marks; source wording is unchanged."""
    return value.replace("**", "").replace("`", "").strip()


def _sections_from_markdown(filename: str) -> tuple[LegalSection, ...]:
    lines = (_SOURCE_DIRECTORY / filename).read_text(encoding="utf-8").splitlines()
    sections: list[LegalSection] = []
    heading = "About this document"
    paragraphs: list[str] = []
    bullets: list[str] = []

    def append_section() -> None:
        if paragraphs or bullets:
            sections.append(
                LegalSection(
                    heading=heading,
                    paragraphs=tuple(paragraphs),
                    bullets=tuple(bullets),
                )
            )

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("# "):
            continue
        if stripped.startswith("## "):
            append_section()
            heading = _plain_markdown(stripped[3:])
            paragraphs = []
            bullets = []
        elif stripped.startswith("- "):
            bullets.append(_plain_markdown(stripped[2:]))
        else:
            paragraphs.append(_plain_markdown(stripped))
    append_section()
    return tuple(sections)


def _published_source_document(
    *,
    document_id: str,
    title: str,
    summary: str,
    filename: str,
) -> LegalDocument:
    return LegalDocument(
        document_id=document_id,
        title=title,
        summary=summary,
        audience="public and participant",
        publication_status="published",
        source_file=f"app/legal_sources/{filename}",
        sections=_sections_from_markdown(filename),
    )


def _awaiting_source_document(
    *, document_id: str, title: str, source_file: str | None
) -> LegalDocument:
    return LegalDocument(
        document_id=document_id,
        title=title,
        summary="This document has not been published because its approved source still requires completion.",
        audience="public and participant",
        publication_status="awaiting_source_completion",
        source_file=source_file,
    )


LEGAL_DOCUMENTS = {
    "terms": _published_source_document(
        document_id="terms",
        title="Terms of Use",
        summary="Terms for invited participant use of Citizen Centric.",
        filename="terms_of_use_v1.md",
    ),
    # Do not fall back to earlier paraphrased copy. The approved sources below
    # retain unresolved fields or are absent entirely.
    "privacy": _awaiting_source_document(
        document_id="privacy",
        title="Privacy Notice",
        source_file="Citizen Centric Legal Pack v1.0: CITIZEN CENTRIC PRIVACY NOTICE.docx",
    ),
    "cookies": _awaiting_source_document(
        document_id="cookies",
        title="Cookie and Similar Technologies Policy",
        source_file="Citizen Centric Legal Pack v1.0: Citizen Centric Cookie Policy - App Ready.md",
    ),
    "accessibility": _awaiting_source_document(
        document_id="accessibility",
        title="Accessibility Statement",
        source_file=None,
    ),
    "acceptable-use": _awaiting_source_document(
        document_id="acceptable-use",
        title="Acceptable Use Policy",
        source_file="Citizen Centric Legal Pack v1.0: Acceptable Use Policy for Citizen Centric - App Ready.md",
    ),
    "legal": _awaiting_source_document(
        document_id="legal",
        title="Legal Information",
        source_file="Citizen Centric Legal Pack v1.0: Citizen Centric Legal Information - Revised.docx",
    ),
}


def public_legal_document(slug: str) -> LegalDocument | None:
    return LEGAL_DOCUMENTS.get(slug)
