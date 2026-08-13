import json
from datetime import datetime, timezone

from .models import ResearchAnalysisSuggestion


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
