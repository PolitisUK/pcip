"""PostgreSQL regression coverage for account-scoped participant deletion.

The CI migration job runs this file against its disposable PostgreSQL service.
It covers the foreign-key ordering that SQLite does not reproduce.
"""

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.db import SessionLocal, engine
from app.models import (
    Activity,
    ActivityResponse,
    AnalysisCanvas,
    AnalysisCanvasNode,
    AnalysisTarget,
    AnalyticalRelationship,
    CodeApplication,
    EvidenceConfidenceAssessment,
    EvidenceFile,
    Organisation,
    OrganisationMembership,
    OutboxEmail,
    Participant,
    ParticipantAppAccessCode,
    ParticipantInvitation,
    ParticipantMessage,
    ParticipantPasswordCredential,
    ParticipantPrivacyRequest,
    Project,
    PublicAuthSession,
    ResearchAnalysisSuggestion,
    ResearchAnnotation,
    ResearchCode,
    ResearchFinding,
    ResearchMemo,
    ResearchTheme,
    ResearchThemeCode,
    Study,
    StudyEnrolment,
    User,
)
from app.privacy_lifecycle import process_deletion_request, revoke_participant_access

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="requires the CI PostgreSQL service",
)


class RecordingStorage:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete(self, key: str) -> None:
        self.deleted.append(key)


