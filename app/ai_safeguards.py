"""Non-negotiable server-side safeguards for AI-assisted research analysis."""
from dataclasses import dataclass

QUALITATIVE_CONFIDENCE_CATEGORIES = {"weak", "developing", "moderate", "strong", "contested"}

class SafeguardViolation(ValueError):
    pass

@dataclass(frozen=True)
class SourceClaim:
    source_id: int
    quote: str

def validate_provisional_ai_output(output: dict, source_text: str) -> None:
    if output.get("needs_researcher_review") is not True:
        raise SafeguardViolation("AI output must require researcher review")
    if output.get("status") not in (None, "awaiting_researcher_review"):
        raise SafeguardViolation("AI output cannot set an accepted status")
    codes = output.get("suggested_codes")
    if not isinstance(codes, list):
        raise SafeguardViolation("AI suggested_codes must be a list")
    for code in codes:
        if not isinstance(code, dict) or not isinstance(code.get("evidence"), str):
            raise SafeguardViolation("Every code requires source evidence")
        if code["evidence"].strip() not in source_text:
            raise SafeguardViolation("AI evidence quote is not exact source text")
    forbidden = ("statistically representative", "proves caus", "causes ", "population prevalence")
    text = str(output.get("provisional_insight", "")).lower()
    if any(term in text for term in forbidden):
        raise SafeguardViolation("Unsupported statistical or causal claim")

def validate_scope(organisation_id: int | None, study_id: int | None, rows: list[dict]) -> None:
    if not organisation_id or not study_id:
        raise SafeguardViolation("Organisation and study scope are mandatory")
    if any(row.get("organisation_id") != organisation_id or row.get("study_id") != study_id for row in rows):
        raise SafeguardViolation("Cross-scope retrieval result rejected")

def validate_confidence(category: str, support_participant_ids: set[int], contradiction_ids: list[int]) -> None:
    if category not in QUALITATIVE_CONFIDENCE_CATEGORIES:
        raise SafeguardViolation("Confidence category is not qualitative")
    if category == "strong" and len(support_participant_ids) < 2:
        raise SafeguardViolation("One participant cannot create strong evidence")
    if contradiction_ids and category != "contested":
        raise SafeguardViolation("Contradictory evidence must be contested")
