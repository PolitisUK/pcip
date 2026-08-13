import json
from datetime import datetime, timezone

from .models import EvidenceConfidenceAssessment, ResearchAnalysisSuggestion


class UnsafeAIResponse(ValueError): pass
def response_text(response):
    value=json.loads(response.value_json or '{}'); text=value.get('text') or value.get('value') or ''
    if not isinstance(text,str) or not text.strip(): raise ValueError('Response has no text evidence')
    return text.strip()
def create_suggestion(db,user,study,response,output):
    if user.role not in {'owner','admin','researcher'}: raise PermissionError('Only researchers can request analysis')
    if response.organisation_id!=user.organisation_id or response.study_id!=study.id: raise PermissionError('Source scope mismatch')
    if output.get('needs_researcher_review') is not True: raise UnsafeAIResponse('AI response missing mandatory review gate')
    if not isinstance(output.get('suggested_codes'),list) or not isinstance(output.get('provisional_insight'),str): raise UnsafeAIResponse('AI response schema invalid')
    row=ResearchAnalysisSuggestion(organisation_id=user.organisation_id,study_id=study.id,source_response_id=response.id,source_snapshot=response_text(response),suggested_codes_json=json.dumps(output['suggested_codes']),provisional_insight=output['provisional_insight'],confidence=float(output.get('confidence',0)),status='awaiting_researcher_review')
    db.add(row); return row
def review_suggestion(user,row,decision,note=''):
    if user.role not in {'owner','admin','researcher'}: raise PermissionError('Only researchers can review analysis')
    if row.organisation_id!=user.organisation_id: raise PermissionError('Organisation scope mismatch')
    if row.status!='awaiting_researcher_review': raise ValueError('Suggestion already reviewed')
    if decision not in {'accepted','rejected'} or (decision=='rejected' and not note.strip()): raise ValueError('Invalid review decision')
    row.status=decision; row.reviewer_user_id=user.id; row.reviewer_note=note.strip(); row.reviewed_at=datetime.now(timezone.utc); return row


def build_evidence_confidence(focus, supporting_responses, contradicting_responses):
    """Return qualitative strength, never numeric or population-level confidence."""
    if not focus.strip(): raise ValueError('Assessment focus is required')
    support_ids = [row.id for row in supporting_responses]
    contradiction_ids = [row.id for row in contradicting_responses]
    participants = {row.participant_id for row in supporting_responses}
    limitations = ['This is a qualitative evidence-strength assessment, not a measure of prevalence, causation, or population representation.']
    needs = []
    if contradiction_ids:
        category = 'contested'
        limitations.append('Contradictory or negative-case material remains visible and requires interpretation.')
        needs.append('Compare supporting and contradictory accounts in context with a researcher.')
    elif not support_ids:
        category = 'weak'; limitations.append('No supporting source items were selected.'); needs.append('Identify relevant source material before interpreting this focus.')
    elif len(support_ids) == 1:
        category = 'developing'; limitations.append('One source item cannot establish a wider pattern.'); needs.append('Seek additional perspectives where methodologically appropriate.')
    elif len(participants) < 2:
        category = 'developing'; limitations.append('Supporting material comes from one participant.'); needs.append('Assess whether other accounts complicate this experience.')
    elif len(support_ids) >= 4 and len(participants) >= 3:
        category = 'strong'; needs.append('Retain negative-case searching and contextual interpretation before any finding is proposed.')
    else:
        category = 'moderate'; needs.append('Review contextual completeness and look actively for contradictory accounts.')
    explanation = f"{len(support_ids)} supporting source item(s) from {len(participants)} participant(s); {len(contradiction_ids)} contradictory source item(s)."
    return {'category': category, 'support_ids': support_ids, 'contradiction_ids': contradiction_ids, 'explanation': explanation, 'limitations': limitations, 'strengthening_needs': needs}


def create_confidence_assessment(db, user, study, focus, supporting_responses, contradicting_responses):
    if user.role not in {'owner','admin','researcher'}: raise PermissionError('Only researchers can assess evidence')
    all_rows = [*supporting_responses, *contradicting_responses]
    if any(row.organisation_id != user.organisation_id or row.study_id != study.id for row in all_rows): raise PermissionError('Evidence scope mismatch')
    result = build_evidence_confidence(focus, supporting_responses, contradicting_responses)
    row = EvidenceConfidenceAssessment(organisation_id=user.organisation_id, study_id=study.id, focus=focus.strip(), supporting_response_ids_json=json.dumps(result['support_ids']), contradicting_response_ids_json=json.dumps(result['contradiction_ids']), category=result['category'], explanation=result['explanation'], limitations_json=json.dumps(result['limitations']), strengthening_needs_json=json.dumps(result['strengthening_needs']), status='awaiting_researcher_review')
    db.add(row); return row


def review_confidence_assessment(user, row, decision, note=''):
    if user.role not in {'owner','admin','researcher'}: raise PermissionError('Only researchers can review evidence assessment')
    if row.organisation_id != user.organisation_id: raise PermissionError('Organisation scope mismatch')
    if row.status != 'awaiting_researcher_review': raise ValueError('Assessment already reviewed')
    if decision not in {'accepted','rejected'} or (decision == 'rejected' and not note.strip()): raise ValueError('Invalid review decision')
    row.status = decision; row.reviewer_user_id = user.id; row.reviewer_note = note.strip(); row.reviewed_at = datetime.now(timezone.utc); return row
