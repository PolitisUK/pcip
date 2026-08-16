"""Study governance validation and launch-readiness assessment.

The assessment identifies missing controller decisions. It is not legal advice
and never fills a controller decision from a platform default.
"""

import json
from dataclasses import dataclass

from .models import StudyGovernance


FEATURES = {"messaging", "photo", "document", "audio", "ai_research_support"}
ASSESSMENT_STATES = {"not_assessed", "not_required", "recorded", "review_required"}
SPECIAL_CATEGORY_STATES = {"not_assessed", "no", "yes"}


@dataclass(frozen=True)
class LaunchReadiness:
    status: str
    missing: tuple[str, ...]
    review_required: tuple[str, ...]

    @property
    def can_launch(self) -> bool:
        return self.status == "complete"


@dataclass(frozen=True)
class StudyDocumentReference:
    document_type: str
    version: str
    reference: str
    effective_date: str


def study_document_references(governance: StudyGovernance | None) -> tuple[StudyDocumentReference, ...]:
    if governance is None:
        return ()
    return (
        StudyDocumentReference(
            "participant_information",
            governance.participant_information_version,
            governance.participant_information_reference,
            governance.participant_information_effective_date,
        ),
        StudyDocumentReference(
            "privacy_notice",
            governance.privacy_notice_version,
            governance.privacy_notice_reference,
            governance.privacy_notice_effective_date,
        ),
        StudyDocumentReference(
            "consent_text",
            governance.consent_text_version,
            governance.consent_text_reference,
            governance.consent_text_effective_date,
        ),
    )


def missing_document_references(governance: StudyGovernance) -> tuple[str, ...]:
    required = []
    if governance.participant_information_available:
        required.append("participant information")
    if governance.privacy_information_available:
        required.append("privacy notice")
    if governance.participation_consent_configured:
        required.append("consent text")
    documents = {item.document_type: item for item in study_document_references(governance)}
    field_name = {
        "participant information": "participant_information",
        "privacy notice": "privacy_notice",
        "consent text": "consent_text",
    }
    missing = []
    for label in required:
        item = documents[field_name[label]]
        if not (item.reference.strip() and item.version.strip() and item.effective_date.strip()):
            missing.append(f"{label} reference, version and effective date")
    return tuple(missing)


def enabled_features(governance: StudyGovernance | None) -> set[str]:
    if governance is None:
        return set()
    try:
        values = json.loads(governance.enabled_features_json or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        return set()
    return {str(value) for value in values if str(value) in FEATURES}


def study_launch_readiness(governance: StudyGovernance | None) -> LaunchReadiness:
    if governance is None:
        return LaunchReadiness(
            "incomplete",
            (
                "controller identity", "controller privacy contact", "participant information",
                "privacy information", "Article 6 lawful basis", "research participation consent",
                "retention approach", "withdrawal process", "deletion handling", "data categories",
                "participant population", "enabled participant features", "ethics assessment",
                "DPIA assessment", "international-transfer assessment",
            ),
            (),
        )

    missing = []
    required_text = {
        "controller identity": governance.controller_name,
        "controller privacy contact": governance.controller_privacy_contact,
        "research contact": governance.research_contact,
        "participant population": governance.participant_population,
        "data categories": governance.data_categories,
        "Article 6 lawful basis": governance.article_6_lawful_basis,
        "retention approach": governance.retention_description,
        "security considerations": governance.security_considerations,
    }
    missing.extend(label for label, value in required_text.items() if not value.strip())
    if not governance.participation_consent_configured:
        missing.append("research participation consent")
    if not governance.participant_information_available:
        missing.append("participant information")
    if not governance.privacy_information_available:
        missing.append("privacy information")
    if not governance.withdrawal_process_defined:
        missing.append("withdrawal process")
    if not governance.deletion_handling_defined:
        missing.append("deletion handling")
    missing.extend(missing_document_references(governance))
    if not governance.features_assessed:
        missing.append("enabled participant features")
    if governance.special_category_data == "not_assessed":
        missing.append("special-category data assessment")
    for label, value in {
        "ethics assessment": governance.ethics_status,
        "DPIA assessment": governance.dpia_status,
        "international-transfer assessment": governance.international_transfer_assessment,
    }.items():
        if value == "not_assessed":
            missing.append(label)

    review = []
    features = enabled_features(governance)
    if governance.special_category_data == "yes" and not governance.article_9_condition.strip():
        review.append("Article 9 condition for special-category data")
    if "ai_research_support" in features and not governance.ai_features_disclosed:
        review.append("AI feature disclosure and approval")
    for label, value in {
        "ethics": governance.ethics_status,
        "DPIA": governance.dpia_status,
        "international transfer": governance.international_transfer_assessment,
    }.items():
        if value == "review_required":
            review.append(f"{label} review")

    if missing:
        return LaunchReadiness("incomplete", tuple(missing), tuple(review))
    if review:
        return LaunchReadiness("review_required", (), tuple(review))
    return LaunchReadiness("complete", (), ())
