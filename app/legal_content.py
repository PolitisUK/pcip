"""Controlled public legal content for Citizen Centric.

This is platform information, effective 15 August 2026. Study-specific
participant information, privacy notices, legal bases and retention periods are
owned by the relevant controller and must be configured for each study.
"""

# Controlled legal prose is kept as complete paragraphs for accurate review.
# ruff: noqa: E501

from dataclasses import dataclass

LEGAL_VERSION = "1.0"
LEGAL_EFFECTIVE_DATE = "15 August 2026"
CONTACT_EMAIL = "info@politisconsulting.co.uk"
COMPANY_NAME = "Politis Ltd"
COMPANY_NUMBER = "13661766"
ICO_REFERENCE = "ZB738312"
REGISTERED_OFFICE = "The Old Courthouse, Orsett Road, Grays, Essex, England, RM17 5DD"


@dataclass(frozen=True)
class LegalSection:
    heading: str
    paragraphs: tuple[str, ...]


@dataclass(frozen=True)
class LegalDocument:
    slug: str
    title: str
    summary: str
    sections: tuple[LegalSection, ...]


PUBLIC_LEGAL_DOCUMENTS = {
    "privacy": LegalDocument(
        "privacy",
        "Privacy Notice",
        "How Citizen Centric supports research organisations and participants.",
        (
            LegalSection("Our role", (
                "Citizen Centric is provided by Politis Ltd. In many studies, the research organisation is the controller for Study Data and Politis Ltd processes that data on its documented instructions. The study-specific privacy information explains the arrangement for a particular study.",
                f"{COMPANY_NAME} is registered in England and Wales. Registered office: {REGISTERED_OFFICE}. Company number {COMPANY_NUMBER}. ICO registration reference {ICO_REFERENCE}.",
            )),
            LegalSection("Keeping information", (
                "Information is kept only for as long as necessary for its purpose. Study Data follows the controller-approved retention period documented for the study. Where Politis Ltd acts as processor, it follows the controller’s documented retention and deletion instructions, subject to legal obligations.",
                "We do not use a single arbitrary retention period for every study.",
            )),
            LegalSection("Rights and requests", (
                "Participants can ask to withdraw from a study or request deletion through the secure participant experience. These requests are handled on the server and are not a local-only action.",
                f"For questions about the Citizen Centric service, contact {CONTACT_EMAIL}. For a study-specific request, use the contact details supplied by the research organisation.",
            )),
            LegalSection("Where information is processed", (
                "The approved platform policy is to host and process personal data in the UK and/or EU/EEA. Study-specific information should identify any arrangements that apply to that study.",
            )),
        ),
    ),
    "terms": LegalDocument(
        "terms",
        "Terms of Use",
        "Using Citizen Centric safely and respectfully.",
        (
            LegalSection("Using the service", (
                "Use Citizen Centric only through authorised access and in line with the research organisation’s instructions. The service supports research; it does not replace emergency, medical, legal or safeguarding services.",
            )),
            LegalSection("Your responsibilities", (
                "Keep access credentials and participant invitations private. Do not try to access another person’s information, bypass security controls, upload malicious material or use the service to harass or harm anyone.",
            )),
            LegalSection("Study terms", (
                "Organisation and customer contractual terms, data-processing schedules and study-specific terms are provided to the relevant authorised parties. They are not participant-facing documents.",
            )),
        ),
    ),
    "cookies": LegalDocument(
        "cookies",
        "Cookie and Similar Technologies Policy",
        "The technologies used to keep the web service and participant app working.",
        (
            LegalSection("Strictly necessary website cookies", (
                "The web service uses strictly necessary session and security cookies where needed to provide authenticated access and protect requests. They are not used for advertising or cross-site behavioural tracking.",
            )),
            LegalSection("Mobile app storage", (
                "Mobile drafts and secure session storage are not cookies. The participant app uses secure device storage for session credentials and local storage for drafts and safe offline queueing.",
            )),
            LegalSection("Analytics and tracking", (
                "Citizen Centric does not use marketing or participant-profiling tracking in the participant app. Operational diagnostics, security logging and service-performance telemetry may be used to run and protect the service. Non-essential analytics must not be enabled without the appropriate controls.",
            )),
        ),
    ),
    "accessibility": LegalDocument(
        "accessibility",
        "Accessibility Statement",
        "Our approach to making Citizen Centric usable for more people.",
        (
            LegalSection("Our approach", (
                "Citizen Centric is designed with clear labels, meaningful status messages, scalable text, accessible touch targets and controls that do not rely on colour alone. We continue to test with assistive technologies and real devices.",
                "We do not claim a certification or full assistive-technology conformance that has not been independently verified.",
            )),
            LegalSection("Getting help", (
                f"If you experience a barrier, contact the relevant research team or email {CONTACT_EMAIL} with enough detail for us to understand the problem.",
            )),
        ),
    ),
    "acceptable-use": LegalDocument(
        "acceptable-use",
        "Acceptable Use Policy",
        "The standards that help keep Citizen Centric safe and respectful.",
        (
            LegalSection("Please do", (
                "Use the service for legitimate research activity, keep credentials and invitation codes private, and share only material you are entitled to provide.",
            )),
            LegalSection("Please do not", (
                "Do not attempt unauthorised access, interfere with the service, upload malware, expose another person’s private information, or use Citizen Centric to harm, harass or discriminate against anyone.",
            )),
        ),
    ),
    "legal-information": LegalDocument(
        "legal-information",
        "Legal Information",
        "Company and regulatory information for Citizen Centric.",
        (
            LegalSection("Company details", (
                f"Citizen Centric is provided by {COMPANY_NAME}. Company number {COMPANY_NUMBER}. Registered office: {REGISTERED_OFFICE}.",
                f"ICO registration/reference: {ICO_REFERENCE}. Contact: {CONTACT_EMAIL}.",
            )),
        ),
    ),
    "contact": LegalDocument(
        "contact",
        "Contact",
        "How to contact Politis Ltd about Citizen Centric.",
        (
            LegalSection("Platform contact", (
                f"Email {CONTACT_EMAIL} for questions about the Citizen Centric platform.",
            )),
            LegalSection("Study contact", (
                "For questions about a specific study or participation, use the contact details in the participant information supplied by the research organisation.",
            )),
        ),
    ),
}


def public_legal_document(slug: str) -> LegalDocument | None:
    return PUBLIC_LEGAL_DOCUMENTS.get(slug)