def test_postgres_account_deletion_orders_cleanup_and_preserves_reusable_analysis():
    marker = uuid4().hex
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        organisation = Organisation(
            name=f"REL-02 deletion {marker}",
            slug=f"rel-02-deletion-{marker}",
        )
        db.add(organisation)
        db.flush()
        researcher = User(
            organisation_id=organisation.id,
            name="Synthetic researcher",
            email=f"rel-02-{marker}@example.invalid",
            role="owner",
        )
        db.add(researcher)
        db.flush()
        db.add(
            OrganisationMembership(
                user_id=researcher.id,
                organisation_id=organisation.id,
                role="owner",
                is_active=True,
            )
        )
        project = Project(
            organisation_id=organisation.id,
            title="Synthetic deletion project",
            code=f"REL02-{marker}",
            created_by_id=researcher.id,
        )
        db.add(project)
        db.flush()
        study = Study(
            organisation_id=organisation.id,
            project_id=project.id,
            title="Synthetic deletion study",
            code=f"REL02-STUDY-{marker}",
            created_by_id=researcher.id,
        )
        db.add(study)
        db.flush()
        participant = Participant(
            organisation_id=organisation.id,
            reference=f"REL02-{marker}",
            name="Synthetic deletion participant",
            created_by_id=researcher.id,
        )
        unaffected_participant = Participant(
            organisation_id=organisation.id,
            reference=f"REL02-KEEP-{marker}",
            name="Unaffected synthetic participant",
            created_by_id=researcher.id,
        )
        db.add_all((participant, unaffected_participant))
        db.flush()
        db.add_all(
            (
                StudyEnrolment(
                    organisation_id=organisation.id,
                    study_id=study.id,
                    participant_id=participant.id,
                ),
                StudyEnrolment(
                    organisation_id=organisation.id,
                    study_id=study.id,
                    participant_id=unaffected_participant.id,
                ),
            )
        )
        activity = Activity(
            organisation_id=organisation.id,
            study_id=study.id,
            title="Synthetic deletion activity",
        )
        db.add(activity)
        db.flush()
        response = ActivityResponse(
            organisation_id=organisation.id,
            study_id=study.id,
            activity_id=activity.id,
            participant_id=participant.id,
            value_json='{"answer":"synthetic deletion material"}',
            status="submitted",
        )
        unaffected_response = ActivityResponse(
            organisation_id=organisation.id,
            study_id=study.id,
            activity_id=activity.id,
            participant_id=unaffected_participant.id,
            value_json='{"answer":"unaffected synthetic material"}',
            status="submitted",
        )
        db.add_all((response, unaffected_response))
        db.flush()
        evidence = EvidenceFile(
            organisation_id=organisation.id,
            study_id=study.id,
            activity_id=activity.id,
            participant_id=participant.id,
            response_id=response.id,
            original_name="synthetic.txt",
            stored_name=f"rel02/{marker}/synthetic.txt",
        )
        db.add(evidence)
        invitation = ParticipantInvitation(
            organisation_id=organisation.id,
            participant_id=participant.id,
            study_id=study.id,
            token_hash=f"rel02-token-{marker}",
            expires_at=now + timedelta(days=1),
            invited_by_id=researcher.id,
        )
        db.add(invitation)
        db.flush()
        credential = ParticipantPasswordCredential(
            organisation_id=organisation.id,
            participant_id=participant.id,
            participant_invitation_id=invitation.id,
            login_identifier_normalised=f"participant-{marker}@example.invalid",
            password_hash="synthetic-not-a-password-hash",
        )
        db.add(credential)
        db.flush()
        session = PublicAuthSession(
            scope="participant_api",
            session_hash=f"rel02-session-{marker}",
            participant_invitation_id=invitation.id,
            participant_password_credential_id=credential.id,
            expires_at=now + timedelta(hours=1),
        )
        access_code = ParticipantAppAccessCode(
            organisation_id=organisation.id,
            participant_invitation_id=invitation.id,
            code_hash=f"rel02-code-{marker}",
            expires_at=now + timedelta(hours=1),
        )
        message = ParticipantMessage(
            organisation_id=organisation.id,
            study_id=study.id,
            participant_id=participant.id,
            sender_type="participant",
            body="synthetic deletion message",
        )
        outbox = OutboxEmail(
            organisation_id=organisation.id,
            participant_id=participant.id,
            study_id=study.id,
            recipient=f"participant-{marker}@example.invalid",
            subject="Synthetic deletion mail",
            body="Synthetic deletion mail",
        )
        db.add_all((session, access_code, message, outbox))
        response_target = AnalysisTarget(
            organisation_id=organisation.id,
            study_id=study.id,
            target_type="activity_response",
            activity_response_id=response.id,
            anchor_json='{"start":0,"end":9}',
            created_by_id=researcher.id,
        )
        evidence_target = AnalysisTarget(
            organisation_id=organisation.id,
            study_id=study.id,
            target_type="evidence_file",
            evidence_file_id=evidence.id,
            anchor_json='{"x":0,"y":0,"width":1,"height":1}',
            created_by_id=researcher.id,
        )
        participant_target = AnalysisTarget(
            organisation_id=organisation.id,
            study_id=study.id,
            target_type="participant_case",
            participant_id=participant.id,
            created_by_id=researcher.id,
        )
        db.add_all((response_target, evidence_target, participant_target))
        db.flush()
        research_code = ResearchCode(
            organisation_id=organisation.id,
            study_id=study.id,
            name="Reusable research code",
            created_by_id=researcher.id,
        )
        db.add(research_code)
        db.flush()
        code_application = CodeApplication(
            organisation_id=organisation.id,
            study_id=study.id,
            analysis_target_id=response_target.id,
            research_code_id=research_code.id,
            applied_by_id=researcher.id,
            anchor_json='{"start":0,"end":9}',
        )
        annotation = ResearchAnnotation(
            organisation_id=organisation.id,
            study_id=study.id,
            analysis_target_id=response_target.id,
            author_id=researcher.id,
            anchor_json='{"start":0,"end":9}',
            body="Synthetic deletion annotation",
        )
        target_memo = ResearchMemo(
            organisation_id=organisation.id,
            study_id=study.id,
            scope_type="analysis_target",
            analysis_target_id=response_target.id,
            title="Synthetic target memo",
            body="Synthetic target memo",
            author_id=researcher.id,
        )
        response_memo = ResearchMemo(
            organisation_id=organisation.id,
            study_id=study.id,
            scope_type="response",
            activity_response_id=response.id,
            title="Synthetic response memo",
            body="Synthetic response memo",
            author_id=researcher.id,
        )
        participant_memo = ResearchMemo(
            organisation_id=organisation.id,
            study_id=study.id,
            scope_type="participant",
            participant_id=participant.id,
            title="Synthetic participant memo",
            body="Synthetic participant memo",
            author_id=researcher.id,
        )
        study_memo = ResearchMemo(
            organisation_id=organisation.id,
            study_id=study.id,
            scope_type="study",
            title="Reusable study memo",
            body="Reusable study-level analysis",
            author_id=researcher.id,
        )
        db.add_all(
            (
                code_application,
                annotation,
                target_memo,
                response_memo,
                participant_memo,
                study_memo,
            )
        )
        participant_suggestion = ResearchAnalysisSuggestion(
            organisation_id=organisation.id,
            study_id=study.id,
            source_response_id=response.id,
            source_snapshot="synthetic participant source",
        )
        unaffected_suggestion = ResearchAnalysisSuggestion(
            organisation_id=organisation.id,
            study_id=study.id,
            source_response_id=unaffected_response.id,
            source_snapshot="unaffected synthetic source",
        )
        db.add_all((participant_suggestion, unaffected_suggestion))
        db.flush()
        theme = ResearchTheme(
            organisation_id=organisation.id,
            study_id=study.id,
            name="Reusable study theme",
            source_suggestion_ids_json=json.dumps(
                [participant_suggestion.id, unaffected_suggestion.id]
            ),
            created_by_id=researcher.id,
        )
        converted_finding = ResearchFinding(
            organisation_id=organisation.id,
            study_id=study.id,
            title="Participant-source finding",
            body="Synthetic participant-source finding",
            created_by_id=researcher.id,
            originating_suggestion_id=participant_suggestion.id,
        )
        reusable_finding = ResearchFinding(
            organisation_id=organisation.id,
            study_id=study.id,
            title="Reusable study finding",
            body="Reusable study-level finding",
            created_by_id=researcher.id,
        )
        confidence = EvidenceConfidenceAssessment(
            organisation_id=organisation.id,
            study_id=study.id,
            focus="Synthetic deletion confidence record",
            supporting_response_ids_json=json.dumps([response.id]),
        )
        db.add_all((theme, converted_finding, reusable_finding, confidence))
        db.flush()
        theme_code = ResearchThemeCode(
            organisation_id=organisation.id,
            study_id=study.id,
            research_theme_id=theme.id,
            research_code_id=research_code.id,
            linked_by_id=researcher.id,
        )
        relationship = AnalyticalRelationship(
            organisation_id=organisation.id,
            study_id=study.id,
            source_type="finding",
            source_id=reusable_finding.id,
            relationship_type="supports",
            target_type="analysis_target",
            target_id=response_target.id,
            created_by_id=researcher.id,
        )
        canvas = AnalysisCanvas(
            organisation_id=organisation.id,
            study_id=study.id,
            owner_id=researcher.id,
        )
        db.add_all((theme_code, relationship, canvas))
        db.flush()
        target_node = AnalysisCanvasNode(
            organisation_id=organisation.id,
            study_id=study.id,
            canvas_id=canvas.id,
            object_type="analysis_target",
            object_id=response_target.id,
            x=10,
            y=10,
            added_by_id=researcher.id,
        )
        theme_node = AnalysisCanvasNode(
            organisation_id=organisation.id,
            study_id=study.id,
            canvas_id=canvas.id,
            object_type="theme",
            object_id=theme.id,
            x=20,
            y=20,
            added_by_id=researcher.id,
        )
        historical_request = ParticipantPrivacyRequest(
            organisation_id=organisation.id,
            participant_id=participant.id,
            study_id=study.id,
            request_type="withdrawal",
            scope="study",
            status="completed",
        )
        deletion_request = ParticipantPrivacyRequest(
            organisation_id=organisation.id,
            participant_id=participant.id,
            request_type="deletion",
            scope="account",
            status="received",
        )
        db.add_all((target_node, theme_node, historical_request, deletion_request))
        db.commit()

        ids = {
            "participant": participant.id,
            "unaffected_participant": unaffected_participant.id,
            "response": response.id,
            "unaffected_response": unaffected_response.id,
            "evidence": evidence.id,
            "invitation": invitation.id,
            "credential": credential.id,
            "session": session.id,
            "access_code": access_code.id,
            "message": message.id,
            "outbox": outbox.id,
            "response_target": response_target.id,
            "evidence_target": evidence_target.id,
            "participant_target": participant_target.id,
            "code_application": code_application.id,
            "annotation": annotation.id,
            "target_memo": target_memo.id,
            "response_memo": response_memo.id,
            "participant_memo": participant_memo.id,
            "study_memo": study_memo.id,
            "participant_suggestion": participant_suggestion.id,
            "unaffected_suggestion": unaffected_suggestion.id,
            "theme": theme.id,
            "theme_code": theme_code.id,
            "converted_finding": converted_finding.id,
            "reusable_finding": reusable_finding.id,
            "confidence": confidence.id,
            "relationship": relationship.id,
            "canvas": canvas.id,
            "target_node": target_node.id,
            "theme_node": theme_node.id,
            "research_code": research_code.id,
            "historical_request": historical_request.id,
            "deletion_request": deletion_request.id,
        }
        stored_name = evidence.stored_name

    storage = RecordingStorage()
    with SessionLocal() as db:
        request = db.get(ParticipantPrivacyRequest, ids["deletion_request"])
        assert request is not None
        revoke_participant_access(
            db,
            organisation_id=request.organisation_id,
            participant_id=ids["participant"],
            study_id=None,
        )
        db.commit()
        assert process_deletion_request(db, storage, request) is True

    assert storage.deleted == [stored_name]
    with SessionLocal() as db:
        request = db.get(ParticipantPrivacyRequest, ids["deletion_request"])
        historical = db.get(ParticipantPrivacyRequest, ids["historical_request"])
        assert request is not None
        assert request.status == "completed"
        assert request.participant_id is None
        assert request.retriable is False
        assert request.last_error_code == ""
        assert historical is not None and historical.participant_id is None

        for model, key in (
            (Participant, "participant"),
            (ActivityResponse, "response"),
            (EvidenceFile, "evidence"),
            (ParticipantInvitation, "invitation"),
            (ParticipantPasswordCredential, "credential"),
            (PublicAuthSession, "session"),
            (ParticipantAppAccessCode, "access_code"),
            (ParticipantMessage, "message"),
            (OutboxEmail, "outbox"),
            (AnalysisTarget, "response_target"),
            (AnalysisTarget, "evidence_target"),
            (AnalysisTarget, "participant_target"),
            (CodeApplication, "code_application"),
            (ResearchAnnotation, "annotation"),
            (ResearchMemo, "target_memo"),
            (ResearchMemo, "response_memo"),
            (ResearchMemo, "participant_memo"),
            (ResearchAnalysisSuggestion, "participant_suggestion"),
            (ResearchFinding, "converted_finding"),
            (EvidenceConfidenceAssessment, "confidence"),
            (AnalyticalRelationship, "relationship"),
            (AnalysisCanvasNode, "target_node"),
        ):
            assert db.get(model, ids[key]) is None

        assert db.get(Participant, ids["unaffected_participant"]) is not None
        assert db.get(ActivityResponse, ids["unaffected_response"]) is not None
        assert (
            db.get(ResearchAnalysisSuggestion, ids["unaffected_suggestion"])
            is not None
        )
        assert db.get(ResearchCode, ids["research_code"]) is not None
        assert db.get(ResearchMemo, ids["study_memo"]) is not None
        assert db.get(ResearchFinding, ids["reusable_finding"]) is not None
        assert db.get(AnalysisCanvas, ids["canvas"]) is not None
        assert db.get(AnalysisCanvasNode, ids["theme_node"]) is not None
        assert db.get(ResearchThemeCode, ids["theme_code"]) is not None
        theme = db.get(ResearchTheme, ids["theme"])
        assert theme is not None
        assert json.loads(theme.source_suggestion_ids_json) == [
            ids["unaffected_suggestion"]
        ]
