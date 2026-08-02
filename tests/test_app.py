import os
import json
from pathlib import Path
from tempfile import gettempdir
from uuid import uuid4

TEST_DATABASE_PATH = Path(gettempdir()) / f"pcip-test-{uuid4().hex}.db"
TEST_DATABASE_PATH.unlink(missing_ok=True)
os.environ['DATABASE_URL'] = f"sqlite:///{TEST_DATABASE_PATH}"

import re
from glob import glob
import pytest
from types import SimpleNamespace
from contextlib import contextmanager
from fastapi.testclient import TestClient
from app.main import app
from datetime import timedelta
from sqlalchemy import func, select

from app.config import settings
from app.db import SessionLocal
from app.models import User
from app.observability import configure_observability
from app.main import (
    InMemoryRateLimiter,
    activity_window,
    entra_identity_from_claims,
    now,
    rate_limiter,
)
from app.config import validate_runtime_settings

client = TestClient(app)


@pytest.fixture(scope='session', autouse=True)
def cleanup_test_database():
    yield
    from app.db import engine

    engine.dispose()
    TEST_DATABASE_PATH.unlink(missing_ok=True)


def csrf_token() -> str:
    page = client.get('/login')
    match = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert match is not None
    return match.group(1)


def post_with_csrf(path, data=None, files=None, follow_redirects=False):
    payload = dict(data or {})
    payload['csrf_token'] = csrf_token()
    return client.post(path, data=payload, files=files, follow_redirects=follow_redirects)


def unique_value(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


def login():
    return post_with_csrf('/login', data={'email': 'admin@politis.local', 'password': 'PolitisDemo!'}, follow_redirects=False)


def login_as(email: str, password: str):
    response = post_with_csrf('/login', data={'email': email, 'password': password}, follow_redirects=False)
    client.cookies.update(response.cookies)
    return response


def auth():
    r = login(); client.cookies.update(r.cookies); return r


def test_health_and_version():
    with client:
        data = client.get('/health').json()
        assert data['status'] == 'ok'
        assert data['version'] == '0.6.0'


def test_readiness_checks_database():
    with client:
        data = client.get('/health/ready')
        assert data.status_code == 200
        assert data.json()['status'] == 'ready'


def test_readiness_fails_without_exposing_database_error(monkeypatch):
    import app.main as main_module

    class UnavailableEngine:
        def connect(self):
            raise RuntimeError('sensitive database connection detail')

    with client:
        monkeypatch.setattr(main_module, 'engine', UnavailableEngine())
        response = client.get('/health/ready')
    assert response.status_code == 503
    assert response.json() == {'status': 'unavailable'}
    assert 'sensitive' not in response.text


def test_observability_is_disabled_without_connection_string():
    candidate = SimpleNamespace(
        applicationinsights_connection_string=None,
    )
    assert configure_observability(candidate) is False


def test_login_and_dashboard():
    with client:
        r = auth(); assert r.status_code == 303
        d = client.get('/')
        assert d.status_code == 200 and 'Seven-day town centre diary' in d.text


def test_global_user_can_hold_memberships_in_multiple_organisations():
    from app.models import Organisation, OrganisationMembership
    from app.security import decode_session, hash_password

    email = f"{unique_value('global-user')}@example.org"
    password = 'SecurePass123!'
    with client:
        client.cookies.clear()
        with SessionLocal() as db:
            existing_org = db.scalar(
                select(Organisation).order_by(Organisation.id)
            )
            second_org = Organisation(
                name=unique_value('Second organisation'),
                slug=unique_value('second-org').lower(),
            )
            db.add(second_org)
            db.flush()
            user = User(
                organisation_id=existing_org.id,
                name='Global User',
                email=email,
                password_hash=hash_password(password),
                role='researcher',
            )
            db.add(user)
            db.flush()
            db.add_all([
                OrganisationMembership(
                    user_id=user.id,
                    organisation_id=existing_org.id,
                    role='researcher',
                ),
                OrganisationMembership(
                    user_id=user.id,
                    organisation_id=second_org.id,
                    role='observer',
                ),
            ])
            db.commit()
            second_org_id = second_org.id
        response = login_as(email, password)
        assert response.status_code == 303
        assert response.headers['location'] == '/'
        assert client.cookies.get('session')
        switched = post_with_csrf(
            '/organisations/switch',
            data={'organisation_id': second_org_id},
            follow_redirects=False,
        )
        assert switched.status_code == 303
        identity = decode_session(client.cookies.get('session'))
        assert identity is not None
        assert identity.organisation_id == second_org_id
        dashboard = client.get('/')
        assert dashboard.status_code == 200
        assert 'Observer' in dashboard.text


def test_entra_identity_requires_configured_tenant_claim():
    original_tenant = settings.entra_tenant_id
    try:
        settings.entra_tenant_id = 'expected-tenant'
        common = {
            'sub': 'entra-subject',
            'preferred_username': 'researcher@example.org',
            'name': 'Researcher',
        }
        assert entra_identity_from_claims(common) is None
        assert entra_identity_from_claims(
            {**common, 'tid': 'different-tenant'}
        ) is None
        assert entra_identity_from_claims(
            {**common, 'tid': 'expected-tenant'}
        ) == (
            'entra-subject',
            'researcher@example.org',
            'Researcher',
        )
    finally:
        settings.entra_tenant_id = original_tenant


def test_activity_window_uses_study_start_and_offsets():
    start = now()
    study = SimpleNamespace(start_at=start)
    activity = SimpleNamespace(
        release_offset_days=1,
        due_offset_days=3,
    )
    assert activity_window(
        study,
        activity,
        start + timedelta(hours=12),
    )['status'] == 'upcoming'
    assert activity_window(
        study,
        activity,
        start + timedelta(days=2),
    )['status'] == 'open'
    assert activity_window(
        study,
        activity,
        start + timedelta(days=4),
    )['status'] == 'closed'
    assert activity_window(
        SimpleNamespace(start_at=None),
        activity,
        start,
    )['status'] == 'open'


def test_project_and_study_creation():
    with client:
        auth()
        p = post_with_csrf('/projects', data={'title': 'Access Study', 'code': 'ACC-001', 'description': 'Test', 'status_value': 'live'}, follow_redirects=False)
        assert p.status_code == 303
        page = client.get('/projects'); assert 'Access Study' in page.text
        project_id = int(page.text.split('/projects/')[1].split('"')[0])
        s = post_with_csrf(f'/projects/{project_id}/studies', data={'title': 'Access diary', 'code': 'ACC-D01', 'description': 'Diary', 'methodology': 'diary', 'status_value': 'recruiting'}, follow_redirects=False)
        assert s.status_code == 303
        detail = client.get(s.headers['location'])
        assert 'Access diary' in detail.text


def test_first_project_wizard_creates_project_and_study():
    with client:
        auth()
        wizard_page = client.get('/onboarding/first-project')
        assert wizard_page.status_code == 200
        assert 'Launch your first pilot project' in wizard_page.text

        project_code = unique_value('WIZ').upper().replace('_', '-')
        study_code = unique_value('WST').upper().replace('_', '-')
        submit = post_with_csrf(
            '/onboarding/first-project',
            data={
                'project_title': 'Wizard Test Project',
                'project_code': project_code,
                'project_description': 'Created through onboarding wizard.',
                'project_status': 'live',
                'study_title': 'Wizard Test Study',
                'study_code': study_code,
                'study_description': 'Created through onboarding wizard.',
                'study_methodology': 'mixed_method',
                'study_status': 'recruiting',
                'add_starter_activity': 'true',
            },
            follow_redirects=False,
        )
        assert submit.status_code == 303
        detail = client.get(submit.headers['location'])
        assert 'Wizard Test Study' in detail.text
        assert 'Welcome activity' in detail.text


def test_generate_pilot_sample_data_endpoint_is_idempotent():
    with client:
        auth()
        first = post_with_csrf('/pilot/sample-data', follow_redirects=False)
        assert first.status_code == 303
        dashboard = client.get('/')
        assert 'Sample pilot data' in dashboard.text

        second = post_with_csrf('/pilot/sample-data', follow_redirects=False)
        assert second.status_code == 303

        participants_page = client.get('/participants')
        assert 'PILOT-P01' in participants_page.text
        assert 'PILOT-P02' in participants_page.text


def test_participant_enrolment_activity_and_invitation():
    with client:
        auth()
        p = post_with_csrf('/participants', data={'reference': 'P-101', 'name': 'Alex Participant', 'email': 'alex.participant@example.org', 'phone': '', 'status_value': 'prospective', 'consent_status': 'pending', 'communication_preference': 'email', 'tags': 'ward 1', 'notes': ''}, follow_redirects=False)
        assert p.status_code == 303
        participant_id = int(p.headers['location'].rsplit('/', 1)[-1])
        studies = client.get('/studies')
        study_id = int(studies.text.split('/studies/')[1].split('"')[0])
        e = post_with_csrf(f'/studies/{study_id}/enrol', data={'participant_id': participant_id}, follow_redirects=False)
        assert e.status_code == 303
        a = post_with_csrf(f'/studies/{study_id}/activities', data={'title': 'Rate the visit', 'prompt': 'How was it?', 'activity_type': 'rating', 'options': '', 'required': 'true', 'release_offset_days': '1', 'due_offset_days': '3'}, follow_redirects=False)
        assert a.status_code == 303
        invite = post_with_csrf(f'/studies/{study_id}/invite/{participant_id}', follow_redirects=False)
        assert invite.status_code == 303
        outbox = client.get('/outbox')
        assert 'alex.participant@example.org' in outbox.text and 'Invitation:' in outbox.text


def test_researcher_invite_and_admin_pages():
    with client:
        auth()
        p = post_with_csrf('/researchers/invite', data={'name': 'Alex Researcher', 'email': 'alex.researcher@example.org', 'role': 'researcher'}, follow_redirects=False)
        assert p.status_code == 303
        for path in ['/projects', '/studies', '/participants', '/researchers', '/audit', '/outbox']:
            page = client.get(path)
            assert page.status_code == 200, (path, page.text)

def test_participant_accepts_invitation():
    from app.db import SessionLocal
    from app.models import OutboxEmail
    from sqlalchemy import select
    with client:
        auth()
        p = post_with_csrf('/participants', data={'reference': 'P-202', 'name': 'Jamie Resident', 'email': 'jamie@example.org', 'phone': '', 'status_value': 'prospective', 'consent_status': 'pending', 'communication_preference': 'email', 'tags': '', 'notes': ''}, follow_redirects=False)
        participant_id = int(p.headers['location'].rsplit('/', 1)[-1])
        studies = client.get('/studies')
        study_id = int(studies.text.split('/studies/')[1].split('"')[0])
        post_with_csrf(f'/studies/{study_id}/enrol', data={'participant_id': participant_id}, follow_redirects=False)
        post_with_csrf(f'/studies/{study_id}/invite/{participant_id}', follow_redirects=False)
        with SessionLocal() as db:
            email = db.scalar(select(OutboxEmail).where(OutboxEmail.recipient == 'jamie@example.org').order_by(OutboxEmail.id.desc()))
            token = email.body.split('token=')[1].strip()
        page = client.get(f'/join-study?token={token}')
        assert page.status_code == 200 and 'Research invitation' in page.text
        accepted = post_with_csrf('/join-study', data={'consent': 'true'}, follow_redirects=True)
        assert accepted.status_code == 200 and "You're enrolled" in accepted.text


def _prepare_participant_api_portal_context(consent: bool = True, email_suffix: str = 'portal-summary'):
    invitation_token, participant_id, study_id = _create_participant_invitation_for_api(email_suffix)

    if consent:
        with client:
            landing = client.get(f'/join-study?token={invitation_token}', follow_redirects=False)
            assert landing.status_code == 303
            accepted = post_with_csrf('/join-study', data={'consent': 'true'}, follow_redirects=False)
            assert accepted.status_code == 303

    with client:
        exchange = _exchange_participant_api_session(invitation_token)
        assert exchange.status_code == 200
        api_token = exchange.json()['session']['access_token']

    return api_token, participant_id, study_id, invitation_token


def test_participant_api_portal_summary_requires_participant_session():
    with client:
        client.cookies.clear()
        response = client.get('/api/v1/participant/portal', follow_redirects=False)
        assert response.status_code == 401
        assert response.headers.get('www-authenticate') == 'Bearer'


def test_participant_api_portal_summary_cookie_only_session_does_not_authenticate_mobile_api():
    _api_token, _participant_id, _study_id, invitation_token = _prepare_participant_api_portal_context(
        consent=True,
        email_suffix='portal-summary-cookie-only',
    )

    with client:
        landing = client.get(f'/join-study?token={invitation_token}', follow_redirects=False)
        assert landing.status_code == 303

        cookie_only = client.get('/api/v1/participant/portal', follow_redirects=False)
        assert cookie_only.status_code == 401
        assert cookie_only.headers.get('www-authenticate') == 'Bearer'


def test_participant_api_portal_summary_missing_bearer_with_html_accept_returns_json_challenge_without_csrf_cookie():
    with client:
        response = client.get(
            '/api/v1/participant/portal',
            headers={'Accept': 'text/html'},
            follow_redirects=False,
        )
        assert response.status_code == 401
        assert response.headers.get('www-authenticate') == 'Bearer'
        assert response.headers.get('content-type', '').startswith('application/json')
        assert response.json() == {'detail': 'Invalid or expired participant API credentials.'}
        assert 'csrf_session=' not in (response.headers.get('set-cookie') or '')


def test_participant_api_portal_summary_rejects_unaccepted_invitation_session():
    api_token, _participant_id, _study_id, _invitation_token = _prepare_participant_api_portal_context(
        consent=False,
        email_suffix='portal-summary-unaccepted',
    )

    with client:
        response = client.get(
            '/api/v1/participant/portal',
            headers={'Authorization': f'Bearer {api_token}'},
            follow_redirects=False,
        )
        assert response.status_code == 403


def test_participant_api_portal_summary_returns_contract_shaped_payload_for_accepted_participant():
    from app.models import Activity

    api_token, participant_id, study_id, invitation_token = _prepare_participant_api_portal_context(
        consent=True,
        email_suffix='portal-summary-accepted',
    )

    with SessionLocal() as db:
        first_activity = db.scalar(
            select(Activity)
            .where(Activity.study_id == study_id)
            .order_by(Activity.position.asc(), Activity.id.asc())
        )
        assert first_activity is not None
        activity_id = first_activity.id
        unanswered_activity = Activity(
            organisation_id=first_activity.organisation_id,
            study_id=study_id,
            title='Unanswered portal activity',
            prompt='Please answer later',
            activity_type='long_text',
            required=True,
            position=(first_activity.position or 1) + 100,
            release_offset_days=0,
            due_offset_days=None,
        )
        db.add(unanswered_activity)
        db.commit()
        unanswered_activity_id = unanswered_activity.id

    with client:
        # Keep portal cookie session for existing write routes while asserting API bearer auth.
        landing = client.get(f'/join-study?token={invitation_token}', follow_redirects=False)
        assert landing.status_code == 303
        accepted = post_with_csrf('/join-study', data={'consent': 'true'}, follow_redirects=False)
        assert accepted.status_code == 303

        draft = post_with_csrf(
            f'/participant-portal/activity/{activity_id}',
            data={'action': 'draft', 'answer': 'draft from portal summary test'},
            follow_redirects=False,
        )
        assert draft.status_code == 303

        sent = post_with_csrf(
            '/participant-portal/message',
            data={'body': 'Hello from portal summary test'},
            follow_redirects=False,
        )
        assert sent.status_code == 303

        summary = client.get(
            '/api/v1/participant/portal',
            headers={'Authorization': f'Bearer {api_token}'},
            follow_redirects=False,
        )
        assert summary.status_code == 200
        assert summary.headers.get('cache-control') == 'no-store'
        body = summary.json()

        assert set(body.keys()) == {'study', 'participant', 'activities', 'responses', 'messages'}
        assert body['study']['study_id'] == study_id
        assert body['participant']['participant_id'] == participant_id

        activity_ids = {item['activity_id'] for item in body['activities']}
        assert activity_id in activity_ids
        assert unanswered_activity_id in activity_ids

        by_activity_id = {item['activity_id']: item for item in body['activities']}
        assert 'response' in by_activity_id[activity_id]
        assert by_activity_id[activity_id]['response']['status'] == 'draft'
        assert 'response' not in by_activity_id[unanswered_activity_id]

        response_entries = {item['activity_id']: item for item in body['responses']}
        assert activity_id in response_entries
        assert unanswered_activity_id not in response_entries
        assert response_entries[activity_id]['status'] == 'draft'
        assert response_entries[activity_id]['value']['answer'] == 'draft from portal summary test'

        assert body['messages']
        assert body['messages'][-1]['sender_type'] == 'participant'
        assert 'Hello from portal summary test' in body['messages'][-1]['body']

        scoped = client.get(
            f'/api/v1/participant/portal?study_id={study_id}',
            headers={'Authorization': f'Bearer {api_token}'},
            follow_redirects=False,
        )
        assert scoped.status_code == 200

        out_of_scope = client.get(
            f'/api/v1/participant/portal?study_id={study_id + 9999}',
            headers={'Authorization': f'Bearer {api_token}'},
            follow_redirects=False,
        )
        assert out_of_scope.status_code == 403


def test_participant_api_portal_summary_rejects_withdrawn_consent_after_historical_acceptance():
    from app.models import Participant

    api_token, participant_id, _study_id, _invitation_token = _prepare_participant_api_portal_context(
        consent=True,
        email_suffix='portal-summary-consent-withdrawn',
    )

    with SessionLocal() as db:
        participant_row = db.get(Participant, participant_id)
        assert participant_row is not None
        participant_row.consent_status = 'withdrawn'
        db.commit()

    with client:
        denied = client.get(
            '/api/v1/participant/portal',
            headers={'Authorization': f'Bearer {api_token}'},
            follow_redirects=False,
        )
        assert denied.status_code == 403
        assert denied.headers.get('cache-control') != 'no-store'
        assert denied.json() == {'detail': 'Participant consent is no longer active.'}
        assert set(denied.json().keys()) == {'detail'}


def test_participant_api_portal_summary_rejects_missing_enrolment_after_session_issued():
    from app.models import StudyEnrolment

    api_token, participant_id, study_id, _invitation_token = _prepare_participant_api_portal_context(
        consent=True,
        email_suffix='portal-summary-no-enrolment',
    )

    with SessionLocal() as db:
        enrolment = db.scalar(
            select(StudyEnrolment).where(
                StudyEnrolment.study_id == study_id,
                StudyEnrolment.participant_id == participant_id,
            )
        )
        assert enrolment is not None
        db.delete(enrolment)
        db.commit()

    with client:
        denied = client.get(
            '/api/v1/participant/portal',
            headers={'Authorization': f'Bearer {api_token}'},
            follow_redirects=False,
        )
        assert denied.status_code == 403
        assert denied.json() == {'detail': 'Participant is not enrolled in this study.'}
        assert set(denied.json().keys()) == {'detail'}


def test_password_reset_token_is_exchanged_and_replay_is_blocked():
    from app.models import OutboxEmail
    with client:
        client.cookies.clear()
        issued = post_with_csrf('/forgot-password', data={'email': 'admin@politis.local'}, follow_redirects=False)
        assert issued.status_code == 200
        with SessionLocal() as db:
            email = db.scalar(
                select(OutboxEmail)
                .where(OutboxEmail.recipient == 'admin@politis.local')
                .order_by(OutboxEmail.id.desc())
            )
            assert email is not None
            token = email.body.split('token=')[1].strip()

        exchanged = client.get(f'/reset-password?token={token}', follow_redirects=False)
        assert exchanged.status_code == 303
        assert exchanged.headers['location'] == '/reset-password'

        clean_page = client.get('/reset-password')
        assert clean_page.status_code == 200
        assert 'Create a new password' in clean_page.text
        assert 'name="token"' not in clean_page.text

        client.cookies.clear()
        replay = client.get(f'/reset-password?token={token}', follow_redirects=True)
        assert replay.status_code == 200
        assert 'invalid or expired' in replay.text


def test_participant_invitation_token_can_create_a_fresh_session_until_revoked():
    from app.models import OutboxEmail, ParticipantInvitation
    from app.security import token_hash
    with client:
        client.cookies.clear()
        auth()
        p = post_with_csrf('/participants', data={'reference': 'P-EX1', 'name': 'Replay Protected', 'email': 'portal.replay@example.org', 'phone': '', 'status_value': 'prospective', 'consent_status': 'pending', 'communication_preference': 'email', 'tags': '', 'notes': ''}, follow_redirects=False)
        participant_id = int(p.headers['location'].rsplit('/', 1)[-1])
        studies = client.get('/studies')
        study_id = int(studies.text.split('/studies/')[1].split('"')[0])
        post_with_csrf(f'/studies/{study_id}/enrol', data={'participant_id': participant_id}, follow_redirects=False)
        post_with_csrf(f'/studies/{study_id}/invite/{participant_id}', follow_redirects=False)
        with SessionLocal() as db:
            email = db.scalar(
                select(OutboxEmail)
                .where(OutboxEmail.recipient == 'portal.replay@example.org')
                .order_by(OutboxEmail.id.desc())
            )
            assert email is not None
            token = email.body.split('token=')[1].strip()

        exchanged = client.get(f'/join-study?token={token}', follow_redirects=False)
        assert exchanged.status_code == 303
        assert exchanged.headers['location'] == '/join-study'

        clean_page = client.get('/join-study')
        assert clean_page.status_code == 200
        assert 'Research invitation' in clean_page.text
        assert 'name="token"' not in clean_page.text

        client.cookies.clear()
        reopened = client.get(f'/join-study?token={token}', follow_redirects=False)
        assert reopened.status_code == 303
        assert reopened.headers['location'] == '/join-study'
        assert client.get('/join-study').status_code == 200

        with SessionLocal() as db:
            invitation = db.scalar(
                select(ParticipantInvitation)
                .where(ParticipantInvitation.token_hash == token_hash(token))
            )
            invitation.revoked_at = now()
            db.commit()

        client.cookies.clear()
        revoked = client.get(f'/join-study?token={token}', follow_redirects=True)
        assert revoked.status_code == 200
        assert 'Invitation unavailable' in revoked.text


def test_researcher_invitation_token_is_exchanged_and_replay_is_blocked():
    from app.models import OutboxEmail
    with client:
        client.cookies.clear()
        auth()
        invite = post_with_csrf('/researchers/invite', data={'name': 'Replay Researcher', 'email': 'invite.replay@example.org', 'role': 'researcher'}, follow_redirects=False)
        assert invite.status_code == 303
        with SessionLocal() as db:
            email = db.scalar(
                select(OutboxEmail)
                .where(OutboxEmail.recipient == 'invite.replay@example.org')
                .order_by(OutboxEmail.id.desc())
            )
            assert email is not None
            token = email.body.split('token=')[1].strip()

        exchanged = client.get(f'/accept-invitation?token={token}', follow_redirects=False)
        assert exchanged.status_code == 303
        assert exchanged.headers['location'] == '/accept-invitation'

        clean_page = client.get('/accept-invitation')
        assert clean_page.status_code == 200
        assert 'Activate your researcher account' in clean_page.text
        assert 'name="token"' not in clean_page.text

        client.cookies.clear()
        replay = client.get(f'/accept-invitation?token={token}', follow_redirects=True)
        assert replay.status_code == 200
        assert 'Invitation unavailable' in replay.text


def test_existing_global_identity_can_accept_second_organisation_membership():
    from app.models import (
        Organisation,
        OrganisationMembership,
        OutboxEmail,
    )
    from app.security import hash_password

    existing_email = f"{unique_value('existing-global')}@example.org"
    existing_password = 'SecurePass123!'
    with client:
        client.cookies.clear()
        auth()
        with SessionLocal() as db:
            owner = db.scalar(
                select(User).where(User.email == 'admin@politis.local')
            )
            second_org = Organisation(
                name=unique_value('Membership organisation'),
                slug=unique_value('membership-org').lower(),
            )
            db.add(second_org)
            db.flush()
            db.add(
                OrganisationMembership(
                    user_id=owner.id,
                    organisation_id=second_org.id,
                    role='owner',
                )
            )
            existing = User(
                organisation_id=owner.organisation_id,
                name='Existing Global User',
                email=existing_email,
                password_hash=hash_password(existing_password),
                role='researcher',
            )
            db.add(existing)
            db.flush()
            db.add(
                OrganisationMembership(
                    user_id=existing.id,
                    organisation_id=owner.organisation_id,
                    role='researcher',
                )
            )
            db.commit()
            second_org_id = second_org.id
            existing_id = existing.id

        switched = post_with_csrf(
            '/organisations/switch',
            data={'organisation_id': second_org_id},
            follow_redirects=False,
        )
        assert switched.status_code == 303
        invited = post_with_csrf(
            '/researchers/invite',
            data={
                'name': 'Existing Global User',
                'email': existing_email,
                'role': 'observer',
            },
            follow_redirects=False,
        )
        assert invited.status_code == 303
        with SessionLocal() as db:
            email = db.scalar(
                select(OutboxEmail)
                .where(OutboxEmail.recipient == existing_email)
                .order_by(OutboxEmail.id.desc())
            )
            token = email.body.split('token=')[1].strip()

        exchanged = client.get(
            f'/accept-invitation?token={token}',
            follow_redirects=True,
        )
        assert exchanged.status_code == 200
        assert 'Existing account password' in exchanged.text
        accepted = post_with_csrf(
            '/accept-invitation',
            data={'password': existing_password},
            follow_redirects=False,
        )
        assert accepted.status_code == 303
        with SessionLocal() as db:
            membership = db.scalar(
                select(OrganisationMembership).where(
                    OrganisationMembership.user_id == existing_id,
                    OrganisationMembership.organisation_id == second_org_id,
                )
            )
            assert membership is not None
            assert membership.role == 'observer'


def test_invalid_status_and_activity_validation():
    with client:
        auth()
        r = post_with_csrf('/projects', data={'title':'Invalid','code':'BAD-1','status_value':'nonsense'})
        assert r.status_code == 400
        from app.db import SessionLocal
        from app.models import Project
        from sqlalchemy import select
        with SessionLocal() as db:
            project_id = db.scalar(select(Project.id).order_by(Project.id.asc()))
        study = post_with_csrf(f'/projects/{project_id}/studies', data={'title':'Validation study','code':'VAL-1','methodology':'diary','status_value':'draft'}, follow_redirects=False)
        assert study.status_code == 303
        study_id = int(study.headers['location'].split('/')[-1])
        r = post_with_csrf(f'/studies/{study_id}/activities', data={'title':'Bad choice','activity_type':'single_choice','options':'Only one','release_offset_days':'0','due_offset_days':'0','required':'true'})
        assert r.status_code == 400
        invalid_methodology = post_with_csrf(
            f'/studies/{study_id}/edit',
            data={'title':'Validation study','methodology':'unsupported','status_value':'draft'},
        )
        assert invalid_methodology.status_code == 400
        valid_activity = post_with_csrf(
            f'/studies/{study_id}/activities',
            data={'title':'Valid activity','activity_type':'long_text','release_offset_days':'0','due_offset_days':'2'},
            follow_redirects=False,
        )
        assert valid_activity.status_code == 303
        from app.models import Activity
        with SessionLocal() as db:
            activity_id = db.scalar(select(Activity.id).where(Activity.study_id == study_id))
        invalid_activity_edit = post_with_csrf(
            f'/activities/{activity_id}/edit',
            data={'title':'Changed','activity_type':'unsupported','release_offset_days':'0','due_offset_days':'2'},
        )
        assert invalid_activity_edit.status_code == 400
        invalid_participant = post_with_csrf(
            '/participants',
            data={
                'reference':'BAD-COMMS',
                'name':'Invalid Comms',
                'status_value':'prospective',
                'consent_status':'pending',
                'communication_preference':'carrier_pigeon',
            },
        )
        assert invalid_participant.status_code == 400


def test_navigation_active_state_and_mobile_safe_markup():
    with client:
        auth()
        html = client.get('/projects').text
        assert 'class="active" href="/projects"' in html
        assert 'aria-label="Primary navigation"' in html


def test_participant_portal_draft_submit_and_message(monkeypatch):
    from io import BytesIO
    import app.main as main_module
    from app.db import SessionLocal
    from app.models import Activity, ActivityResponse, EvidenceFile, OutboxEmail, ParticipantMessage, Study
    from sqlalchemy import select
    with client:
        auth()
        p = post_with_csrf('/participants', data={'reference':'P-303','name':'Portal User','email':'portal@example.org','phone':'','status_value':'prospective','consent_status':'pending','communication_preference':'email','tags':'','notes':''}, follow_redirects=False)
        participant_id = int(p.headers['location'].rsplit('/',1)[-1])
        with SessionLocal() as db:
            first_activity=db.scalar(select(Activity).order_by(Activity.id.asc()))
            study_id=first_activity.study_id
            activity_id=first_activity.id
        post_with_csrf(f'/studies/{study_id}/enrol', data={'participant_id':participant_id})
        post_with_csrf(f'/studies/{study_id}/invite/{participant_id}')
        with SessionLocal() as db:
            email=db.scalar(select(OutboxEmail).where(OutboxEmail.recipient=='portal@example.org').order_by(OutboxEmail.id.desc()))
            token=email.body.split('token=')[1].strip()
        client.get(f'/join-study?token={token}')
        post_with_csrf('/join-study', data={'consent':'true'})
        with SessionLocal() as db:
            study_row = db.get(Study, study_id)
            study_row.start_at = now() + timedelta(days=1)
            db.commit()
        upcoming_portal = client.get('/participant-portal')
        assert upcoming_portal.status_code == 200
        assert 'will be available from' in upcoming_portal.text
        blocked = post_with_csrf(
            f'/participant-portal/activity/{activity_id}',
            data={'action':'draft','answer':'too early'},
            follow_redirects=False,
        )
        assert blocked.status_code == 409
        with SessionLocal() as db:
            study_row = db.get(Study, study_id)
            study_row.start_at = None
            db.commit()
        portal=client.get('/participant-portal')
        assert portal.status_code==200 and 'Your activities' in portal.text
        evidence_files_before = set(Path(settings.local_storage_path).glob('*'))

        def fail_activity_audit(*_args, **_kwargs):
            raise RuntimeError('simulated database workflow failure')

        with monkeypatch.context() as patch:
            patch.setattr(main_module, 'audit', fail_activity_audit)
            with pytest.raises(RuntimeError, match='simulated database workflow failure'):
                post_with_csrf(
                    f'/participant-portal/activity/{activity_id}',
                    data={'action':'draft','answer':''},
                    files={'upload':('cleanup.txt',BytesIO(b'ordinary evidence'),'text/plain')},
                    follow_redirects=False,
                )
        assert set(Path(settings.local_storage_path).glob('*')) == evidence_files_before
        with SessionLocal() as db:
            assert db.scalar(select(EvidenceFile).where(EvidenceFile.participant_id == participant_id, EvidenceFile.activity_id == activity_id)) is None
            assert db.scalar(select(ActivityResponse).where(ActivityResponse.participant_id == participant_id, ActivityResponse.activity_id == activity_id)) is None

        infected = post_with_csrf(
            f'/participant-portal/activity/{activity_id}',
            data={'action':'draft','answer':''},
            files={'upload':('unsafe.txt',BytesIO(b'EICAR-STANDARD-ANTIVIRUS-TEST-FILE'),'text/plain')},
            follow_redirects=False,
        )
        assert infected.status_code == 400
        with SessionLocal() as db:
            assert db.scalar(select(EvidenceFile).where(EvidenceFile.participant_id == participant_id, EvidenceFile.activity_id == activity_id)) is None
            assert db.scalar(select(ActivityResponse).where(ActivityResponse.participant_id == participant_id, ActivityResponse.activity_id == activity_id)) is None
        draft=post_with_csrf(f'/participant-portal/activity/{activity_id}', data={'action':'draft','answer':'draft answer'}, follow_redirects=False)
        assert draft.status_code==303
        submit=post_with_csrf(f'/participant-portal/activity/{activity_id}', data={'action':'submit','answer':'final answer'}, follow_redirects=False)
        assert submit.status_code==303
        msg=post_with_csrf('/participant-portal/message', data={'body':'Hello research team'}, follow_redirects=False)
        assert msg.status_code==303
        with SessionLocal() as db:
            response=db.scalar(select(ActivityResponse).where(ActivityResponse.participant_id==participant_id,ActivityResponse.activity_id==activity_id))
            assert response.status=='submitted' and 'final answer' in response.value_json
            assert db.scalar(select(ParticipantMessage).where(ParticipantMessage.participant_id==participant_id)) is not None


def test_bulk_import_editing_and_password_reset_request():
    from io import BytesIO
    with client:
        auth()
        csv_data=b'reference,name,email,phone,tags\nB-1,Bulk Person,bulk@example.org,,ward 2\n'
        r=post_with_csrf('/participants/import', files={'file':('participants.csv',BytesIO(csv_data),'text/csv')}, follow_redirects=False)
        assert r.status_code==303
        page=client.get('/participants?q=Bulk')
        assert 'Bulk Person' in page.text
        reset=post_with_csrf('/forgot-password', data={'email':'admin@politis.local'})
        assert reset.status_code==200 and 'reset link has been issued' in reset.text


def test_bulk_import_rejects_invalid_email_and_oversized_file(monkeypatch):
    from io import BytesIO
    import app.main as main_module

    with client:
        auth()
        invalid_email = b'reference,name,email\nCSV-BAD-1,Bad Email,not-an-email\n'
        response = post_with_csrf(
            '/participants/import',
            files={'file':('participants.csv',BytesIO(invalid_email),'text/csv')},
        )
        assert response.status_code == 400

        monkeypatch.setattr(main_module, 'MAX_CSV_IMPORT_BYTES', 32)
        oversized = b'reference,name\nCSV-BIG-1,' + (b'x' * 64) + b'\n'
        response = post_with_csrf(
            '/participants/import',
            files={'file':('participants.csv',BytesIO(oversized),'text/csv')},
        )
        assert response.status_code == 413


def test_admin_can_export_participant_data_and_audit_event():
    from app.models import AuditEvent
    with client:
        client.cookies.clear()
        auth()
        created = post_with_csrf(
            '/participants',
            data={
                'reference': 'PRIV-EXP-1',
                'name': 'Privacy Export',
                'email': 'privacy.export@example.org',
                'phone': '',
                'status_value': 'prospective',
                'consent_status': 'pending',
                'communication_preference': 'email',
                'tags': 'gdpr',
                'notes': 'export me',
            },
            follow_redirects=False,
        )
        participant_id = int(created.headers['location'].rsplit('/', 1)[-1])

        export = client.get(f'/participants/{participant_id}/export')
        assert export.status_code == 200
        assert export.headers.get('content-disposition', '').startswith('attachment;')
        payload = export.json()
        assert payload['participant']['id'] == participant_id
        assert payload['participant']['email'] == 'privacy.export@example.org'

        with SessionLocal() as db:
            event = db.scalar(
                select(AuditEvent)
                .where(AuditEvent.action == 'privacy.participant_exported', AuditEvent.entity_id == str(participant_id))
                .order_by(AuditEvent.id.desc())
            )
            assert event is not None


def test_researcher_is_blocked_from_admin_privacy_functions():
    from app.models import User
    from app.security import hash_password
    with client:
        client.cookies.clear()
        auth()
        participant = post_with_csrf(
            '/participants',
            data={
                'reference': 'PRIV-BLOCK-1',
                'name': 'Privacy Block',
                'email': 'privacy.block@example.org',
                'phone': '',
                'status_value': 'prospective',
                'consent_status': 'pending',
                'communication_preference': 'email',
                'tags': '',
                'notes': '',
            },
            follow_redirects=False,
        )
        participant_id = int(participant.headers['location'].rsplit('/', 1)[-1])

        researcher_email = f"{unique_value('privacy-researcher')}@example.org"
        researcher_password = 'SecurePass123!'
        with SessionLocal() as db:
            owner = db.scalar(select(User).where(User.email == 'admin@politis.local'))
            db.add(User(organisation_id=owner.organisation_id, name='Privacy Researcher', email=researcher_email, password_hash=hash_password(researcher_password), role='researcher'))
            db.commit()

        client.cookies.clear()
        login_response = login_as(researcher_email, researcher_password)
        assert login_response.status_code == 303

        assert client.get(f'/participants/{participant_id}/export').status_code == 403
        assert post_with_csrf(f'/participants/{participant_id}/privacy/delete-request', follow_redirects=False).status_code == 403
        assert post_with_csrf('/privacy/retention/apply', follow_redirects=False).status_code == 403


def test_privacy_deletion_workflow_hard_deletes_without_related_records():
    from app.models import AuditEvent, Participant
    with client:
        client.cookies.clear()
        auth()
        created = post_with_csrf(
            '/participants',
            data={
                'reference': 'PRIV-DEL-1',
                'name': 'Delete Candidate',
                'email': 'delete.candidate@example.org',
                'phone': '',
                'status_value': 'prospective',
                'consent_status': 'pending',
                'communication_preference': 'email',
                'tags': '',
                'notes': '',
            },
            follow_redirects=False,
        )
        participant_id = int(created.headers['location'].rsplit('/', 1)[-1])

        start = post_with_csrf(f'/participants/{participant_id}/privacy/delete-request', follow_redirects=False)
        assert start.status_code == 303

        detail = client.get(f'/participants/{participant_id}')
        token_match = re.search(r'name="workflow_token" value="([^"]+)"', detail.text)
        assert token_match is not None
        workflow_token = token_match.group(1)

        execute = post_with_csrf(
            f'/participants/{participant_id}/privacy/delete-execute',
            data={'workflow_token': workflow_token, 'mode': 'delete'},
            follow_redirects=False,
        )
        assert execute.status_code == 303
        assert execute.headers['location'] == '/participants'

        with SessionLocal() as db:
            row = db.get(Participant, participant_id)
            assert row is None
            event = db.scalar(
                select(AuditEvent)
                .where(AuditEvent.action == 'privacy.participant_deleted', AuditEvent.entity_id == str(participant_id))
                .order_by(AuditEvent.id.desc())
            )
            assert event is not None


def test_privacy_deletion_workflow_anonymises_when_related_records_exist():
    from app.models import AuditEvent, Participant
    with client:
        client.cookies.clear()
        auth()
        created = post_with_csrf(
            '/participants',
            data={
                'reference': 'PRIV-ANON-1',
                'name': 'Anon Candidate',
                'email': 'anon.candidate@example.org',
                'phone': '',
                'status_value': 'prospective',
                'consent_status': 'pending',
                'communication_preference': 'email',
                'tags': '',
                'notes': 'sensitive',
            },
            follow_redirects=False,
        )
        participant_id = int(created.headers['location'].rsplit('/', 1)[-1])
        studies = client.get('/studies')
        study_id = int(studies.text.split('/studies/')[1].split('"')[0])
        post_with_csrf(f'/studies/{study_id}/enrol', data={'participant_id': participant_id}, follow_redirects=False)

        post_with_csrf(f'/participants/{participant_id}/privacy/delete-request', follow_redirects=False)
        detail = client.get(f'/participants/{participant_id}')
        token_match = re.search(r'name="workflow_token" value="([^"]+)"', detail.text)
        assert token_match is not None
        workflow_token = token_match.group(1)

        execute = post_with_csrf(
            f'/participants/{participant_id}/privacy/delete-execute',
            data={'workflow_token': workflow_token, 'mode': 'auto'},
            follow_redirects=False,
        )
        assert execute.status_code == 303

        with SessionLocal() as db:
            row = db.get(Participant, participant_id)
            assert row is not None
            assert row.email is None
            assert row.phone is None
            assert row.name.startswith('Anonymised Participant')
            assert row.reference.startswith('ANON-')
            event = db.scalar(
                select(AuditEvent)
                .where(AuditEvent.action == 'privacy.participant_anonymised', AuditEvent.entity_id == str(participant_id))
                .order_by(AuditEvent.id.desc())
            )
            assert event is not None


def test_privacy_retention_apply_processes_configured_participants_and_audits():
    from app.models import AuditEvent, Participant
    original_days = settings.privacy_retention_days
    original_statuses = settings.privacy_retention_statuses
    original_action = settings.privacy_retention_action
    try:
        settings.privacy_retention_days = 1
        settings.privacy_retention_statuses = 'withdrawn'
        settings.privacy_retention_action = 'anonymise'

        with client:
            client.cookies.clear()
            auth()
            created = post_with_csrf(
                '/participants',
                data={
                    'reference': 'PRIV-RET-1',
                    'name': 'Retention Candidate',
                    'email': 'retention.candidate@example.org',
                    'phone': '',
                    'status_value': 'withdrawn',
                    'consent_status': 'withdrawn',
                    'communication_preference': 'email',
                    'tags': '',
                    'notes': '',
                },
                follow_redirects=False,
            )
            participant_id = int(created.headers['location'].rsplit('/', 1)[-1])

            with SessionLocal() as db:
                row = db.get(Participant, participant_id)
                row.created_at = now() - timedelta(days=30)
                db.commit()

            apply_result = post_with_csrf('/privacy/retention/apply', follow_redirects=False)
            assert apply_result.status_code == 303

            with SessionLocal() as db:
                refreshed = db.get(Participant, participant_id)
                assert refreshed is not None
                assert refreshed.name.startswith('Anonymised Participant')
                summary = db.scalar(
                    select(AuditEvent)
                    .where(AuditEvent.action == 'privacy.retention_applied')
                    .order_by(AuditEvent.id.desc())
                )
                assert summary is not None
                assert '"processed":' in summary.detail
    finally:
        settings.privacy_retention_days = original_days
        settings.privacy_retention_statuses = original_statuses
        settings.privacy_retention_action = original_action


def test_study_and_project_edit_forms_render():
    with client:
        auth()
        projects=client.get('/projects')
        project_id=int(projects.text.split('/projects/')[1].split('"')[0])
        detail=client.get(f'/projects/{project_id}')
        assert '/edit' in detail.text and 'Edit project' in detail.text
        studies=client.get('/studies')
        study_id=int(studies.text.split('/studies/')[1].split('"')[0])
        study=client.get(f'/studies/{study_id}')
        assert 'Edit study settings' in study.text and 'Activity builder' in study.text


def test_enterprise_security_headers_and_access_interface():
    with client:
        auth()
        page = client.get('/studies')
        assert page.headers['x-content-type-options'] == 'nosniff'
        assert page.headers['x-frame-options'] == 'DENY'
        assert "frame-ancestors 'none'" in page.headers['content-security-policy']
        csp = page.headers['content-security-policy']
        assert "script-src 'self' 'nonce-" in csp
        assert "'unsafe-inline'" not in csp
        study_id = int(page.text.split('/studies/')[1].split('"')[0])
        detail = client.get(f'/studies/{study_id}')
        assert 'Study access' in detail.text
        assert 'Skip to main content' in detail.text


def test_csp_nonce_is_present_on_public_and_authenticated_pages():
    with client:
        public_page = client.get('/login')
        public_csp = public_page.headers['content-security-policy']
        assert "script-src 'self' 'nonce-" in public_csp
        assert 'nonce="' in public_page.text

        auth()
        private_page = client.get('/projects')
        private_csp = private_page.headers['content-security-policy']
        assert "script-src 'self' 'nonce-" in private_csp
        assert 'nonce="' in private_page.text


def test_templates_do_not_use_inline_scripts_or_inline_event_handlers():
    for file_path in glob('app/templates/**/*.html', recursive=True):
        html = Path(file_path).read_text(encoding='utf-8')
        assert 'onclick=' not in html
        assert 'onchange=' not in html
        assert 'oninput=' not in html
        assert re.search(r'<script(?![^>]*\bsrc=)[^>]*>', html, flags=re.IGNORECASE) is None


def test_study_access_assignment():
    from app.db import SessionLocal
    from app.models import OrganisationMembership, User, Study, StudyAccess
    from app.security import hash_password
    from sqlalchemy import select
    with client:
        auth()
        with SessionLocal() as db:
            owner = db.scalar(select(User).where(User.email == 'admin@politis.local'))
            researcher = db.scalar(select(User).where(User.email == 'permissions@example.org'))
            if not researcher:
                researcher = User(organisation_id=owner.organisation_id, name='Permissions Researcher', email='permissions@example.org', password_hash=hash_password('SecurePass123!'), role='researcher')
                db.add(researcher); db.flush()
                db.add(OrganisationMembership(user_id=researcher.id, organisation_id=owner.organisation_id, role='researcher'))
                db.commit(); db.refresh(researcher)
            study = db.scalar(select(Study).where(Study.organisation_id == owner.organisation_id).order_by(Study.id))
            researcher_id, study_id = researcher.id, study.id
        response = post_with_csrf(f'/studies/{study_id}/access', data={'user_id': researcher_id, 'permission': 'view'}, follow_redirects=False)
        assert response.status_code == 303
        with SessionLocal() as db:
            row = db.scalar(select(StudyAccess).where(StudyAccess.study_id == study_id, StudyAccess.user_id == researcher_id))
            assert row and row.permission == 'view'


def test_storage_limit_and_antivirus_test_signature(tmp_path):
    from io import BytesIO
    from app.storage import LocalStorage
    from app.scanner import scan_file
    local = LocalStorage(tmp_path)
    stored = local.save_stream(BytesIO(b'normal evidence'), 'note.txt', 100)
    assert stored.size == 15 and len(stored.sha256_hex) == 64
    infected = local.save_stream(BytesIO(b'EICAR-STANDARD-ANTIVIRUS-TEST-FILE'), 'test.txt', 100)
    status, _ = scan_file(local.path(infected.key))
    assert status == 'infected'
    try:
        local.save_stream(BytesIO(b'x' * 101), 'large.txt', 100)
        assert False, 'Expected upload limit rejection'
    except ValueError:
        pass


def test_defender_webhook_validation_and_unknown_result():
    with client:
        validation = client.post('/webhooks/defender-storage', json=[{
            'eventType': 'Microsoft.EventGrid.SubscriptionValidationEvent',
            'data': {'validationCode': 'abc123'}
        }])
        assert validation.status_code == 200
        assert validation.json()['validationResponse'] == 'abc123'
        result = client.post('/webhooks/defender-storage', json=[{
            'eventType': 'Microsoft.Security.MalwareScanningResult',
            'data': {'blobUri': 'https://example.blob.core.windows.net/evidence/missing.pdf', 'scanResultType': 'No threats found'}
        }])
        assert result.status_code == 200 and result.json()['accepted'] is True


def test_hosted_webhook_rejects_unsigned_and_invalid_requests_and_logs(caplog):
    from app.config import settings
    original_env = settings.environment
    original_secret = settings.azure_defender_webhook_secret
    settings.environment = 'production'
    settings.azure_defender_webhook_secret = 'webhook-signature-secret'
    caplog.set_level('WARNING', logger='pcip.security')
    try:
        unsigned = client.post('/webhooks/defender-storage', json=[{'eventType': 'Microsoft.EventGrid.SubscriptionValidationEvent', 'data': {'validationCode': 'abc'}}])
        assert unsigned.status_code == 401
        assert 'Missing webhook signature.' in unsigned.text

        invalid = client.post('/webhooks/defender-storage', headers={'x-pcip-webhook-secret': 'wrong'}, json=[{'eventType': 'Microsoft.EventGrid.SubscriptionValidationEvent', 'data': {'validationCode': 'abc'}}])
        assert invalid.status_code == 401
        assert 'Invalid webhook secret.' in invalid.text

        messages = [r.message for r in caplog.records if 'webhook_rejected' in r.message]
        assert any('reason=unsigned' in m for m in messages)
        assert any('reason=invalid_signature' in m for m in messages)
    finally:
        settings.environment = original_env
        settings.azure_defender_webhook_secret = original_secret


def create_evidence_with_status(scan_status: str) -> int:
    from app.models import Activity, EvidenceFile, Participant, Study, User
    with SessionLocal() as db:
        owner = db.scalar(select(User).where(User.email == 'admin@politis.local'))
        study = db.scalar(select(Study).where(Study.organisation_id == owner.organisation_id).order_by(Study.id.asc()))
        activity = db.scalar(select(Activity).where(Activity.study_id == study.id).order_by(Activity.id.asc()))
        participant = Participant(
            organisation_id=owner.organisation_id,
            reference=unique_value('EVP').upper(),
            name='Evidence Participant',
            email=None,
            phone=None,
            status='prospective',
            consent_status='pending',
            communication_preference='email',
            tags='',
            demographics_json='{}',
            notes='',
            created_by_id=owner.id,
        )
        db.add(participant)
        db.flush()
        row = EvidenceFile(
            organisation_id=owner.organisation_id,
            study_id=study.id,
            activity_id=activity.id,
            participant_id=participant.id,
            response_id=None,
            original_name='blocked.txt',
            stored_name=f"{unique_value('missing-file')}.txt",
            content_type='text/plain',
            size_bytes=1,
            sha256_hex='0' * 64,
            scan_status=scan_status,
            scan_detail='',
            storage_provider='local',
            blob_uri='',
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id


def test_participant_detail_surfaces_evidence_file_and_scan_status():
    from app.models import EvidenceFile

    with client:
        client.cookies.clear()
        auth()
        evidence_id = create_evidence_with_status('pending')
        with SessionLocal() as db:
            evidence = db.get(EvidenceFile, evidence_id)
            participant_id = evidence.participant_id

        response = client.get(f'/participants/{participant_id}')

        assert response.status_code == 200
        assert 'Evidence files' in response.text
        assert 'blocked.txt' in response.text
        assert 'Pending' in response.text
        assert f'/evidence/{evidence_id}' in response.text


@pytest.mark.parametrize('scan_status', ['not_scanned', 'pending', 'failed', 'not_configured', 'error'])
def test_evidence_download_blocks_non_clean_scan_states(scan_status):
    with client:
        client.cookies.clear()
        auth()
        evidence_id = create_evidence_with_status(scan_status)
        response = client.get(f'/evidence/{evidence_id}')
        assert response.status_code == 423
        assert 'explicitly CLEAN' in response.text


def test_evidence_download_allows_dev_bypass_only_when_explicitly_enabled():
    from app.config import settings
    original_env = settings.environment
    original_bypass = settings.development_allow_unscanned_downloads
    try:
        settings.environment = 'development'
        settings.development_allow_unscanned_downloads = False
        with client:
            client.cookies.clear()
            auth()
            blocked_id = create_evidence_with_status('pending')
            blocked = client.get(f'/evidence/{blocked_id}')
            assert blocked.status_code == 423

        settings.development_allow_unscanned_downloads = True
        with client:
            client.cookies.clear()
            auth()
            bypass_id = create_evidence_with_status('pending')
            bypass = client.get(f'/evidence/{bypass_id}')
            # Bypass allows the request to pass the scan gate; file is still absent in local storage.
            assert bypass.status_code == 404
    finally:
        settings.environment = original_env
        settings.development_allow_unscanned_downloads = original_bypass


def test_azure_configuration_is_present():
    from app.config import settings
    assert settings.storage_backend == 'local'
    assert settings.azure_storage_container == 'evidence'
    assert settings.defender_require_clean_download is True


def test_login_page_respects_sign_in_configuration():
    from app.config import settings
    original_entra = settings.entra_enabled
    original_local = settings.local_login_enabled
    try:
        settings.entra_enabled = False
        settings.local_login_enabled = True
        response = client.get('/login')
        assert response.status_code == 200
        assert 'Sign in with Microsoft' not in response.text
        assert 'Forgot your password?' in response.text
    finally:
        settings.entra_enabled = original_entra
        settings.local_login_enabled = original_local

def test_user_model_supports_external_identity():
    from app.models import User
    columns = User.__table__.columns
    assert 'external_provider' in columns
    assert 'external_subject' in columns
    assert 'last_login_at' in columns

def test_failed_logins_lock_account():
    with SessionLocal() as db:
        before_user = db.scalar(
            select(User).where(User.email == "admin@politis.local")
        )
        assert before_user is not None
        before_session_version = before_user.session_version

    with client:
        for _ in range(settings.login_max_failed_attempts):
            response = post_with_csrf(
                "/login",
                data={
                    "email": "admin@politis.local",
                    "password": "wrong-password",
                },
                follow_redirects=False,
            )
            assert response.status_code == 200
            assert "Email or password is incorrect." in response.text

        response = login()
        assert response.status_code == 200
        assert "Email or password is incorrect." in response.text

        with SessionLocal() as db:
            user = db.scalar(
                select(User).where(User.email == "admin@politis.local")
            )
            assert user is not None
            assert user.failed_login_count == settings.login_max_failed_attempts
            assert user.locked_until is not None
            assert user.session_version == before_session_version + 1


def test_expired_lockout_allows_login_and_resets_counter():
    with SessionLocal() as db:
        user = db.scalar(
            select(User).where(User.email == "admin@politis.local")
        )
        assert user is not None

        user.failed_login_count = settings.login_max_failed_attempts
        user.locked_until = now() - timedelta(seconds=1)
        db.commit()

    with client:
        response = login()
        assert response.status_code == 303

    with SessionLocal() as db:
        user = db.scalar(
            select(User).where(User.email == "admin@politis.local")
        )
        assert user is not None
        assert user.failed_login_count == 0
        assert user.locked_until is None


def test_csrf_rejects_missing_and_invalid_token():
    with client:
        missing = client.post(
            '/login',
            data={'email': 'admin@politis.local', 'password': 'PolitisDemo!'},
            follow_redirects=False,
        )
        assert missing.status_code == 422

        invalid = client.post(
            '/login',
            data={
                'email': 'admin@politis.local',
                'password': 'PolitisDemo!',
                'csrf_token': 'invalid-token',
            },
            follow_redirects=False,
        )
        assert invalid.status_code == 403
        assert invalid.json()['detail'] == 'Invalid CSRF token.'


def test_csrf_blocks_authenticated_post_without_token():
    with client:
        auth()
        denied = client.post(
            '/projects',
            data={
                'title': 'Blocked project',
                'code': 'CSRF-001',
                'description': 'Should be rejected',
                'status_value': 'draft',
            },
            follow_redirects=False,
        )
        assert denied.status_code == 422

        allowed = post_with_csrf(
            '/projects',
            data={
                'title': 'Allowed project',
                'code': 'CSRF-002',
                'description': 'Should pass',
                'status_value': 'draft',
            },
            follow_redirects=False,
        )
        assert allowed.status_code == 303


def test_organisation_isolation_across_project_study_and_participant_endpoints():
    from app.models import Organisation, User
    from app.security import hash_password
    with client:
        client.cookies.clear()
        auth()
        code = unique_value('ORGISO').upper()
        project = post_with_csrf(
            '/projects',
            data={
                'title': f'Isolation project {code}',
                'code': code,
                'description': 'Org isolation test',
                'status_value': 'live',
            },
            follow_redirects=False,
        )
        assert project.status_code == 303
        project_id = int(project.headers['location'].split('/')[-1])

        study = post_with_csrf(
            f'/projects/{project_id}/studies',
            data={
                'title': f'Isolation study {code}',
                'code': f'{code}S',
                'description': 'Org isolation test',
                'methodology': 'diary',
                'status_value': 'recruiting',
            },
            follow_redirects=False,
        )
        assert study.status_code == 303
        study_id = int(study.headers['location'].split('/')[-1])

        participant = post_with_csrf(
            '/participants',
            data={
                'reference': f'{code}P',
                'name': f'Participant {code}',
                'email': f'{code.lower()}@example.org',
                'phone': '',
                'status_value': 'prospective',
                'consent_status': 'pending',
                'communication_preference': 'email',
                'tags': '',
                'notes': '',
            },
            follow_redirects=False,
        )
        assert participant.status_code == 303
        participant_id = int(participant.headers['location'].split('/')[-1])
        post_with_csrf(f'/studies/{study_id}/enrol', data={'participant_id': participant_id}, follow_redirects=False)

        second_email = f"{unique_value('owner2')}@example.org"
        second_password = 'SecurePass123!'
        with SessionLocal() as db:
            second_org = Organisation(name=unique_value('Org Two'), slug=unique_value('org-two').lower())
            db.add(second_org); db.flush()
            db.add(User(organisation_id=second_org.id, name='Second Owner', email=second_email, password_hash=hash_password(second_password), role='owner'))
            db.commit()

        client.cookies.clear()
        login_response = login_as(second_email, second_password)
        assert login_response.status_code == 303

        assert client.get(f'/projects/{project_id}').status_code == 404
        assert client.get(f'/studies/{study_id}').status_code == 404
        assert client.get(f'/participants/{participant_id}').status_code == 404

        denied_update = post_with_csrf(
            f'/participants/{participant_id}/update',
            data={
                'name': 'Should Fail',
                'email': '',
                'phone': '',
                'status_value': 'prospective',
                'consent_status': 'pending',
                'communication_preference': 'email',
                'tags': '',
                'notes': '',
                'demographics_json': '{}',
            },
            follow_redirects=False,
        )
        assert denied_update.status_code == 404


def test_researcher_cannot_access_admin_surfaces_or_actions():
    from app.models import User
    from app.security import hash_password
    with client:
        client.cookies.clear()
        auth()
        researcher_email = f"{unique_value('researcher-admin-block')}@example.org"
        researcher_password = 'SecurePass123!'
        with SessionLocal() as db:
            owner = db.scalar(select(User).where(User.email == 'admin@politis.local'))
            db.add(User(organisation_id=owner.organisation_id, name='Researcher Blocked', email=researcher_email, password_hash=hash_password(researcher_password), role='researcher'))
            db.commit()

        client.cookies.clear()
        login_response = login_as(researcher_email, researcher_password)
        assert login_response.status_code == 303

        for path in ['/researchers', '/audit', '/outbox']:
            assert client.get(path).status_code == 403

        denied_invite = post_with_csrf(
            '/researchers/invite',
            data={'name': 'Nope', 'email': f"{unique_value('x')}@example.org", 'role': 'researcher'},
            follow_redirects=False,
        )
        assert denied_invite.status_code == 403


def test_restricted_researcher_cannot_access_unassigned_study_or_participant_records():
    from app.models import User
    from app.security import hash_password
    with client:
        client.cookies.clear()
        auth()
        code = unique_value('SCOPE').upper()
        project = post_with_csrf('/projects', data={'title': f'Scope project {code}', 'code': code, 'description': '', 'status_value': 'live'}, follow_redirects=False)
        project_id = int(project.headers['location'].split('/')[-1])
        study = post_with_csrf(
            f'/projects/{project_id}/studies',
            data={'title': f'Scope study {code}', 'code': f'{code}S', 'description': '', 'methodology': 'diary', 'status_value': 'recruiting'},
            follow_redirects=False,
        )
        study_id = int(study.headers['location'].split('/')[-1])
        participant = post_with_csrf(
            '/participants',
            data={
                'reference': f'{code}P',
                'name': f'Scoped Participant {code}',
                'email': f'{code.lower()}@example.org',
                'phone': '',
                'status_value': 'prospective',
                'consent_status': 'pending',
                'communication_preference': 'email',
                'tags': '',
                'notes': '',
            },
            follow_redirects=False,
        )
        participant_id = int(participant.headers['location'].split('/')[-1])
        post_with_csrf(f'/studies/{study_id}/enrol', data={'participant_id': participant_id}, follow_redirects=False)

        researcher_email = f"{unique_value('restricted')}@example.org"
        researcher_password = 'SecurePass123!'
        with SessionLocal() as db:
            owner = db.scalar(select(User).where(User.email == 'admin@politis.local'))
            db.add(User(organisation_id=owner.organisation_id, name='Restricted Researcher', email=researcher_email, password_hash=hash_password(researcher_password), role='researcher'))
            db.commit()

        client.cookies.clear()
        login_response = login_as(researcher_email, researcher_password)
        assert login_response.status_code == 303

        dashboard = client.get('/')
        assert dashboard.status_code == 200
        assert f'Scope study {code}' not in dashboard.text

        projects_page = client.get('/projects')
        assert projects_page.status_code == 200
        assert f'Scope project {code}' not in projects_page.text
        assert client.get(f'/projects/{project_id}').status_code == 403

        studies_page = client.get('/studies')
        assert studies_page.status_code == 200
        assert f'Scope study {code}' not in studies_page.text
        assert client.get(f'/studies/{study_id}').status_code == 403

        participants_page = client.get('/participants')
        assert participants_page.status_code == 200
        assert f'Scoped Participant {code}' not in participants_page.text
        assert client.get(f'/participants/{participant_id}').status_code == 403


def test_researcher_with_view_access_can_read_study_participant_but_not_edit_study():
    from app.models import User, StudyAccess
    from app.security import hash_password
    with client:
        client.cookies.clear()
        auth()
        code = unique_value('VIEW').upper()
        project = post_with_csrf('/projects', data={'title': f'View project {code}', 'code': code, 'description': '', 'status_value': 'live'}, follow_redirects=False)
        project_id = int(project.headers['location'].split('/')[-1])
        study = post_with_csrf(
            f'/projects/{project_id}/studies',
            data={'title': f'View study {code}', 'code': f'{code}S', 'description': '', 'methodology': 'diary', 'status_value': 'recruiting'},
            follow_redirects=False,
        )
        study_id = int(study.headers['location'].split('/')[-1])
        participant = post_with_csrf(
            '/participants',
            data={
                'reference': f'{code}P',
                'name': f'View Participant {code}',
                'email': f'{code.lower()}@example.org',
                'phone': '',
                'status_value': 'prospective',
                'consent_status': 'pending',
                'communication_preference': 'email',
                'tags': '',
                'notes': '',
            },
            follow_redirects=False,
        )
        participant_id = int(participant.headers['location'].split('/')[-1])
        post_with_csrf(f'/studies/{study_id}/enrol', data={'participant_id': participant_id}, follow_redirects=False)

        researcher_email = f"{unique_value('viewer')}@example.org"
        researcher_password = 'SecurePass123!'
        with SessionLocal() as db:
            owner = db.scalar(select(User).where(User.email == 'admin@politis.local'))
            researcher = User(organisation_id=owner.organisation_id, name='View Researcher', email=researcher_email, password_hash=hash_password(researcher_password), role='researcher')
            db.add(researcher); db.flush()
            db.add(StudyAccess(organisation_id=owner.organisation_id, study_id=study_id, user_id=researcher.id, permission='view', created_by_id=owner.id))
            db.commit()

        client.cookies.clear()
        login_response = login_as(researcher_email, researcher_password)
        assert login_response.status_code == 303

        dashboard = client.get('/')
        assert dashboard.status_code == 200
        assert f'View study {code}' in dashboard.text

        projects_page = client.get('/projects')
        assert projects_page.status_code == 200
        assert f'View project {code}' in projects_page.text
        project_detail = client.get(f'/projects/{project_id}')
        assert project_detail.status_code == 200
        assert f'View study {code}' in project_detail.text

        assert client.get(f'/studies/{study_id}').status_code == 200
        assert client.get(f'/participants/{participant_id}').status_code == 200

        denied_edit = post_with_csrf(
            f'/studies/{study_id}/activities',
            data={
                'title': 'Blocked edit',
                'prompt': '',
                'activity_type': 'long_text',
                'options': '',
                'required': 'true',
                'release_offset_days': '0',
                'due_offset_days': '',
            },
            follow_redirects=False,
        )
        assert denied_edit.status_code == 403


def test_researcher_message_requires_participant_enrolment_in_study():
    with client:
        client.cookies.clear()
        auth()
        code = unique_value('MSGISO').upper()
        project = post_with_csrf('/projects', data={'title': f'Message project {code}', 'code': code, 'description': '', 'status_value': 'live'}, follow_redirects=False)
        project_id = int(project.headers['location'].split('/')[-1])

        study_a = post_with_csrf(
            f'/projects/{project_id}/studies',
            data={'title': f'Message study A {code}', 'code': f'{code}A', 'description': '', 'methodology': 'diary', 'status_value': 'recruiting'},
            follow_redirects=False,
        )
        study_a_id = int(study_a.headers['location'].split('/')[-1])
        study_b = post_with_csrf(
            f'/projects/{project_id}/studies',
            data={'title': f'Message study B {code}', 'code': f'{code}B', 'description': '', 'methodology': 'diary', 'status_value': 'recruiting'},
            follow_redirects=False,
        )
        study_b_id = int(study_b.headers['location'].split('/')[-1])

        participant = post_with_csrf(
            '/participants',
            data={
                'reference': f'{code}P',
                'name': f'Message Participant {code}',
                'email': f'{code.lower()}@example.org',
                'phone': '',
                'status_value': 'prospective',
                'consent_status': 'pending',
                'communication_preference': 'email',
                'tags': '',
                'notes': '',
            },
            follow_redirects=False,
        )
        participant_id = int(participant.headers['location'].split('/')[-1])
        post_with_csrf(f'/studies/{study_a_id}/enrol', data={'participant_id': participant_id}, follow_redirects=False)

        denied = post_with_csrf(
            f'/participants/{participant_id}/message',
            data={'study_id': study_b_id, 'body': 'Should fail', 'internal_note': 'true'},
            follow_redirects=False,
        )
        assert denied.status_code == 400

        allowed = post_with_csrf(
            f'/participants/{participant_id}/message',
            data={'study_id': study_a_id, 'body': 'Allowed', 'internal_note': 'true'},
            follow_redirects=False,
        )
        assert allowed.status_code == 303


def test_researcher_message_route_preserves_sender_audit_and_redirect_semantics():
    from app.models import AuditEvent, ParticipantMessage

    with client:
        client.cookies.clear()
        auth()
        code = unique_value('MSGROUTE').upper()
        project = post_with_csrf('/projects', data={'title': f'Message route project {code}', 'code': code, 'description': '', 'status_value': 'live'}, follow_redirects=False)
        project_id = int(project.headers['location'].split('/')[-1])

        study = post_with_csrf(
            f'/projects/{project_id}/studies',
            data={'title': f'Message route study {code}', 'code': f'{code}A', 'description': '', 'methodology': 'diary', 'status_value': 'recruiting'},
            follow_redirects=False,
        )
        study_id = int(study.headers['location'].split('/')[-1])

        participant_created = post_with_csrf(
            '/participants',
            data={
                'reference': f'{code}P',
                'name': f'Message Route Participant {code}',
                'email': f'{code.lower()}@example.org',
                'phone': '',
                'status_value': 'prospective',
                'consent_status': 'pending',
                'communication_preference': 'email',
                'tags': '',
                'notes': '',
            },
            follow_redirects=False,
        )
        participant_id = int(participant_created.headers['location'].split('/')[-1])
        post_with_csrf(f'/studies/{study_id}/enrol', data={'participant_id': participant_id}, follow_redirects=False)

        response = post_with_csrf(
            f'/participants/{participant_id}/message',
            data={'study_id': study_id, 'body': '  routed note  ', 'internal_note': 'true'},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers['location'] == f'/participants/{participant_id}#messages'

        with SessionLocal() as db:
            message = db.scalar(
                select(ParticipantMessage)
                .where(ParticipantMessage.participant_id == participant_id)
                .order_by(ParticipantMessage.id.desc())
            )
            assert message is not None
            assert message.sender_type == 'researcher'
            assert message.sender_user_id is not None
            assert message.body == 'routed note'
            assert message.internal_note is True

            audit_row = db.scalar(
                select(AuditEvent)
                .where(
                    AuditEvent.action == 'message.created',
                    AuditEvent.entity_type == 'participant',
                    AuditEvent.entity_id == str(participant_id),
                )
                .order_by(AuditEvent.id.desc())
            )
            assert audit_row is not None
            assert audit_row.detail == 'internal'


def test_participant_message_route_preserves_validation_and_storage_semantics():
    from app.models import OutboxEmail, ParticipantMessage

    with client:
        client.cookies.clear()
        auth()
        code = unique_value('MSGPORTAL').upper()
        project = post_with_csrf('/projects', data={'title': f'Portal message project {code}', 'code': code, 'description': '', 'status_value': 'live'}, follow_redirects=False)
        project_id = int(project.headers['location'].split('/')[-1])
        study = post_with_csrf(
            f'/projects/{project_id}/studies',
            data={'title': f'Portal message study {code}', 'code': f'{code}A', 'description': '', 'methodology': 'diary', 'status_value': 'recruiting'},
            follow_redirects=False,
        )
        study_id = int(study.headers['location'].split('/')[-1])
        participant_created = post_with_csrf(
            '/participants',
            data={
                'reference': f'{code}P',
                'name': f'Portal Message Participant {code}',
                'email': f'{code.lower()}@example.org',
                'phone': '',
                'status_value': 'prospective',
                'consent_status': 'pending',
                'communication_preference': 'email',
                'tags': '',
                'notes': '',
            },
            follow_redirects=False,
        )
        participant_id = int(participant_created.headers['location'].split('/')[-1])

        post_with_csrf(f'/studies/{study_id}/enrol', data={'participant_id': participant_id}, follow_redirects=False)
        post_with_csrf(f'/studies/{study_id}/invite/{participant_id}', follow_redirects=False)

        with SessionLocal() as db:
            invite_email = db.scalar(
                select(OutboxEmail)
                .where(OutboxEmail.recipient == f'{code.lower()}@example.org')
                .order_by(OutboxEmail.id.desc())
            )
            assert invite_email is not None
            token = invite_email.body.split('token=')[1].strip()

        client.get(f'/join-study?token={token}')
        consent = post_with_csrf('/join-study', data={'consent': 'true'}, follow_redirects=False)
        assert consent.status_code == 303

        empty = post_with_csrf('/participant-portal/message', data={'body': '   '}, follow_redirects=False)
        assert empty.status_code == 400

        created = post_with_csrf('/participant-portal/message', data={'body': '  hello research  '}, follow_redirects=False)
        assert created.status_code == 303
        assert created.headers['location'] == '/participant-portal#messages'

        with SessionLocal() as db:
            message = db.scalar(
                select(ParticipantMessage)
                .where(ParticipantMessage.participant_id == participant_id, ParticipantMessage.study_id == study_id)
                .order_by(ParticipantMessage.id.desc())
            )
            assert message is not None
            assert message.sender_type == 'participant'
            assert message.sender_user_id is None
            assert message.internal_note is False
            assert message.body == 'hello research'


def hosted_settings(**overrides):
    data = {
        'environment': 'production',
        'secret_key': 'VeryStrongSecretKey!WithLength12345',
        'database_url': 'postgresql+psycopg://pcip:strongpassword@db.example.org:5432/pcip?sslmode=require',
        'cookie_secure': True,
        'session_cookie_secure': True,
        'base_url': 'https://pilot.example.org',
        'trusted_hosts': 'pilot.example.org',
        'allowed_origins': 'https://pilot.example.org',
        'azure_defender_webhook_secret': 'required-webhook-secret',
        'seed_demo_data': False,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.mark.parametrize(
    ('override', 'expected_fragment'),
    [
        ({'secret_key': 'dev-only-change-me'}, 'SECRET_KEY'),
        ({'secret_key': 'short'}, 'SECRET_KEY'),
        ({'cookie_secure': False}, 'COOKIE_SECURE'),
        ({'session_cookie_secure': False}, 'SESSION_COOKIE_SECURE'),
        ({'base_url': 'http://pilot.example.org'}, 'BASE_URL'),
        ({'trusted_hosts': ''}, 'TRUSTED_HOSTS'),
        ({'trusted_hosts': 'localhost,pilot.example.org'}, 'TRUSTED_HOSTS'),
        ({'allowed_origins': ''}, 'ALLOWED_ORIGINS'),
        ({'allowed_origins': 'http://pilot.example.org'}, 'ALLOWED_ORIGINS'),
        ({'azure_defender_webhook_secret': ''}, 'AZURE_DEFENDER_WEBHOOK_SECRET'),
        ({'database_url': 'sqlite:///./data/app.db'}, 'DATABASE_URL'),
        ({'seed_demo_data': True}, 'SEED_DEMO_DATA'),
    ],
)
def test_hosted_startup_validation_rejects_insecure_settings(override, expected_fragment):
    candidate = hosted_settings(**override)
    with pytest.raises(RuntimeError) as exc:
        validate_runtime_settings(candidate)
    assert expected_fragment in str(exc.value)


def test_hosted_startup_validation_accepts_secure_settings():
    candidate = hosted_settings(
        secret_key='AnotherStrongKey!1234567890_WithEntropy',
        cookie_secure=True,
        session_cookie_secure=True,
        base_url='https://secure.pilot.example.org',
        trusted_hosts='secure.pilot.example.org',
        allowed_origins='https://secure.pilot.example.org',
    )
    validate_runtime_settings(candidate)


def test_azure_bicep_sets_required_secure_cookie_settings():
    bicep = Path('infra/main.bicep').read_text()
    assert "{ name: 'COOKIE_SECURE', value: 'true' }" in bicep
    assert "{ name: 'SESSION_COOKIE_SECURE', value: 'true' }" in bicep
    assert 'param runMigrations bool = false' in bicep
    assert "{ name: 'RUN_MIGRATIONS', value: string(runMigrations) }" in bicep


def test_migrations_are_automatic_only_in_local_compose():
    entrypoint = Path('entrypoint.sh').read_text()
    compose = Path('docker-compose.yml').read_text()
    assert '${RUN_MIGRATIONS:-false}' in entrypoint
    assert 'RUN_MIGRATIONS: "true"' in compose


def test_development_environment_allows_local_defaults():
    candidate = hosted_settings(
        environment='development',
        secret_key='dev-only-change-me',
        cookie_secure=False,
        session_cookie_secure=False,
        base_url='http://127.0.0.1:8000',
        trusted_hosts='127.0.0.1,localhost,testserver',
        allowed_origins='http://127.0.0.1:8000,http://localhost:8000,http://testserver',
    )
    validate_runtime_settings(candidate)


def test_test_environment_allows_local_defaults():
    candidate = hosted_settings(
        environment='test',
        secret_key='dev-only-change-me',
        cookie_secure=False,
        session_cookie_secure=False,
        base_url='http://127.0.0.1:8000',
        trusted_hosts='127.0.0.1,localhost,testserver',
        allowed_origins='http://127.0.0.1:8000,http://localhost:8000,http://testserver',
    )
    validate_runtime_settings(candidate)


@contextmanager
def with_rate_limit_settings(**overrides):
    names = [
        'rate_limit_enabled',
        'rate_limit_window_seconds',
        'rate_limit_login_ip',
        'rate_limit_login_account',
        'rate_limit_forgot_password_ip',
        'rate_limit_forgot_password_account',
        'rate_limit_password_reset_ip',
        'rate_limit_password_reset_token',
        'rate_limit_invitation_accept_ip',
        'rate_limit_invitation_accept_token',
        'rate_limit_portal_write_ip',
        'rate_limit_portal_write_token',
    ]
    original = {name: getattr(settings, name) for name in names}
    try:
        for name, value in overrides.items():
            setattr(settings, name, value)
        rate_limiter.reset()
        yield
    finally:
        for name, value in original.items():
            setattr(settings, name, value)
        rate_limiter.reset()


def test_login_rate_limit_sets_retry_after_and_audits_abuse():
    from app.models import AuditEvent
    with with_rate_limit_settings(rate_limit_enabled=True, rate_limit_window_seconds=60, rate_limit_login_ip=1, rate_limit_login_account=1):
        with client:
            client.cookies.clear()
            first = post_with_csrf('/login', data={'email': 'admin@politis.local', 'password': 'PolitisDemo!'}, follow_redirects=False)
            assert first.status_code == 303
            blocked = post_with_csrf('/login', data={'email': 'admin@politis.local', 'password': 'PolitisDemo!'}, follow_redirects=False)
            assert blocked.status_code == 429
            assert 'Retry-After' in blocked.headers
            assert 'Too many requests' in blocked.text

        with SessionLocal() as db:
            row = db.scalar(select(AuditEvent).where(AuditEvent.action == 'security.rate_limited').order_by(AuditEvent.id.desc()))
            assert row is not None
            assert row.detail.startswith('scope=login')


def test_in_memory_rate_limiter_bounds_unique_keys():
    limiter = InMemoryRateLimiter(max_keys=2)
    assert limiter.check('first', 2, 60) is None
    assert limiter.check('second', 2, 60) is None
    assert limiter.check('third', 2, 60) is None
    assert list(limiter._hits) == ['second', 'third']


def test_forgot_password_rate_limit_blocks_repeated_attempts():
    with with_rate_limit_settings(rate_limit_enabled=True, rate_limit_window_seconds=60, rate_limit_forgot_password_ip=1, rate_limit_forgot_password_account=1):
        with client:
            first = post_with_csrf('/forgot-password', data={'email': 'admin@politis.local'}, follow_redirects=False)
            assert first.status_code == 200
            blocked = post_with_csrf('/forgot-password', data={'email': 'admin@politis.local'}, follow_redirects=False)
            assert blocked.status_code == 429
            assert 'Retry-After' in blocked.headers


def test_password_reset_rate_limit_blocks_repeated_token_attempts():
    with with_rate_limit_settings(rate_limit_enabled=True, rate_limit_window_seconds=60, rate_limit_password_reset_ip=1, rate_limit_password_reset_token=1):
        with client:
            first = post_with_csrf('/reset-password', data={'token': 'invalid-token', 'password': 'SecurePass123!'}, follow_redirects=False)
            assert first.status_code == 400
            blocked = post_with_csrf('/reset-password', data={'token': 'invalid-token', 'password': 'SecurePass123!'}, follow_redirects=False)
            assert blocked.status_code == 429
            assert 'Retry-After' in blocked.headers


def test_invitation_acceptance_rate_limit_blocks_repeated_attempts():
    with with_rate_limit_settings(rate_limit_enabled=True, rate_limit_window_seconds=60, rate_limit_invitation_accept_ip=1, rate_limit_invitation_accept_token=1):
        with client:
            first_researcher = post_with_csrf('/accept-invitation', data={'token': 'invalid', 'password': 'SecurePass123!'}, follow_redirects=False)
            assert first_researcher.status_code == 400
            blocked_researcher = post_with_csrf('/accept-invitation', data={'token': 'invalid', 'password': 'SecurePass123!'}, follow_redirects=False)
            assert blocked_researcher.status_code == 429

            rate_limiter.reset()
            first_participant = post_with_csrf('/join-study', data={'token': 'invalid', 'consent': 'true'}, follow_redirects=False)
            assert first_participant.status_code == 400
            blocked_participant = post_with_csrf('/join-study', data={'token': 'invalid', 'consent': 'true'}, follow_redirects=False)
            assert blocked_participant.status_code == 429


def test_participant_portal_write_rate_limit_blocks_repeated_attempts():
    with with_rate_limit_settings(rate_limit_enabled=True, rate_limit_window_seconds=60, rate_limit_portal_write_ip=1, rate_limit_portal_write_token=1):
        with client:
            first = post_with_csrf('/participant-portal/message', data={'token': 'invalid', 'body': 'hello'}, follow_redirects=False)
            assert first.status_code == 400
            blocked = post_with_csrf('/participant-portal/message', data={'token': 'invalid', 'body': 'hello'}, follow_redirects=False)
            assert blocked.status_code == 429
            assert 'Retry-After' in blocked.headers


def test_stolen_cookie_stops_working_after_admin_password_reset():
    from app.models import OrganisationMembership, OutboxEmail
    from app.security import hash_password

    researcher_email = f"{unique_value('stolen-cookie')}@example.org"
    researcher_password = 'SecurePass123!'

    with SessionLocal() as db:
        owner = db.scalar(select(User).where(User.email == 'admin@politis.local'))
        assert owner is not None
        researcher = User(
            organisation_id=owner.organisation_id,
            name='Cookie Target',
            email=researcher_email,
            password_hash=hash_password(researcher_password),
            role='researcher',
            is_active=True,
        )
        db.add(researcher)
        db.flush()
        db.add(OrganisationMembership(user_id=researcher.id, organisation_id=owner.organisation_id, role='researcher'))
        db.commit()
        db.refresh(researcher)
        researcher_id = researcher.id
        before_version = researcher.session_version

    with client:
        client.cookies.clear()
        researcher_login = login_as(researcher_email, researcher_password)
        assert researcher_login.status_code == 303
        stolen_cookie = client.cookies.get('session')
        assert stolen_cookie

        client.cookies.clear()
        owner_login = login()
        client.cookies.update(owner_login.cookies)
        assert owner_login.status_code == 303

        reset = post_with_csrf(f'/researchers/{researcher_id}/reset-password', follow_redirects=False)
        assert reset.status_code == 303

        with SessionLocal() as db:
            refreshed = db.get(User, researcher_id)
            assert refreshed is not None
            assert refreshed.session_version == before_version + 1
            reset_mail = db.scalar(
                select(OutboxEmail)
                .where(OutboxEmail.recipient == researcher_email)
                .order_by(OutboxEmail.id.desc())
            )
            assert reset_mail is not None
            assert '/reset-password?token=' in reset_mail.body

        client.cookies.clear()
        client.cookies.set('session', stolen_cookie)
        denied = client.get('/', follow_redirects=False)
        assert denied.status_code == 303
        assert denied.headers['location'] == '/login'


def test_logout_invalidates_existing_session_cookie():
    with SessionLocal() as db:
        before_user = db.scalar(select(User).where(User.email == 'admin@politis.local'))
        assert before_user is not None
        before_version = before_user.session_version

    with client:
        client.cookies.clear()
        login_response = login()
        client.cookies.update(login_response.cookies)
        assert login_response.status_code == 303
        stolen_cookie = client.cookies.get('session')
        assert stolen_cookie

        logout_response = post_with_csrf('/logout', follow_redirects=False)
        assert logout_response.status_code == 303

        with SessionLocal() as db:
            after_user = db.scalar(select(User).where(User.email == 'admin@politis.local'))
            assert after_user is not None
            assert after_user.session_version == before_version + 1

        client.cookies.clear()
        client.cookies.set('session', stolen_cookie)
        denied = client.get('/', follow_redirects=False)
        assert denied.status_code == 303
        assert denied.headers['location'] == '/login'


def test_password_reset_invalidates_existing_session_cookie():
    from app.models import OutboxEmail
    from app.security import hash_password, verify_password

    email = f"{unique_value('pwd-reset')}@example.org"
    old_password = 'SecurePass123!'
    new_password = 'SecurePass456!'

    with SessionLocal() as db:
        owner = db.scalar(select(User).where(User.email == 'admin@politis.local'))
        assert owner is not None
        user = User(
            organisation_id=owner.organisation_id,
            name='Reset Target',
            email=email,
            password_hash=hash_password(old_password),
            role='researcher',
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
        before_version = user.session_version

    with client:
        client.cookies.clear()
        login_response = login_as(email, old_password)
        assert login_response.status_code == 303
        stolen_cookie = client.cookies.get('session')
        assert stolen_cookie

        forgot = post_with_csrf('/forgot-password', data={'email': email}, follow_redirects=False)
        assert forgot.status_code == 200

        with SessionLocal() as db:
            email_row = db.scalar(
                select(OutboxEmail)
                .where(OutboxEmail.recipient == email)
                .order_by(OutboxEmail.id.desc())
            )
            assert email_row is not None
            token = email_row.body.split('token=')[1].strip()

        client.get(f'/reset-password?token={token}', follow_redirects=False)
        reset = post_with_csrf('/reset-password', data={'password': new_password}, follow_redirects=False)
        assert reset.status_code == 303

        with SessionLocal() as db:
            refreshed = db.get(User, user_id)
            assert refreshed is not None
            assert refreshed.session_version == before_version + 1
            assert verify_password(new_password, refreshed.password_hash)

        client.cookies.clear()
        client.cookies.set('session', stolen_cookie)
        denied = client.get('/', follow_redirects=False)
        assert denied.status_code == 303
        assert denied.headers['location'] == '/login'


def test_pwa_manifest_is_valid_and_participant_focused():
    import json

    response = client.get('/static/manifest.webmanifest')

    assert response.status_code == 200
    manifest = json.loads(response.text)
    assert manifest['name'] == 'Citizen Centric Participant'
    assert manifest['start_url'] == '/participant-portal'
    assert manifest['scope'] == '/'
    assert manifest['display'] == 'standalone'
    assert manifest['icons'] == []


def test_service_worker_is_root_scoped_and_not_cached():
    response = client.get('/service-worker.js')

    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-cache'
    assert response.headers['service-worker-allowed'] == '/'
    assert 'application/javascript' in response.headers['content-type']


def test_service_worker_caches_only_explicit_public_assets():
    response = client.get('/service-worker.js')

    assert response.status_code == 200
    script = response.text

    assert 'PUBLIC_STATIC_ASSETS' in script
    assert '/static/offline.html' in script
    assert '/static/politis_symbol_colour.png' in script
    assert 'request.mode === "navigate"' in script

    sensitive_paths = [
        '/participant-portal',
        '/join-study',
        '/evidence/',
        '/api/',
        '/participants/',
        '/messages/',
    ]
    for path in sensitive_paths:
        assert path not in script


def test_offline_page_contains_no_participant_information():
    response = client.get('/static/offline.html')

    assert response.status_code == 200
    assert "You’re offline" in response.text
    assert 'No participant page, response, message or evidence' in response.text
    assert 'csrf_token' not in response.text
    assert 'invitation' not in response.text.lower()
    assert 'participant.name' not in response.text


def test_base_template_links_to_manifest():
    template = Path('app/templates/base.html').read_text()

    assert (
        '<link rel="manifest" href="/static/manifest.webmanifest">'
        in template
    )
    assert '<meta name="theme-color" content="#215bb3">' in template


def test_participant_templates_register_pwa_once():
    join_template = Path('app/templates/join_study.html').read_text()
    portal_template = Path('app/templates/participant_portal.html').read_text()

    script_reference = 'src="/static/participant_pwa.js"'

    assert join_template.count(script_reference) == 1
    assert portal_template.count(script_reference) == 1
    assert 'id="main-content"' in portal_template


def test_pwa_registration_uses_root_service_worker_scope():
    script = Path('app/static/participant_pwa.js').read_text()

    assert '.register("/service-worker.js", { scope: "/" })' in script
    assert 'localStorage' not in script
    assert 'sessionStorage' not in script


def test_resolve_participant_invitation_success():
    from app.main import now
    from app.models import Participant, ParticipantInvitation, Project, PublicAuthSession, Study
    from app.participant_services import resolve_participant_invitation
    from app.security import new_token, token_hash

    with SessionLocal() as db:
        user = db.scalar(select(User).order_by(User.id))
        assert user is not None

        project = db.scalar(
            select(Project)
            .where(Project.organisation_id == user.organisation_id)
            .order_by(Project.id)
        )
        if not project:
            project = Project(
                organisation_id=user.organisation_id,
                title=unique_value('Resolver project'),
                code=unique_value('resolver-project').upper(),
                description='Resolver test project',
                status='draft',
                created_by_id=user.id,
            )
            db.add(project)
            db.flush()

        study_row = db.scalar(
            select(Study)
            .where(Study.organisation_id == user.organisation_id)
            .order_by(Study.id)
        )
        if not study_row:
            study_row = Study(
                organisation_id=user.organisation_id,
                project_id=project.id,
                title=unique_value('Resolver study'),
                code=unique_value('resolver-study').upper(),
                description='Resolver test study',
                methodology='diary',
                status='draft',
                created_by_id=user.id,
            )
            db.add(study_row)
            db.flush()

        participant_row = db.scalar(
            select(Participant)
            .where(Participant.organisation_id == user.organisation_id)
            .order_by(Participant.id)
        )
        if not participant_row:
            participant_row = Participant(
                organisation_id=user.organisation_id,
                reference=unique_value('resolver-participant').upper(),
                name='Resolver Participant',
                email=f"{unique_value('resolver')}@example.org",
                status='invited',
                consent_status='pending',
                communication_preference='email',
                created_by_id=user.id,
            )
            db.add(participant_row)
            db.flush()

        invitation = ParticipantInvitation(
            organisation_id=user.organisation_id,
            participant_id=participant_row.id,
            study_id=study_row.id,
            token_hash=token_hash(new_token()),
            expires_at=now() + timedelta(days=1),
            invited_by_id=user.id,
        )
        db.add(invitation)
        db.flush()

        session_row = PublicAuthSession(
            scope='participant_portal',
            session_hash=token_hash(new_token()),
            participant_invitation_id=invitation.id,
            expires_at=now() + timedelta(hours=1),
        )
        db.add(session_row)
        db.flush()

        resolved = resolve_participant_invitation(db, session_row)
        assert resolved is not None
        assert resolved.id == invitation.id


def test_resolve_participant_invitation_missing_participant_invitation_id():
    from app.main import now
    from app.models import PublicAuthSession
    from app.participant_services import resolve_participant_invitation

    with SessionLocal() as db:
        session_row = PublicAuthSession(
            scope='participant_portal',
            session_hash='resolver-missing-id',
            participant_invitation_id=None,
            expires_at=now() + timedelta(hours=1),
        )
        assert resolve_participant_invitation(db, session_row) is None


def test_resolve_participant_invitation_missing_invitation_record():
    from app.main import now
    from app.models import PublicAuthSession
    from app.participant_services import resolve_participant_invitation

    with SessionLocal() as db:
        session_row = PublicAuthSession(
            scope='participant_portal',
            session_hash='resolver-missing-invitation',
            participant_invitation_id=999999999,
            expires_at=now() + timedelta(hours=1),
        )
        assert resolve_participant_invitation(db, session_row) is None


def test_resolve_participant_invitation_does_not_validate_auth_or_scope():
    from app.main import now
    from app.models import ParticipantInvitation, PublicAuthSession
    from app.participant_services import resolve_participant_invitation

    with SessionLocal() as db:
        invitation = db.scalar(
            select(ParticipantInvitation).order_by(ParticipantInvitation.id.desc())
        )
        assert invitation is not None

        session_row = PublicAuthSession(
            scope='unrelated_scope',
            session_hash='resolver-no-auth-check',
            participant_invitation_id=invitation.id,
            expires_at=now() - timedelta(hours=1),
            revoked_at=now(),
        )

        resolved = resolve_participant_invitation(db, session_row)
        assert resolved is not None
        assert resolved.id == invitation.id


def test_invitation_service_token_hash_lookup_success_and_no_match():
    from app.main import now
    from app.models import Participant, ParticipantInvitation, Study
    from app.participant_services import resolve_invitation_by_token
    from app.security import new_token, token_hash

    with SessionLocal() as db:
        user = db.scalar(select(User).order_by(User.id))
        assert user is not None

        participant_row = db.scalar(
            select(Participant)
            .where(Participant.organisation_id == user.organisation_id)
            .order_by(Participant.id)
        )
        assert participant_row is not None

        study_row = db.scalar(
            select(Study)
            .where(Study.organisation_id == user.organisation_id)
            .order_by(Study.id)
        )
        assert study_row is not None

        raw_token = new_token()
        invitation = ParticipantInvitation(
            organisation_id=user.organisation_id,
            participant_id=participant_row.id,
            study_id=study_row.id,
            token_hash=token_hash(raw_token),
            expires_at=now() + timedelta(days=1),
            invited_by_id=user.id,
        )
        db.add(invitation)
        db.flush()

        resolved = resolve_invitation_by_token(db, raw_token)
        assert resolved is not None
        assert resolved.id == invitation.id

        assert resolve_invitation_by_token(db, new_token()) is None


def test_invitation_service_live_lookup_excludes_accepted_revoked_and_expired():
    from app.main import now
    from app.models import Participant, ParticipantInvitation, Study
    from app.participant_services import find_live_unaccepted_invitation
    from app.security import new_token, token_hash

    with SessionLocal() as db:
        user = db.scalar(select(User).order_by(User.id))
        assert user is not None

        study_row = db.scalar(
            select(Study)
            .where(Study.organisation_id == user.organisation_id)
            .order_by(Study.id)
        )
        assert study_row is not None

        def make_participant(suffix: str) -> Participant:
            participant_row = Participant(
                organisation_id=user.organisation_id,
                reference=unique_value(f'INV-{suffix}').upper(),
                name=f'Invitation {suffix}',
                email=f"{unique_value(f'inv-{suffix}')}@example.org",
                status='prospective',
                consent_status='pending',
                communication_preference='email',
                created_by_id=user.id,
            )
            db.add(participant_row)
            db.flush()
            return participant_row

        live_participant = make_participant('live')
        live_invitation = ParticipantInvitation(
            organisation_id=user.organisation_id,
            participant_id=live_participant.id,
            study_id=study_row.id,
            token_hash=token_hash(new_token()),
            expires_at=now() + timedelta(days=2),
            invited_by_id=user.id,
        )
        db.add(live_invitation)
        db.flush()

        accepted_participant = make_participant('accepted')
        db.add(
            ParticipantInvitation(
                organisation_id=user.organisation_id,
                participant_id=accepted_participant.id,
                study_id=study_row.id,
                token_hash=token_hash(new_token()),
                expires_at=now() + timedelta(days=2),
                accepted_at=now(),
                invited_by_id=user.id,
            )
        )

        revoked_participant = make_participant('revoked')
        db.add(
            ParticipantInvitation(
                organisation_id=user.organisation_id,
                participant_id=revoked_participant.id,
                study_id=study_row.id,
                token_hash=token_hash(new_token()),
                expires_at=now() + timedelta(days=2),
                revoked_at=now(),
                invited_by_id=user.id,
            )
        )

        expired_participant = make_participant('expired')
        db.add(
            ParticipantInvitation(
                organisation_id=user.organisation_id,
                participant_id=expired_participant.id,
                study_id=study_row.id,
                token_hash=token_hash(new_token()),
                expires_at=now() - timedelta(minutes=1),
                invited_by_id=user.id,
            )
        )
        db.flush()

        assert (
            find_live_unaccepted_invitation(db, study_row.id, live_participant.id, now()).id
            == live_invitation.id
        )
        assert (
            find_live_unaccepted_invitation(db, study_row.id, accepted_participant.id, now())
            is None
        )
        assert (
            find_live_unaccepted_invitation(db, study_row.id, revoked_participant.id, now())
            is None
        )
        assert (
            find_live_unaccepted_invitation(db, study_row.id, expired_participant.id, now())
            is None
        )


def test_invitation_service_org_scoped_lookup_blocks_other_organisation():
    from app.main import now
    from app.models import Organisation, Participant, ParticipantInvitation, Study
    from app.participant_services import resolve_org_scoped_invitation
    from app.security import new_token, token_hash

    with SessionLocal() as db:
        owner = db.scalar(select(User).where(User.email == 'admin@politis.local'))
        assert owner is not None

        study_row = db.scalar(
            select(Study)
            .where(Study.organisation_id == owner.organisation_id)
            .order_by(Study.id)
        )
        participant_row = db.scalar(
            select(Participant)
            .where(Participant.organisation_id == owner.organisation_id)
            .order_by(Participant.id)
        )
        assert study_row is not None
        assert participant_row is not None

        invitation = ParticipantInvitation(
            organisation_id=owner.organisation_id,
            participant_id=participant_row.id,
            study_id=study_row.id,
            token_hash=token_hash(new_token()),
            expires_at=now() + timedelta(days=1),
            invited_by_id=owner.id,
        )
        db.add(invitation)
        db.flush()

        other_org = Organisation(
            name=unique_value('Invitation scope org'),
            slug=unique_value('invitation-scope-org').lower(),
        )
        db.add(other_org)
        db.flush()

        assert resolve_org_scoped_invitation(db, owner.organisation_id, invitation.id) is not None
        assert resolve_org_scoped_invitation(db, other_org.id, invitation.id) is None


def test_invitation_service_mark_revoked_sets_timestamp():
    from app.main import now
    from app.models import Participant, ParticipantInvitation, Study
    from app.participant_services import mark_invitation_revoked
    from app.security import new_token, token_hash

    with SessionLocal() as db:
        user = db.scalar(select(User).order_by(User.id))
        assert user is not None

        study_row = db.scalar(
            select(Study)
            .where(Study.organisation_id == user.organisation_id)
            .order_by(Study.id)
        )
        participant_row = db.scalar(
            select(Participant)
            .where(Participant.organisation_id == user.organisation_id)
            .order_by(Participant.id)
        )
        assert study_row is not None
        assert participant_row is not None

        invitation = ParticipantInvitation(
            organisation_id=user.organisation_id,
            participant_id=participant_row.id,
            study_id=study_row.id,
            token_hash=token_hash(new_token()),
            expires_at=now() + timedelta(days=1),
            invited_by_id=user.id,
        )
        db.add(invitation)
        db.flush()

        revoked_at = now()
        mark_invitation_revoked(invitation, revoked_at)
        assert invitation.revoked_at == revoked_at


def test_invitation_routes_preserve_invite_revoke_resend_behaviour():
    from app.models import ParticipantInvitation

    with client:
        auth()
        participant_response = post_with_csrf(
            '/participants',
            data={
                'reference': unique_value('ROUTE-P').upper(),
                'name': 'Route Behaviour Participant',
                'email': f"{unique_value('route-behaviour')}@example.org",
                'phone': '',
                'status_value': 'prospective',
                'consent_status': 'pending',
                'communication_preference': 'email',
                'tags': '',
                'notes': '',
            },
            follow_redirects=False,
        )
        assert participant_response.status_code == 303
        participant_id = int(participant_response.headers['location'].rsplit('/', 1)[-1])

        studies_page = client.get('/studies')
        study_id = int(studies_page.text.split('/studies/')[1].split('"')[0])

        enrol = post_with_csrf(
            f'/studies/{study_id}/enrol',
            data={'participant_id': participant_id},
            follow_redirects=False,
        )
        assert enrol.status_code == 303

        first_invite = post_with_csrf(
            f'/studies/{study_id}/invite/{participant_id}',
            follow_redirects=False,
        )
        assert first_invite.status_code == 303

        duplicate_invite = post_with_csrf(
            f'/studies/{study_id}/invite/{participant_id}',
            follow_redirects=False,
        )
        assert duplicate_invite.status_code == 400
        assert 'A live invitation already exists' in duplicate_invite.text

        with SessionLocal() as db:
            active_invitation = db.scalar(
                select(ParticipantInvitation)
                .where(
                    ParticipantInvitation.study_id == study_id,
                    ParticipantInvitation.participant_id == participant_id,
                    ParticipantInvitation.revoked_at.is_(None),
                )
                .order_by(ParticipantInvitation.id.desc())
            )
            assert active_invitation is not None
            invitation_id = active_invitation.id

        revoke = post_with_csrf(
            f'/participant-invitations/{invitation_id}/revoke',
            follow_redirects=False,
        )
        assert revoke.status_code == 303

        resend = post_with_csrf(
            f'/participant-invitations/{invitation_id}/resend',
            follow_redirects=False,
        )
        assert resend.status_code == 303

        with SessionLocal() as db:
            invitations = db.scalars(
                select(ParticipantInvitation)
                .where(
                    ParticipantInvitation.study_id == study_id,
                    ParticipantInvitation.participant_id == participant_id,
                )
                .order_by(ParticipantInvitation.id.asc())
            ).all()
            assert len(invitations) >= 2
            assert invitations[-1].id != invitation_id
            assert invitations[-1].revoked_at is None


def test_grant_participant_consent_sets_accepted_at_when_absent():
    from app.main import now
    from app.models import Participant, ParticipantInvitation, Study
    from app.participant_services import grant_participant_consent
    from app.security import new_token, token_hash

    with SessionLocal() as db:
        user = db.scalar(select(User).order_by(User.id))
        assert user is not None

        participant_row = Participant(
            organisation_id=user.organisation_id,
            reference=unique_value('CONSENT-SET').upper(),
            name='Consent Set',
            email=f"{unique_value('consent-set')}@example.org",
            status='prospective',
            consent_status='pending',
            communication_preference='email',
            created_by_id=user.id,
        )
        db.add(participant_row)
        db.flush()

        study_row = db.scalar(
            select(Study)
            .where(Study.organisation_id == user.organisation_id)
            .order_by(Study.id)
        )
        assert study_row is not None

        invitation = ParticipantInvitation(
            organisation_id=user.organisation_id,
            participant_id=participant_row.id,
            study_id=study_row.id,
            token_hash=token_hash(new_token()),
            expires_at=now() + timedelta(days=1),
            invited_by_id=user.id,
            accepted_at=None,
        )
        db.add(invitation)
        db.flush()

        accepted_at = now()
        grant_participant_consent(invitation, participant_row, accepted_at)

        assert invitation.accepted_at == accepted_at


def test_grant_participant_consent_preserves_existing_accepted_at():
    from app.main import now
    from app.models import Participant, ParticipantInvitation, Study
    from app.participant_services import grant_participant_consent
    from app.security import new_token, token_hash

    with SessionLocal() as db:
        user = db.scalar(select(User).order_by(User.id))
        assert user is not None

        participant_row = Participant(
            organisation_id=user.organisation_id,
            reference=unique_value('CONSENT-PRESERVE').upper(),
            name='Consent Preserve',
            email=f"{unique_value('consent-preserve')}@example.org",
            status='invited',
            consent_status='pending',
            communication_preference='email',
            created_by_id=user.id,
        )
        db.add(participant_row)
        db.flush()

        study_row = db.scalar(
            select(Study)
            .where(Study.organisation_id == user.organisation_id)
            .order_by(Study.id)
        )
        assert study_row is not None

        existing_accepted_at = now() - timedelta(hours=2)
        invitation = ParticipantInvitation(
            organisation_id=user.organisation_id,
            participant_id=participant_row.id,
            study_id=study_row.id,
            token_hash=token_hash(new_token()),
            expires_at=now() + timedelta(days=1),
            invited_by_id=user.id,
            accepted_at=existing_accepted_at,
        )
        db.add(invitation)
        db.flush()

        grant_participant_consent(invitation, participant_row, now())

        assert invitation.accepted_at == existing_accepted_at


def test_grant_participant_consent_sets_active_and_granted_statuses():
    from app.main import now
    from app.models import Participant, ParticipantInvitation, Study
    from app.participant_services import grant_participant_consent
    from app.security import new_token, token_hash

    with SessionLocal() as db:
        user = db.scalar(select(User).order_by(User.id))
        assert user is not None

        participant_row = Participant(
            organisation_id=user.organisation_id,
            reference=unique_value('CONSENT-STATUS').upper(),
            name='Consent Status',
            email=f"{unique_value('consent-status')}@example.org",
            status='prospective',
            consent_status='pending',
            communication_preference='email',
            created_by_id=user.id,
        )
        db.add(participant_row)
        db.flush()

        study_row = db.scalar(
            select(Study)
            .where(Study.organisation_id == user.organisation_id)
            .order_by(Study.id)
        )
        assert study_row is not None

        invitation = ParticipantInvitation(
            organisation_id=user.organisation_id,
            participant_id=participant_row.id,
            study_id=study_row.id,
            token_hash=token_hash(new_token()),
            expires_at=now() + timedelta(days=1),
            invited_by_id=user.id,
        )
        db.add(invitation)
        db.flush()

        grant_participant_consent(invitation, participant_row, now())

        assert participant_row.status == 'active'
        assert participant_row.consent_status == 'granted'


def test_grant_participant_consent_performs_no_commit_by_itself():
    from app.main import now
    from app.models import Participant, ParticipantInvitation, Study
    from app.participant_services import grant_participant_consent
    from app.security import new_token, token_hash

    with SessionLocal() as db:
        user = db.scalar(select(User).order_by(User.id))
        assert user is not None

        participant_row = Participant(
            organisation_id=user.organisation_id,
            reference=unique_value('CONSENT-NOCOMMIT').upper(),
            name='Consent No Commit',
            email=f"{unique_value('consent-nocommit')}@example.org",
            status='prospective',
            consent_status='pending',
            communication_preference='email',
            created_by_id=user.id,
        )
        db.add(participant_row)
        db.flush()

        study_row = db.scalar(
            select(Study)
            .where(Study.organisation_id == user.organisation_id)
            .order_by(Study.id)
        )
        assert study_row is not None

        invitation = ParticipantInvitation(
            organisation_id=user.organisation_id,
            participant_id=participant_row.id,
            study_id=study_row.id,
            token_hash=token_hash(new_token()),
            expires_at=now() + timedelta(days=1),
            invited_by_id=user.id,
        )
        db.add(invitation)
        db.commit()
        participant_id = participant_row.id
        invitation_id = invitation.id

    with SessionLocal() as db:
        invitation = db.get(ParticipantInvitation, invitation_id)
        participant_row = db.get(Participant, participant_id)
        assert invitation is not None
        assert participant_row is not None
        grant_participant_consent(invitation, participant_row, now())
        db.rollback()

    with SessionLocal() as db:
        invitation = db.get(ParticipantInvitation, invitation_id)
        participant_row = db.get(Participant, participant_id)
        assert invitation is not None
        assert participant_row is not None
        assert invitation.accepted_at is None
        assert participant_row.status == 'prospective'
        assert participant_row.consent_status == 'pending'


def test_join_study_post_preserves_consent_rejection_and_acceptance_flow():
    from app.models import AuditEvent, OutboxEmail, Participant, ParticipantInvitation
    from app.security import token_hash

    with client:
        auth()
        p = post_with_csrf(
            '/participants',
            data={
                'reference': unique_value('CONSENT-ROUTE').upper(),
                'name': 'Consent Route Participant',
                'email': f"{unique_value('consent-route')}@example.org",
                'phone': '',
                'status_value': 'prospective',
                'consent_status': 'pending',
                'communication_preference': 'email',
                'tags': '',
                'notes': '',
            },
            follow_redirects=False,
        )
        assert p.status_code == 303
        participant_id = int(p.headers['location'].rsplit('/', 1)[-1])

        studies_page = client.get('/studies')
        study_id = int(studies_page.text.split('/studies/')[1].split('"')[0])

        post_with_csrf(
            f'/studies/{study_id}/enrol',
            data={'participant_id': participant_id},
            follow_redirects=False,
        )
        post_with_csrf(
            f'/studies/{study_id}/invite/{participant_id}',
            follow_redirects=False,
        )

        with SessionLocal() as db:
            email = db.scalar(
                select(OutboxEmail)
                .where(OutboxEmail.recipient.like('%consent-route%@example.org'))
                .order_by(OutboxEmail.id.desc())
            )
            assert email is not None
            token = email.body.split('token=')[1].strip()

        exchange = client.get(f'/join-study?token={token}', follow_redirects=False)
        assert exchange.status_code == 303

        rejected = post_with_csrf('/join-study', data={'consent': ''}, follow_redirects=False)
        assert rejected.status_code == 400
        assert 'Consent is required.' in rejected.text

        accepted = post_with_csrf('/join-study', data={'consent': 'true'}, follow_redirects=False)
        assert accepted.status_code == 303
        assert accepted.headers['location'] == '/participant-portal'

        with SessionLocal() as db:
            invitation = db.scalar(
                select(ParticipantInvitation)
                .where(ParticipantInvitation.token_hash == token_hash(token))
            )
            participant_row = db.get(Participant, participant_id)
            assert invitation is not None
            assert participant_row is not None
            assert invitation.accepted_at is not None
            assert participant_row.status == 'active'
            assert participant_row.consent_status == 'granted'
            audit_event = db.scalar(
                select(AuditEvent)
                .where(
                    AuditEvent.action == 'participant.invitation_accepted',
                    AuditEvent.organisation_id == invitation.organisation_id,
                    AuditEvent.actor_user_id.is_(None),
                    AuditEvent.entity_type == 'participant',
                    AuditEvent.entity_id == str(participant_id),
                )
                .order_by(AuditEvent.id.desc())
            )
            assert audit_event is not None


def test_response_service_lookup_success_and_no_match():
    from app.models import Activity, ActivityResponse, Participant
    from app.participant_services import resolve_activity_response

    with SessionLocal() as db:
        activity_row = db.scalar(select(Activity).order_by(Activity.id.asc()))
        assert activity_row is not None
        actor = db.scalar(
            select(User)
            .where(User.organisation_id == activity_row.organisation_id)
            .order_by(User.id.asc())
        )
        assert actor is not None

        participant_row = Participant(
            organisation_id=activity_row.organisation_id,
            reference=unique_value('RESP-LOOKUP').upper(),
            name='Response Lookup',
            email=f"{unique_value('response-lookup')}@example.org",
            status='active',
            consent_status='granted',
            communication_preference='email',
            created_by_id=actor.id,
        )
        db.add(participant_row)
        db.flush()

        response = ActivityResponse(
            organisation_id=activity_row.organisation_id,
            study_id=activity_row.study_id,
            activity_id=activity_row.id,
            participant_id=participant_row.id,
            value_json='{}',
            status='draft',
        )
        db.add(response)
        db.flush()

        found = resolve_activity_response(db, activity_row.id, participant_row.id)
        assert found is not None
        assert found.id == response.id

        assert resolve_activity_response(db, activity_row.id, participant_row.id + 999999) is None


def test_response_service_create_sets_foreign_keys():
    from app.models import Activity, Participant
    from app.participant_services import resolve_or_create_activity_response

    with SessionLocal() as db:
        activity_row = db.scalar(select(Activity).order_by(Activity.id.asc()))
        assert activity_row is not None
        actor = db.scalar(
            select(User)
            .where(User.organisation_id == activity_row.organisation_id)
            .order_by(User.id.asc())
        )
        assert actor is not None

        participant_row = Participant(
            organisation_id=activity_row.organisation_id,
            reference=unique_value('RESP-CREATE').upper(),
            name='Response Create',
            email=f"{unique_value('response-create')}@example.org",
            status='active',
            consent_status='granted',
            communication_preference='email',
            created_by_id=actor.id,
        )
        db.add(participant_row)
        db.flush()

        response = resolve_or_create_activity_response(
            db,
            organisation_id=activity_row.organisation_id,
            study_id=activity_row.study_id,
            activity_id=activity_row.id,
            participant_id=participant_row.id,
        )

        assert response.organisation_id == activity_row.organisation_id
        assert response.study_id == activity_row.study_id
        assert response.activity_id == activity_row.id
        assert response.participant_id == participant_row.id


def test_response_service_payload_serialization_shape_is_unchanged():
    from app.participant_services import serialise_response_payload

    value, choice_list = serialise_response_payload('final answer', '  one |two| | three  ')

    assert choice_list == ['one', 'two', 'three']
    assert value == {'answer': 'final answer', 'choices': ['one', 'two', 'three']}


def test_response_service_apply_action_draft_and_submit_status_and_submitted_at():
    from app.main import now
    from app.models import Activity, ActivityResponse, Participant
    from app.participant_services import apply_response_action

    with SessionLocal() as db:
        activity_row = db.scalar(select(Activity).order_by(Activity.id.asc()))
        assert activity_row is not None
        actor = db.scalar(
            select(User)
            .where(User.organisation_id == activity_row.organisation_id)
            .order_by(User.id.asc())
        )
        assert actor is not None

        participant_row = Participant(
            organisation_id=activity_row.organisation_id,
            reference=unique_value('RESP-ACTION').upper(),
            name='Response Action',
            email=f"{unique_value('response-action')}@example.org",
            status='active',
            consent_status='granted',
            communication_preference='email',
            created_by_id=actor.id,
        )
        db.add(participant_row)
        db.flush()

        response = ActivityResponse(
            organisation_id=activity_row.organisation_id,
            study_id=activity_row.study_id,
            activity_id=activity_row.id,
            participant_id=participant_row.id,
            value_json='{}',
            status='draft',
        )
        db.add(response)
        db.flush()

        apply_response_action(response, {'answer': 'draft', 'choices': []}, 'draft', now())
        assert response.status == 'draft'
        assert response.submitted_at is None

        submitted_at = now()
        apply_response_action(response, {'answer': 'submit', 'choices': ['a']}, 'submit', submitted_at)
        assert response.status == 'submitted'
        assert response.submitted_at == submitted_at


def test_response_service_submit_overwrites_existing_submitted_at_current_behavior():
    from app.main import now
    from app.models import Activity, ActivityResponse, Participant
    from app.participant_services import apply_response_action

    with SessionLocal() as db:
        activity_row = db.scalar(select(Activity).order_by(Activity.id.asc()))
        assert activity_row is not None
        actor = db.scalar(
            select(User)
            .where(User.organisation_id == activity_row.organisation_id)
            .order_by(User.id.asc())
        )
        assert actor is not None

        participant_row = Participant(
            organisation_id=activity_row.organisation_id,
            reference=unique_value('RESP-TIMESTAMP').upper(),
            name='Response Timestamp',
            email=f"{unique_value('response-timestamp')}@example.org",
            status='active',
            consent_status='granted',
            communication_preference='email',
            created_by_id=actor.id,
        )
        db.add(participant_row)
        db.flush()

        old_submitted_at = now() - timedelta(hours=6)
        response = ActivityResponse(
            organisation_id=activity_row.organisation_id,
            study_id=activity_row.study_id,
            activity_id=activity_row.id,
            participant_id=participant_row.id,
            value_json='{}',
            status='submitted',
            submitted_at=old_submitted_at,
        )
        db.add(response)
        db.flush()

        new_submitted_at = now()
        apply_response_action(response, {'answer': 'new', 'choices': []}, 'submit', new_submitted_at)
        assert response.submitted_at == new_submitted_at
        assert response.submitted_at != old_submitted_at


def test_response_service_helpers_do_not_commit():
    from app.main import now
    from app.models import Activity, ActivityResponse, Participant
    from app.participant_services import apply_response_action, resolve_or_create_activity_response

    with SessionLocal() as db:
        activity_row = db.scalar(select(Activity).order_by(Activity.id.asc()))
        assert activity_row is not None
        actor = db.scalar(
            select(User)
            .where(User.organisation_id == activity_row.organisation_id)
            .order_by(User.id.asc())
        )
        assert actor is not None

        participant_row = Participant(
            organisation_id=activity_row.organisation_id,
            reference=unique_value('RESP-NOCOMMIT').upper(),
            name='Response No Commit',
            email=f"{unique_value('response-no-commit')}@example.org",
            status='active',
            consent_status='granted',
            communication_preference='email',
            created_by_id=actor.id,
        )
        db.add(participant_row)
        db.commit()
        participant_id = participant_row.id
        activity_id = activity_row.id

    with SessionLocal() as db:
        activity_row = db.get(Activity, activity_id)
        assert activity_row is not None
        response = resolve_or_create_activity_response(
            db,
            organisation_id=activity_row.organisation_id,
            study_id=activity_row.study_id,
            activity_id=activity_row.id,
            participant_id=participant_id,
        )
        apply_response_action(response, {'answer': 'temp', 'choices': []}, 'submit', now())
        db.rollback()

    with SessionLocal() as db:
        response = db.scalar(
            select(ActivityResponse).where(
                ActivityResponse.activity_id == activity_id,
                ActivityResponse.participant_id == participant_id,
            )
        )
        assert response is None


def test_participant_portal_route_preserves_draft_then_submit_response_behavior():
    from app.models import Activity, ActivityResponse, OutboxEmail

    with client:
        auth()
        participant_created = post_with_csrf(
            '/participants',
            data={
                'reference': unique_value('RESP-ROUTE').upper(),
                'name': 'Route Response Participant',
                'email': f"{unique_value('route-response')}@example.org",
                'phone': '',
                'status_value': 'prospective',
                'consent_status': 'pending',
                'communication_preference': 'email',
                'tags': '',
                'notes': '',
            },
            follow_redirects=False,
        )
        participant_id = int(participant_created.headers['location'].rsplit('/', 1)[-1])

        with SessionLocal() as db:
            first_activity = db.scalar(select(Activity).order_by(Activity.id.asc()))
            assert first_activity is not None
            study_id = first_activity.study_id
            activity_id = first_activity.id

        post_with_csrf(f'/studies/{study_id}/enrol', data={'participant_id': participant_id})
        post_with_csrf(f'/studies/{study_id}/invite/{participant_id}')

        with SessionLocal() as db:
            email = db.scalar(
                select(OutboxEmail)
                .where(OutboxEmail.recipient.like('%route-response%@example.org'))
                .order_by(OutboxEmail.id.desc())
            )
            assert email is not None
            token = email.body.split('token=')[1].strip()

        client.get(f'/join-study?token={token}')
        post_with_csrf('/join-study', data={'consent': 'true'})

        draft = post_with_csrf(
            f'/participant-portal/activity/{activity_id}',
            data={'action': 'draft', 'answer': 'draft only'},
            follow_redirects=False,
        )
        assert draft.status_code == 303

        with SessionLocal() as db:
            response = db.scalar(
                select(ActivityResponse).where(
                    ActivityResponse.activity_id == activity_id,
                    ActivityResponse.participant_id == participant_id,
                )
            )
            assert response is not None
            assert response.status == 'draft'
            assert response.submitted_at is None

        submit = post_with_csrf(
            f'/participant-portal/activity/{activity_id}',
            data={'action': 'submit', 'answer': 'final answer'},
            follow_redirects=False,
        )
        assert submit.status_code == 303

        with SessionLocal() as db:
            response = db.scalar(
                select(ActivityResponse).where(
                    ActivityResponse.activity_id == activity_id,
                    ActivityResponse.participant_id == participant_id,
                )
            )
            assert response is not None
            assert response.status == 'submitted'
            assert response.submitted_at is not None
            assert 'final answer' in response.value_json


def test_participant_portal_route_preserves_evidence_upload_response_association():
    import json
    from io import BytesIO
    from app.models import Activity, ActivityResponse, EvidenceFile, OutboxEmail

    with client:
        auth()
        participant_created = post_with_csrf(
            '/participants',
            data={
                'reference': unique_value('RESP-UPLOAD').upper(),
                'name': 'Upload Response Participant',
                'email': f"{unique_value('route-upload')}@example.org",
                'phone': '',
                'status_value': 'prospective',
                'consent_status': 'pending',
                'communication_preference': 'email',
                'tags': '',
                'notes': '',
            },
            follow_redirects=False,
        )
        participant_id = int(participant_created.headers['location'].rsplit('/', 1)[-1])

        with SessionLocal() as db:
            first_activity = db.scalar(select(Activity).order_by(Activity.id.asc()))
            assert first_activity is not None
            study_id = first_activity.study_id
            activity_id = first_activity.id

        post_with_csrf(f'/studies/{study_id}/enrol', data={'participant_id': participant_id})
        post_with_csrf(f'/studies/{study_id}/invite/{participant_id}')

        with SessionLocal() as db:
            email = db.scalar(
                select(OutboxEmail)
                .where(OutboxEmail.recipient.like('%route-upload%@example.org'))
                .order_by(OutboxEmail.id.desc())
            )
            assert email is not None
            token = email.body.split('token=')[1].strip()

        client.get(f'/join-study?token={token}')
        post_with_csrf('/join-study', data={'consent': 'true'})

        uploaded = post_with_csrf(
            f'/participant-portal/activity/{activity_id}',
            data={'action': 'submit', 'answer': ''},
            files={'upload': ('evidence.txt', BytesIO(b'ordinary evidence'), 'text/plain')},
            follow_redirects=False,
        )
        assert uploaded.status_code == 303

        with SessionLocal() as db:
            response = db.scalar(
                select(ActivityResponse).where(
                    ActivityResponse.activity_id == activity_id,
                    ActivityResponse.participant_id == participant_id,
                )
            )
            evidence = db.scalar(
                select(EvidenceFile).where(
                    EvidenceFile.activity_id == activity_id,
                    EvidenceFile.participant_id == participant_id,
                )
            )
            assert response is not None
            assert evidence is not None
            assert evidence.response_id == response.id
            payload = json.loads(response.value_json)
            assert payload.get('evidence_id') == evidence.id


def test_evidence_service_build_record_preserves_all_fields():
    from app.participant_services import build_evidence_file

    evidence = build_evidence_file(
        organisation_id=10,
        study_id=20,
        activity_id=30,
        participant_id=40,
        response_id=50,
        original_name='proof.txt',
        stored_name='abc123.txt',
        content_type='text/plain',
        size_bytes=123,
        sha256_hex='f' * 64,
        scan_status='pending',
        scan_detail='Awaiting Microsoft Defender for Storage on-upload scan.',
        storage_provider='local',
        blob_uri='https://example.invalid/blob',
    )

    assert evidence.organisation_id == 10
    assert evidence.study_id == 20
    assert evidence.activity_id == 30
    assert evidence.participant_id == 40
    assert evidence.response_id == 50
    assert evidence.original_name == 'proof.txt'
    assert evidence.stored_name == 'abc123.txt'
    assert evidence.content_type == 'text/plain'
    assert evidence.size_bytes == 123
    assert evidence.sha256_hex == 'f' * 64
    assert evidence.scan_status == 'pending'
    assert evidence.scan_detail == 'Awaiting Microsoft Defender for Storage on-upload scan.'
    assert evidence.storage_provider == 'local'
    assert evidence.blob_uri == 'https://example.invalid/blob'


def test_evidence_service_org_scoped_lookup_returns_none_for_other_org():
    from app.models import Activity, EvidenceFile, Organisation, Participant, Study
    from app.participant_services import resolve_org_scoped_evidence

    with SessionLocal() as db:
        owner = db.scalar(select(User).where(User.email == 'admin@politis.local'))
        assert owner is not None
        study_row = db.scalar(
            select(Study)
            .where(Study.organisation_id == owner.organisation_id)
            .order_by(Study.id.asc())
        )
        activity_row = db.scalar(
            select(Activity)
            .where(Activity.study_id == study_row.id)
            .order_by(Activity.id.asc())
        )
        participant_row = Participant(
            organisation_id=owner.organisation_id,
            reference=unique_value('EVID-SCOPE').upper(),
            name='Evidence Scope Participant',
            email=None,
            phone=None,
            status='prospective',
            consent_status='pending',
            communication_preference='email',
            tags='',
            demographics_json='{}',
            notes='',
            created_by_id=owner.id,
        )
        db.add(participant_row)
        db.flush()
        evidence = EvidenceFile(
            organisation_id=owner.organisation_id,
            study_id=study_row.id,
            activity_id=activity_row.id,
            participant_id=participant_row.id,
            response_id=None,
            original_name='scope.txt',
            stored_name=f"{unique_value('scope-file')}.txt",
            content_type='text/plain',
            size_bytes=1,
            sha256_hex='0' * 64,
            scan_status='pending',
            scan_detail='',
            storage_provider='local',
            blob_uri='',
        )
        db.add(evidence)
        db.flush()
        other_org = Organisation(
            name=unique_value('Evidence Org'),
            slug=unique_value('evidence-org').lower(),
        )
        db.add(other_org)
        db.flush()

        assert resolve_org_scoped_evidence(db, owner.organisation_id, evidence.id) is not None
        assert resolve_org_scoped_evidence(db, other_org.id, evidence.id) is None


@pytest.mark.parametrize('scan_status', ['pending', 'infected', 'failed', 'unknown', 'not_scanned', 'scan_failed'])
def test_evidence_service_downloadable_only_for_clean(scan_status):
    from app.participant_services import is_evidence_downloadable

    assert is_evidence_downloadable(scan_status) is False
    assert is_evidence_downloadable('clean') is True


def test_messaging_service_builders_preserve_sender_semantics():
    from app.models import Participant, ParticipantInvitation, Study
    from app.participant_services import create_participant_message, create_researcher_message

    with SessionLocal() as db:
        owner = db.scalar(select(User).where(User.email == 'admin@politis.local'))
        assert owner is not None
        study_row = db.scalar(
            select(Study)
            .where(Study.organisation_id == owner.organisation_id)
            .order_by(Study.id.asc())
        )
        assert study_row is not None
        participant_row = db.scalar(
            select(Participant)
            .where(Participant.organisation_id == owner.organisation_id)
            .order_by(Participant.id.asc())
        )
        assert participant_row is not None

        invitation = ParticipantInvitation(
            organisation_id=owner.organisation_id,
            participant_id=participant_row.id,
            study_id=study_row.id,
            token_hash=unique_value('MSG-TOKEN'),
            expires_at=now() + timedelta(days=1),
            invited_by_id=owner.id,
        )

        participant_message = create_participant_message(invitation, body='  participant hello  ')
        assert participant_message.organisation_id == owner.organisation_id
        assert participant_message.study_id == study_row.id
        assert participant_message.participant_id == participant_row.id
        assert participant_message.sender_type == 'participant'
        assert participant_message.sender_user_id is None
        assert participant_message.body == 'participant hello'

        researcher_message = create_researcher_message(
            organisation_id=owner.organisation_id,
            study_id=study_row.id,
            participant_id=participant_row.id,
            sender_user_id=owner.id,
            body='  researcher hello  ',
            internal_note=True,
        )
        assert researcher_message.organisation_id == owner.organisation_id
        assert researcher_message.study_id == study_row.id
        assert researcher_message.participant_id == participant_row.id
        assert researcher_message.sender_type == 'researcher'
        assert researcher_message.sender_user_id == owner.id
        assert researcher_message.body == 'researcher hello'
        assert researcher_message.internal_note is True


def test_messaging_service_visible_lookup_excludes_internal_notes_and_orders_created_at():
    from app.models import Participant, ParticipantMessage, Study
    from app.participant_services import list_participant_visible_messages

    with SessionLocal() as db:
        owner = db.scalar(select(User).where(User.email == 'admin@politis.local'))
        assert owner is not None
        study_row = db.scalar(
            select(Study)
            .where(Study.organisation_id == owner.organisation_id)
            .order_by(Study.id.asc())
        )
        assert study_row is not None
        participant_row = db.scalar(
            select(Participant)
            .where(Participant.organisation_id == owner.organisation_id)
            .order_by(Participant.id.asc())
        )
        assert participant_row is not None

        public_early = ParticipantMessage(
            organisation_id=owner.organisation_id,
            study_id=study_row.id,
            participant_id=participant_row.id,
            sender_type='participant',
            body=unique_value('PUBLIC-EARLY'),
            created_at=now() - timedelta(minutes=2),
        )
        internal = ParticipantMessage(
            organisation_id=owner.organisation_id,
            study_id=study_row.id,
            participant_id=participant_row.id,
            sender_type='researcher',
            sender_user_id=owner.id,
            body=unique_value('INTERNAL'),
            internal_note=True,
            created_at=now() - timedelta(minutes=1),
        )
        public_late = ParticipantMessage(
            organisation_id=owner.organisation_id,
            study_id=study_row.id,
            participant_id=participant_row.id,
            sender_type='researcher',
            sender_user_id=owner.id,
            body=unique_value('PUBLIC-LATE'),
            internal_note=False,
            created_at=now(),
        )

        db.add_all([public_late, internal, public_early])
        db.flush()

        visible = list_participant_visible_messages(
            db,
            study_id=study_row.id,
            participant_id=participant_row.id,
        )

        visible_ids = [row.id for row in visible]
        assert public_early.id in visible_ids
        assert public_late.id in visible_ids
        assert internal.id not in visible_ids

        public_rows = [row for row in visible if row.id in {public_early.id, public_late.id}]
        assert [row.id for row in public_rows] == [public_early.id, public_late.id]

        db.rollback()


def test_messaging_service_helpers_perform_no_commit_by_themselves():
    from app.models import Participant, ParticipantMessage, Study
    from app.participant_services import create_researcher_message

    marker = unique_value('MSG-NOCOMMIT')

    with SessionLocal() as db:
        owner = db.scalar(select(User).where(User.email == 'admin@politis.local'))
        assert owner is not None
        study_row = db.scalar(
            select(Study)
            .where(Study.organisation_id == owner.organisation_id)
            .order_by(Study.id.asc())
        )
        assert study_row is not None
        participant_row = db.scalar(
            select(Participant)
            .where(Participant.organisation_id == owner.organisation_id)
            .order_by(Participant.id.asc())
        )
        assert participant_row is not None

        message = create_researcher_message(
            organisation_id=owner.organisation_id,
            study_id=study_row.id,
            participant_id=participant_row.id,
            sender_user_id=owner.id,
            body=marker,
            internal_note=False,
        )
        db.add(message)
        db.rollback()

    with SessionLocal() as db:
        persisted = db.scalar(select(ParticipantMessage).where(ParticipantMessage.body == marker))
        assert persisted is None


def test_evidence_service_helpers_perform_no_commit_and_no_storage_access(monkeypatch):
    from app.models import Activity, EvidenceFile, Participant, Study
    from app.participant_services import build_evidence_file

    def fail_storage_access(*_args, **_kwargs):
        raise AssertionError('storage access should not occur')

    monkeypatch.setattr('app.storage.storage.path', fail_storage_access)
    monkeypatch.setattr('app.storage.storage.save_stream', fail_storage_access)

    with SessionLocal() as db:
        owner = db.scalar(select(User).where(User.email == 'admin@politis.local'))
        assert owner is not None
        study_row = db.scalar(
            select(Study)
            .where(Study.organisation_id == owner.organisation_id)
            .order_by(Study.id.asc())
        )
        activity_row = db.scalar(
            select(Activity)
            .where(Activity.study_id == study_row.id)
            .order_by(Activity.id.asc())
        )
        participant_row = Participant(
            organisation_id=owner.organisation_id,
            reference=unique_value('EVID-NOCOMMIT').upper(),
            name='Evidence No Commit',
            email=None,
            phone=None,
            status='prospective',
            consent_status='pending',
            communication_preference='email',
            tags='',
            demographics_json='{}',
            notes='',
            created_by_id=owner.id,
        )
        db.add(participant_row)
        db.commit()
        organisation_id = owner.organisation_id
        participant_id = participant_row.id
        activity_id = activity_row.id
        study_id = study_row.id

    with SessionLocal() as db:
        evidence = build_evidence_file(
            organisation_id=organisation_id,
            study_id=study_id,
            activity_id=activity_id,
            participant_id=participant_id,
            response_id=None,
            original_name='no-commit.txt',
            stored_name='no-commit-key.txt',
            content_type='text/plain',
            size_bytes=10,
            sha256_hex='1' * 64,
            scan_status='pending',
            scan_detail='',
            storage_provider='local',
            blob_uri='',
        )
        db.add(evidence)
        db.rollback()

    with SessionLocal() as db:
        row = db.scalar(
            select(EvidenceFile).where(EvidenceFile.stored_name == 'no-commit-key.txt')
        )
        assert row is None


def test_participant_upload_route_still_creates_identical_evidence_metadata():
    from io import BytesIO
    from app.models import Activity, ActivityResponse, EvidenceFile, OutboxEmail

    with client:
        auth()
        created = post_with_csrf(
            '/participants',
            data={
                'reference': unique_value('EVID-UPLOAD').upper(),
                'name': 'Evidence Upload Participant',
                'email': f"{unique_value('evidence-upload')}@example.org",
                'phone': '',
                'status_value': 'prospective',
                'consent_status': 'pending',
                'communication_preference': 'email',
                'tags': '',
                'notes': '',
            },
            follow_redirects=False,
        )
        participant_id = int(created.headers['location'].rsplit('/', 1)[-1])

        with SessionLocal() as db:
            first_activity = db.scalar(select(Activity).order_by(Activity.id.asc()))
            assert first_activity is not None
            study_id = first_activity.study_id
            activity_id = first_activity.id

        post_with_csrf(f'/studies/{study_id}/enrol', data={'participant_id': participant_id})
        post_with_csrf(f'/studies/{study_id}/invite/{participant_id}')

        with SessionLocal() as db:
            email = db.scalar(
                select(OutboxEmail)
                .where(OutboxEmail.recipient.like('%evidence-upload%@example.org'))
                .order_by(OutboxEmail.id.desc())
            )
            assert email is not None
            token = email.body.split('token=')[1].strip()

        client.get(f'/join-study?token={token}')
        post_with_csrf('/join-study', data={'consent': 'true'})

        uploaded = post_with_csrf(
            f'/participant-portal/activity/{activity_id}',
            data={'action': 'submit', 'answer': ''},
            files={'upload': ('metadata.txt', BytesIO(b'ordinary evidence'), 'text/plain')},
            follow_redirects=False,
        )
        assert uploaded.status_code == 303

        with SessionLocal() as db:
            response = db.scalar(
                select(ActivityResponse).where(
                    ActivityResponse.activity_id == activity_id,
                    ActivityResponse.participant_id == participant_id,
                )
            )
            evidence = db.scalar(
                select(EvidenceFile).where(
                    EvidenceFile.activity_id == activity_id,
                    EvidenceFile.participant_id == participant_id,
                )
            )
            assert response is not None
            assert evidence is not None
            assert evidence.organisation_id == response.organisation_id
            assert evidence.study_id == response.study_id
            assert evidence.activity_id == response.activity_id
            assert evidence.participant_id == response.participant_id
            assert evidence.response_id == response.id
            assert evidence.original_name == 'metadata.txt'
            assert evidence.content_type == 'text/plain'
            assert evidence.size_bytes == len(b'ordinary evidence')
            assert evidence.scan_status == 'not_configured'


def test_clean_evidence_download_remains_authorised_and_downloadable(tmp_path):
    import io
    from app.models import Activity, EvidenceFile, Participant, Study, User
    from app.storage import storage

    original_storage_path = settings.local_storage_path
    try:
        settings.local_storage_path = str(tmp_path)
        with client:
            client.cookies.clear()
            auth()
            with SessionLocal() as db:
                owner = db.scalar(select(User).where(User.email == 'admin@politis.local'))
                study = db.scalar(select(Study).where(Study.organisation_id == owner.organisation_id).order_by(Study.id.asc()))
                activity = db.scalar(select(Activity).where(Activity.study_id == study.id).order_by(Activity.id.asc()))
                participant = Participant(
                    organisation_id=owner.organisation_id,
                    reference=unique_value('EVID-CLEAN').upper(),
                    name='Evidence Clean Participant',
                    email=None,
                    phone=None,
                    status='prospective',
                    consent_status='pending',
                    communication_preference='email',
                    tags='',
                    demographics_json='{}',
                    notes='',
                    created_by_id=owner.id,
                )
                db.add(participant)
                db.flush()
                stored = storage.save_stream(io.BytesIO(b'clean evidence'), 'clean.txt', 1024)
                evidence = EvidenceFile(
                    organisation_id=owner.organisation_id,
                    study_id=study.id,
                    activity_id=activity.id,
                    participant_id=participant.id,
                    response_id=None,
                    original_name='clean.txt',
                    stored_name=stored.key,
                    content_type='text/plain',
                    size_bytes=stored.size,
                    sha256_hex=stored.sha256_hex,
                    scan_status='clean',
                    scan_detail='',
                    storage_provider=stored.provider,
                    blob_uri=stored.uri,
                )
                db.add(evidence)
                db.commit()
                evidence_id = evidence.id

            response = client.get(f'/evidence/{evidence_id}')
            assert response.status_code == 200
            assert response.content == b'clean evidence'
            assert response.headers['content-type'].startswith('text/plain')
    finally:
        settings.local_storage_path = original_storage_path


def _create_participant_invitation_for_api(email_suffix: str = 'api-auth') -> tuple[str, int, int]:
    from app.models import Activity, OutboxEmail

    with client:
        client.cookies.clear()
        auth()
        recipient = f"{unique_value(email_suffix)}@example.org"
        created = post_with_csrf(
            '/participants',
            data={
                'reference': unique_value('APIAUTH').upper(),
                'name': 'Participant API Auth',
            'email': recipient,
                'phone': '',
                'status_value': 'prospective',
                'consent_status': 'pending',
                'communication_preference': 'email',
                'tags': '',
                'notes': '',
            },
            follow_redirects=False,
        )
        participant_id = int(created.headers['location'].rsplit('/', 1)[-1])

        with SessionLocal() as db:
            first_activity = db.scalar(select(Activity).order_by(Activity.id.asc()))
            assert first_activity is not None
            study_id = first_activity.study_id

        post_with_csrf(f'/studies/{study_id}/enrol', data={'participant_id': participant_id})
        post_with_csrf(f'/studies/{study_id}/invite/{participant_id}')

        with SessionLocal() as db:
            email = db.scalar(
                select(OutboxEmail)
                .where(OutboxEmail.recipient == recipient)
                .order_by(OutboxEmail.id.desc())
            )
            assert email is not None
            token = email.body.split('token=')[1].strip()
        return token, participant_id, study_id


def _exchange_participant_api_session(invitation_token: str):
    return client.post(
        '/api/v1/participant/session/exchange',
        json={'invitation_token': invitation_token},
        follow_redirects=False,
    )


def _exchange_participant_api_session_with_payload(payload: dict):
    return client.post(
        '/api/v1/participant/session/exchange',
        json=payload,
        follow_redirects=False,
    )


def test_participant_api_exchange_creates_hashed_bearer_session_without_cookie_and_no_store():
    from app.models import AuditEvent, PublicAuthSession
    from app.participant_api.auth import PARTICIPANT_API_SCOPE
    from app.security import token_hash

    token, _participant_id, _study_id = _create_participant_invitation_for_api('api-auth-hash')

    with client:
        response = _exchange_participant_api_session(token)
        assert response.status_code == 200
        assert response.headers.get('cache-control') == 'no-store'
        assert 'public_auth_session=' not in (response.headers.get('set-cookie') or '')

        payload = response.json()
        raw_api_token = payload['session']['access_token']
        assert payload['session']['token_type'] == 'Bearer'
        assert payload['next_action'] == 'consent_required'

    with SessionLocal() as db:
        row = db.scalar(
            select(PublicAuthSession)
            .where(PublicAuthSession.scope == PARTICIPANT_API_SCOPE)
            .order_by(PublicAuthSession.id.desc())
        )
        assert row is not None
        assert row.session_hash == token_hash(raw_api_token)
        assert row.session_hash != raw_api_token
        event = db.scalar(
            select(AuditEvent)
            .where(AuditEvent.action == 'participant.api_session_exchanged')
            .order_by(AuditEvent.id.desc())
        )
        assert event is not None
        assert raw_api_token not in (event.detail or '')


def test_participant_api_exchange_rejects_unknown_expired_and_revoked_invitation_tokens():
    from app.models import ParticipantInvitation
    from app.security import token_hash

    token, _participant_id, _study_id = _create_participant_invitation_for_api('api-auth-invalid')

    with client:
        unknown = _exchange_participant_api_session('unknown-token-value')
        assert unknown.status_code == 400

    with SessionLocal() as db:
        invitation = db.scalar(
            select(ParticipantInvitation)
            .where(ParticipantInvitation.token_hash == token_hash(token))
        )
        assert invitation is not None
        invitation.expires_at = now() - timedelta(minutes=1)
        db.commit()

    with client:
        expired = _exchange_participant_api_session(token)
        assert expired.status_code == 400

    token_2, _participant_id, _study_id = _create_participant_invitation_for_api('api-auth-revoked')
    with SessionLocal() as db:
        invitation_2 = db.scalar(
            select(ParticipantInvitation)
            .where(ParticipantInvitation.token_hash == token_hash(token_2))
        )
        assert invitation_2 is not None
        invitation_2.revoked_at = now()
        db.commit()

    with client:
        revoked = _exchange_participant_api_session(token_2)
        assert revoked.status_code == 400


def test_participant_api_exchange_replay_returns_conflict_and_does_not_mint_second_token():
    from app.models import ParticipantInvitation, PublicAuthSession
    from app.participant_api.auth import PARTICIPANT_API_SCOPE
    from app.security import token_hash

    token, _participant_id, _study_id = _create_participant_invitation_for_api('api-auth-reuse')
    with client:
        first = _exchange_participant_api_session(token)
        second = _exchange_participant_api_session(token)
        assert first.status_code == 200
        assert second.status_code == 409
        assert second.json() == {'detail': 'A participant API session is already active for this invitation.'}

    with SessionLocal() as db:
        invitation = db.scalar(
            select(ParticipantInvitation)
            .where(ParticipantInvitation.token_hash == token_hash(token))
        )
        assert invitation is not None
        active_count = db.scalar(
            select(func.count(PublicAuthSession.id)).where(
                PublicAuthSession.scope == PARTICIPANT_API_SCOPE,
                PublicAuthSession.participant_invitation_id == invitation.id,
                PublicAuthSession.revoked_at.is_(None),
                PublicAuthSession.expires_at > now(),
            )
        )
        assert int(active_count or 0) == 1


def test_participant_api_exchange_replay_response_exposes_no_participant_or_token_data():
    token, _participant_id, _study_id = _create_participant_invitation_for_api('api-auth-replay-safe')
    with client:
        first = _exchange_participant_api_session(token)
        assert first.status_code == 200
        replay = _exchange_participant_api_session(token)
        assert replay.status_code == 409
        body = replay.json()
        assert 'participant' not in body
        assert 'session' not in body
        assert 'access_token' not in json.dumps(body)


def test_participant_api_exchange_rate_limit_is_enforced():
    with with_rate_limit_settings(
        rate_limit_enabled=True,
        rate_limit_window_seconds=60,
        rate_limit_invitation_accept_ip=1,
        rate_limit_invitation_accept_token=1,
    ):
        with client:
            first = _exchange_participant_api_session('invalid-token')
            assert first.status_code == 400
            blocked = _exchange_participant_api_session('invalid-token')
            assert blocked.status_code == 429


def test_participant_api_session_requires_valid_bearer_and_excludes_internal_fields():
    token, participant_id, study_id = _create_participant_invitation_for_api('api-auth-session')

    with client:
        exchange = _exchange_participant_api_session(token)
        assert exchange.status_code == 200
        api_token = exchange.json()['session']['access_token']

        missing = client.get('/api/v1/participant/session', follow_redirects=False)
        assert missing.status_code == 401
        assert missing.headers.get('www-authenticate') == 'Bearer'

        malformed = client.get(
            '/api/v1/participant/session',
            headers={'Authorization': 'Bearer'},
            follow_redirects=False,
        )
        assert malformed.status_code == 401
        assert malformed.headers.get('www-authenticate') == 'Bearer'

        invalid = client.get(
            '/api/v1/participant/session',
            headers={'Authorization': 'Bearer invalid-value'},
            follow_redirects=False,
        )
        assert invalid.status_code == 401
        assert invalid.headers.get('www-authenticate') == 'Bearer'

        valid = client.get(
            '/api/v1/participant/session?participant_id=9999',
            headers={'Authorization': f'Bearer {api_token}'},
            follow_redirects=False,
        )
        assert valid.status_code == 200
        assert valid.headers.get('cache-control') == 'no-store'
        body = valid.json()
        assert body['participant']['participant_id'] == participant_id
        assert body['study_scope'] == [study_id]
        assert 'session_hash' not in body
        assert 'token_hash' not in body


def test_participant_api_session_missing_bearer_with_html_accept_preserves_bearer_challenge_and_no_csrf_cookie():
    with client:
        response = client.get(
            '/api/v1/participant/session',
            headers={'Accept': 'text/html'},
            follow_redirects=False,
        )
        assert response.status_code == 401
        assert response.headers.get('www-authenticate') == 'Bearer'
        assert response.headers.get('content-type', '').startswith('application/json')
        assert response.json() == {'detail': 'Invalid or expired participant API credentials.'}
        assert 'csrf_session=' not in (response.headers.get('set-cookie') or '')


def test_participant_api_session_invalid_bearer_with_html_accept_preserves_bearer_challenge():
    with client:
        response = client.get(
            '/api/v1/participant/session',
            headers={
                'Accept': 'text/html',
                'Authorization': 'Bearer invalid-token',
            },
            follow_redirects=False,
        )
        assert response.status_code == 401
        assert response.headers.get('www-authenticate') == 'Bearer'
        assert response.headers.get('content-type', '').startswith('application/json')


def test_non_api_html_error_handling_remains_html_when_accept_requests_html():
    with client:
        response = client.get('/this-page-does-not-exist', headers={'Accept': 'text/html'}, follow_redirects=False)
        assert response.status_code == 404
        assert response.headers.get('content-type', '').startswith('text/html')


def test_participant_api_session_rejects_expired_or_revoked_session_rows():
    from app.models import ParticipantInvitation, PublicAuthSession
    from app.participant_api.auth import PARTICIPANT_API_SCOPE
    from app.security import new_token, token_hash

    invitation_token, _participant_id, _study_id = _create_participant_invitation_for_api('api-auth-expired')
    with client:
        exchange = _exchange_participant_api_session(invitation_token)
        assert exchange.status_code == 200

    with SessionLocal() as db:
        invitation = db.scalar(
            select(ParticipantInvitation).where(ParticipantInvitation.token_hash == token_hash(invitation_token))
        )
        assert invitation is not None
        active_session = db.scalar(
            select(PublicAuthSession).where(
                PublicAuthSession.scope == PARTICIPANT_API_SCOPE,
                PublicAuthSession.participant_invitation_id == invitation.id,
                PublicAuthSession.revoked_at.is_(None),
            )
        )
        assert active_session is not None
        active_session.revoked_at = now()
        expired_raw = new_token()
        db.add(
            PublicAuthSession(
                scope=PARTICIPANT_API_SCOPE,
                session_hash=token_hash(expired_raw),
                participant_invitation_id=invitation.id,
                expires_at=now() - timedelta(minutes=1),
            )
        )
        revoked_raw = new_token()
        db.add(
            PublicAuthSession(
                scope=PARTICIPANT_API_SCOPE,
                session_hash=token_hash(revoked_raw),
                participant_invitation_id=invitation.id,
                expires_at=now() + timedelta(hours=1),
                revoked_at=now(),
            )
        )
        db.commit()

    with client:
        expired = client.get(
            '/api/v1/participant/session',
            headers={'Authorization': f'Bearer {expired_raw}'},
            follow_redirects=False,
        )
        assert expired.status_code == 401
        assert expired.headers.get('www-authenticate') == 'Bearer'
        revoked = client.get(
            '/api/v1/participant/session',
            headers={'Authorization': f'Bearer {revoked_raw}'},
            follow_redirects=False,
        )
        assert revoked.status_code == 401
        assert revoked.headers.get('www-authenticate') == 'Bearer'


def test_participant_api_logout_requires_valid_bearer_and_sets_www_authenticate_header():
    with client:
        missing = client.delete('/api/v1/participant/session', follow_redirects=False)
        assert missing.status_code == 401
        assert missing.headers.get('www-authenticate') == 'Bearer'

        malformed = client.delete(
            '/api/v1/participant/session',
            headers={'Authorization': 'Bearer'},
            follow_redirects=False,
        )
        assert malformed.status_code == 401
        assert malformed.headers.get('www-authenticate') == 'Bearer'

        invalid = client.delete(
            '/api/v1/participant/session',
            headers={'Authorization': 'Bearer invalid-value'},
            follow_redirects=False,
        )
        assert invalid.status_code == 401
        assert invalid.headers.get('www-authenticate') == 'Bearer'


def test_participant_api_logout_revokes_current_session_and_allows_replacement_exchange():
    from app.models import AuditEvent

    token, _participant_id, _study_id = _create_participant_invitation_for_api('api-auth-logout')
    with client:
        session_one = _exchange_participant_api_session(token)
        assert session_one.status_code == 200
        token_one = session_one.json()['session']['access_token']

        logout = client.delete(
            '/api/v1/participant/session',
            headers={'Authorization': f'Bearer {token_one}'},
            follow_redirects=False,
        )
        assert logout.status_code == 200
        assert logout.headers.get('cache-control') == 'no-store'
        assert logout.json()['revoked'] is True

        revoked_use = client.get(
            '/api/v1/participant/session',
            headers={'Authorization': f'Bearer {token_one}'},
            follow_redirects=False,
        )
        assert revoked_use.status_code == 401
        assert revoked_use.headers.get('www-authenticate') == 'Bearer'

        replacement = _exchange_participant_api_session(token)
        assert replacement.status_code == 200
        assert replacement.json()['session']['access_token'] != token_one

    with SessionLocal() as db:
        event = db.scalar(
            select(AuditEvent)
            .where(AuditEvent.action == 'participant.api_session_revoked')
            .order_by(AuditEvent.id.desc())
        )
        assert event is not None
        assert token_one not in (event.detail or '')


def test_participant_api_exchange_allows_replacement_after_expired_session():
    from app.models import ParticipantInvitation, PublicAuthSession
    from app.participant_api.auth import PARTICIPANT_API_SCOPE
    from app.security import token_hash

    token, _participant_id, _study_id = _create_participant_invitation_for_api('api-auth-expire-replace')
    with client:
        first = _exchange_participant_api_session(token)
        assert first.status_code == 200

    with SessionLocal() as db:
        invitation = db.scalar(
            select(ParticipantInvitation).where(ParticipantInvitation.token_hash == token_hash(token))
        )
        assert invitation is not None
        session_row = db.scalar(
            select(PublicAuthSession).where(
                PublicAuthSession.scope == PARTICIPANT_API_SCOPE,
                PublicAuthSession.participant_invitation_id == invitation.id,
                PublicAuthSession.revoked_at.is_(None),
            )
        )
        assert session_row is not None
        session_row.expires_at = now() - timedelta(minutes=1)
        db.commit()

    with client:
        replacement = _exchange_participant_api_session(token)
        assert replacement.status_code == 200

    with SessionLocal() as db:
        invitation = db.scalar(
            select(ParticipantInvitation).where(ParticipantInvitation.token_hash == token_hash(token))
        )
        active_count = db.scalar(
            select(func.count(PublicAuthSession.id)).where(
                PublicAuthSession.scope == PARTICIPANT_API_SCOPE,
                PublicAuthSession.participant_invitation_id == invitation.id,
                PublicAuthSession.revoked_at.is_(None),
                PublicAuthSession.expires_at > now(),
            )
        )
        assert int(active_count or 0) == 1


def test_participant_api_exchange_validation_rejects_empty_overlong_and_unexpected_fields_without_echoing_token_value():
    overlong_token = 't' * 513

    with client:
        empty = _exchange_participant_api_session_with_payload({'invitation_token': ''})
        assert empty.status_code == 422

        overlong = _exchange_participant_api_session_with_payload({'invitation_token': overlong_token})
        assert overlong.status_code == 422

        with_extra = _exchange_participant_api_session_with_payload(
            {
                'invitation_token': 'abc',
                'unexpected': 'value',
            }
        )
        assert with_extra.status_code == 422

        for response in (empty, overlong, with_extra):
            body_text = response.text
            assert overlong_token not in body_text
            assert '"input"' not in body_text


def test_participant_api_exchange_accepts_ios_android_and_app_version_length_40_device_hint():
    token_ios, _participant_id, _study_id = _create_participant_invitation_for_api('api-auth-device-ios')
    token_android, _participant_id_2, _study_id_2 = _create_participant_invitation_for_api('api-auth-device-android')
    token_len40, _participant_id_3, _study_id_3 = _create_participant_invitation_for_api('api-auth-device-len40')

    with client:
        ios = _exchange_participant_api_session_with_payload(
            {
                'invitation_token': token_ios,
                'device_hint': {
                    'platform': 'ios',
                    'app_version': '1.2.3',
                },
            }
        )
        assert ios.status_code == 200

        android = _exchange_participant_api_session_with_payload(
            {
                'invitation_token': token_android,
                'device_hint': {
                    'platform': 'android',
                    'app_version': '2.0.0',
                },
            }
        )
        assert android.status_code == 200

        len_40 = _exchange_participant_api_session_with_payload(
            {
                'invitation_token': token_len40,
                'device_hint': {
                    'platform': 'ios',
                    'app_version': 'v' * 40,
                },
            }
        )
        assert len_40.status_code == 200


def test_participant_api_exchange_rejects_unsupported_platform_and_overlong_device_version_without_echoing_token():
    invalid_platform_token, _participant_id, _study_id = _create_participant_invitation_for_api('api-auth-device-invalid-platform')
    overlong_version_token, _participant_id_2, _study_id_2 = _create_participant_invitation_for_api('api-auth-device-overlong-version')

    with client:
        invalid_platform = _exchange_participant_api_session_with_payload(
            {
                'invitation_token': invalid_platform_token,
                'device_hint': {
                    'platform': 'windows',
                    'app_version': '1.0.0',
                },
            }
        )
        assert invalid_platform.status_code == 422

        overlong_version = _exchange_participant_api_session_with_payload(
            {
                'invitation_token': overlong_version_token,
                'device_hint': {
                    'platform': 'android',
                    'app_version': 'v' * 41,
                },
            }
        )
        assert overlong_version.status_code == 422

        for response, token in (
            (invalid_platform, invalid_platform_token),
            (overlong_version, overlong_version_token),
        ):
            body_text = response.text
            assert token not in body_text
            assert '"input"' not in body_text


def test_participant_api_session_immediately_invalid_when_invitation_is_revoked_or_expired():
    from app.models import ParticipantInvitation
    from app.security import token_hash

    token, _participant_id, _study_id = _create_participant_invitation_for_api('api-auth-invite-revoked')
    with client:
        exchange = _exchange_participant_api_session(token)
        assert exchange.status_code == 200
        api_token = exchange.json()['session']['access_token']

    with SessionLocal() as db:
        invitation = db.scalar(
            select(ParticipantInvitation).where(ParticipantInvitation.token_hash == token_hash(token))
        )
        assert invitation is not None
        invitation.revoked_at = now()
        db.commit()

    with client:
        revoked = client.get(
            '/api/v1/participant/session',
            headers={'Authorization': f'Bearer {api_token}'},
            follow_redirects=False,
        )
        assert revoked.status_code == 401
        assert revoked.headers.get('www-authenticate') == 'Bearer'

    token_2, _participant_id, _study_id = _create_participant_invitation_for_api('api-auth-invite-expired')
    with client:
        exchange_2 = _exchange_participant_api_session(token_2)
        assert exchange_2.status_code == 200
        api_token_2 = exchange_2.json()['session']['access_token']

    with SessionLocal() as db:
        invitation_2 = db.scalar(
            select(ParticipantInvitation).where(ParticipantInvitation.token_hash == token_hash(token_2))
        )
        assert invitation_2 is not None
        invitation_2.expires_at = now() - timedelta(minutes=1)
        db.commit()

    with client:
        expired = client.get(
            '/api/v1/participant/session',
            headers={'Authorization': f'Bearer {api_token_2}'},
            follow_redirects=False,
        )
        assert expired.status_code == 401
        assert expired.headers.get('www-authenticate') == 'Bearer'


def test_participant_api_active_session_uniqueness_is_enforced_by_database_constraint():
    from sqlalchemy.exc import IntegrityError
    from app.models import ParticipantInvitation, PublicAuthSession
    from app.participant_api.auth import PARTICIPANT_API_SCOPE
    from app.security import new_token, token_hash

    token, _participant_id, _study_id = _create_participant_invitation_for_api('api-auth-db-unique')

    with SessionLocal() as db:
        invitation = db.scalar(
            select(ParticipantInvitation).where(ParticipantInvitation.token_hash == token_hash(token))
        )
        assert invitation is not None

        first_raw = new_token()
        db.add(
            PublicAuthSession(
                scope=PARTICIPANT_API_SCOPE,
                session_hash=token_hash(first_raw),
                participant_invitation_id=invitation.id,
                expires_at=now() + timedelta(hours=1),
            )
        )
        db.flush()

        second_raw = new_token()
        db.add(
            PublicAuthSession(
                scope=PARTICIPANT_API_SCOPE,
                session_hash=token_hash(second_raw),
                participant_invitation_id=invitation.id,
                expires_at=now() + timedelta(hours=1),
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


def test_participant_api_auth_increment_preserves_html_join_study_and_portal_flow():
    token, _participant_id, _study_id = _create_participant_invitation_for_api('api-auth-regression')

    with client:
        landing = client.get(f'/join-study?token={token}', follow_redirects=False)
        assert landing.status_code == 303
        consent = post_with_csrf('/join-study', data={'consent': 'true'}, follow_redirects=False)
        assert consent.status_code == 303
        assert consent.headers['location'] == '/participant-portal'
        portal = client.get('/participant-portal')
        assert portal.status_code == 200


def test_participant_api_studies_requires_valid_bearer_and_returns_www_authenticate_header():
    token, _participant_id, _study_id = _create_participant_invitation_for_api('api-studies-auth')

    with client:
        exchange = _exchange_participant_api_session(token)
        assert exchange.status_code == 200

        missing = client.get('/api/v1/participant/studies', follow_redirects=False)
        assert missing.status_code == 401
        assert missing.headers.get('www-authenticate') == 'Bearer'

        malformed = client.get(
            '/api/v1/participant/studies',
            headers={'Authorization': 'Bearer'},
            follow_redirects=False,
        )
        assert malformed.status_code == 401
        assert malformed.headers.get('www-authenticate') == 'Bearer'

        invalid = client.get(
            '/api/v1/participant/studies',
            headers={'Authorization': 'Bearer invalid-value'},
            follow_redirects=False,
        )
        assert invalid.status_code == 401
        assert invalid.headers.get('www-authenticate') == 'Bearer'


def test_participant_api_studies_rejects_unaccepted_invitation_with_forbidden():
    token, _participant_id, _study_id = _create_participant_invitation_for_api('api-studies-forbidden')

    with client:
        exchange = _exchange_participant_api_session(token)
        assert exchange.status_code == 200
        api_token = exchange.json()['session']['access_token']

        studies = client.get(
            '/api/v1/participant/studies',
            headers={'Authorization': f'Bearer {api_token}'},
            follow_redirects=False,
        )
        assert studies.status_code == 403


def test_participant_api_studies_returns_scoped_contract_shape_and_no_store_header():
    token, participant_id, study_id = _create_participant_invitation_for_api('api-studies-success')

    with client:
        consent = client.get(f'/join-study?token={token}', follow_redirects=False)
        assert consent.status_code == 303
        accepted = post_with_csrf('/join-study', data={'consent': 'true'}, follow_redirects=False)
        assert accepted.status_code == 303

        exchange = _exchange_participant_api_session(token)
        assert exchange.status_code == 200
        api_token = exchange.json()['session']['access_token']

        studies = client.get(
            '/api/v1/participant/studies?limit=10',
            headers={'Authorization': f'Bearer {api_token}'},
            follow_redirects=False,
        )
        assert studies.status_code == 200
        assert studies.headers.get('cache-control') == 'no-store'
        body = studies.json()
        assert list(body.keys()) == ['data', 'pagination']
        assert isinstance(body['data'], list)
        assert len(body['data']) == 1
        item = body['data'][0]
        assert item['study_id'] == study_id
        assert item['enrolled'] is True
        assert item['title']
        assert item['status']
        assert item['methodology']
        assert body['pagination'] == {
            'cursor': None,
            'next_cursor': None,
            'limit': 10,
            'has_more': False,
        }
        assert item.get('participant_id') is None
        assert participant_id > 0


def test_participant_api_studies_rejects_withdrawn_consent_even_when_invitation_was_accepted():
    from app.models import Participant

    token, participant_id, _study_id = _create_participant_invitation_for_api('api-studies-consent-withdrawn')

    with client:
        consent = client.get(f'/join-study?token={token}', follow_redirects=False)
        assert consent.status_code == 303
        accepted = post_with_csrf('/join-study', data={'consent': 'true'}, follow_redirects=False)
        assert accepted.status_code == 303

        exchange = _exchange_participant_api_session(token)
        assert exchange.status_code == 200
        api_token = exchange.json()['session']['access_token']

    with SessionLocal() as db:
        participant_row = db.get(Participant, participant_id)
        assert participant_row is not None
        participant_row.consent_status = 'withdrawn'
        db.commit()

    with client:
        denied = client.get(
            '/api/v1/participant/studies',
            headers={'Authorization': f'Bearer {api_token}'},
            follow_redirects=False,
        )
        assert denied.status_code == 403
        assert denied.json() == {'detail': 'Participant consent is no longer active.'}


def test_participant_api_activities_requires_valid_bearer_and_returns_www_authenticate_header():
    token, _participant_id, _study_id = _create_participant_invitation_for_api('api-activities-auth')

    with client:
        exchange = _exchange_participant_api_session(token)
        assert exchange.status_code == 200

        missing = client.get('/api/v1/participant/activities', follow_redirects=False)
        assert missing.status_code == 401
        assert missing.headers.get('www-authenticate') == 'Bearer'

        malformed = client.get(
            '/api/v1/participant/activities',
            headers={'Authorization': 'Bearer'},
            follow_redirects=False,
        )
        assert malformed.status_code == 401
        assert malformed.headers.get('www-authenticate') == 'Bearer'

        invalid = client.get(
            '/api/v1/participant/activities',
            headers={'Authorization': 'Bearer invalid-value'},
            follow_redirects=False,
        )
        assert invalid.status_code == 401
        assert invalid.headers.get('www-authenticate') == 'Bearer'


def test_participant_api_activities_rejects_unaccepted_invitation_with_forbidden():
    token, _participant_id, _study_id = _create_participant_invitation_for_api('api-activities-forbidden')

    with client:
        exchange = _exchange_participant_api_session(token)
        assert exchange.status_code == 200
        api_token = exchange.json()['session']['access_token']

        activities = client.get(
            '/api/v1/participant/activities',
            headers={'Authorization': f'Bearer {api_token}'},
            follow_redirects=False,
        )
        assert activities.status_code == 403


def test_participant_api_activities_returns_scoped_activity_list_with_availability_and_response_summary():
    from app.models import Activity

    token, _participant_id, study_id = _create_participant_invitation_for_api('api-activities-success')

    with client:
        landing = client.get(f'/join-study?token={token}', follow_redirects=False)
        assert landing.status_code == 303
        consent = post_with_csrf('/join-study', data={'consent': 'true'}, follow_redirects=False)
        assert consent.status_code == 303

        exchange = _exchange_participant_api_session(token)
        assert exchange.status_code == 200
        api_token = exchange.json()['session']['access_token']

        with SessionLocal() as db:
            first_activity = db.scalar(
                select(Activity)
                .where(Activity.study_id == study_id)
                .order_by(Activity.position.asc(), Activity.id.asc())
            )
            assert first_activity is not None
            activity_id = first_activity.id

        draft = post_with_csrf(
            f'/participant-portal/activity/{activity_id}',
            data={'action': 'draft', 'answer': 'draft answer'},
            follow_redirects=False,
        )
        assert draft.status_code == 303

        activities = client.get(
            f'/api/v1/participant/activities?study_id={study_id}',
            headers={'Authorization': f'Bearer {api_token}'},
            follow_redirects=False,
        )
        assert activities.status_code == 200
        assert activities.headers.get('cache-control') == 'no-store'

        body = activities.json()
        assert list(body.keys()) == ['data']
        assert isinstance(body['data'], list)
        assert len(body['data']) >= 1

        first = body['data'][0]
        assert first['activity_id'] == activity_id
        assert first['title']
        assert first['activity_type']
        assert isinstance(first['required'], bool)
        assert isinstance(first['position'], int)
        assert first['availability']['status'] in {'open', 'upcoming', 'closed'}
        assert first['availability']['release_at'] is None or isinstance(first['availability']['release_at'], str)
        assert first['availability']['due_at'] is None or isinstance(first['availability']['due_at'], str)
        assert first['response']['status'] == 'draft'
        assert first['response']['submitted_at'] is None
        assert isinstance(first['response']['updated_at'], str)

        out_of_scope = client.get(
            '/api/v1/participant/activities?study_id=999999',
            headers={'Authorization': f'Bearer {api_token}'},
            follow_redirects=False,
        )
        assert out_of_scope.status_code == 403


def test_participant_api_activities_rejects_withdrawn_consent_even_when_invitation_was_accepted():
    from app.models import Participant

    token, participant_id, _study_id = _create_participant_invitation_for_api('api-activities-consent-withdrawn')

    with client:
        landing = client.get(f'/join-study?token={token}', follow_redirects=False)
        assert landing.status_code == 303
        consent = post_with_csrf('/join-study', data={'consent': 'true'}, follow_redirects=False)
        assert consent.status_code == 303

        exchange = _exchange_participant_api_session(token)
        assert exchange.status_code == 200
        api_token = exchange.json()['session']['access_token']

    with SessionLocal() as db:
        participant_row = db.get(Participant, participant_id)
        assert participant_row is not None
        participant_row.consent_status = 'withdrawn'
        db.commit()

    with client:
        denied = client.get(
            '/api/v1/participant/activities',
            headers={'Authorization': f'Bearer {api_token}'},
            follow_redirects=False,
        )
        assert denied.status_code == 403
        assert denied.json() == {'detail': 'Participant consent is no longer active.'}


def test_participant_api_activities_rejects_when_participant_not_enrolled_in_invitation_study():
    from app.models import StudyEnrolment

    token, participant_id, study_id = _create_participant_invitation_for_api('api-activities-no-enrolment')

    with client:
        landing = client.get(f'/join-study?token={token}', follow_redirects=False)
        assert landing.status_code == 303
        consent = post_with_csrf('/join-study', data={'consent': 'true'}, follow_redirects=False)
        assert consent.status_code == 303

        exchange = _exchange_participant_api_session(token)
        assert exchange.status_code == 200
        api_token = exchange.json()['session']['access_token']

    with SessionLocal() as db:
        enrolment = db.scalar(
            select(StudyEnrolment).where(
                StudyEnrolment.study_id == study_id,
                StudyEnrolment.participant_id == participant_id,
            )
        )
        assert enrolment is not None
        db.delete(enrolment)
        db.commit()

    with client:
        denied = client.get(
            '/api/v1/participant/activities',
            headers={'Authorization': f'Bearer {api_token}'},
            follow_redirects=False,
        )
        assert denied.status_code == 403
        assert denied.json() == {'detail': 'Participant is not enrolled in this study.'}


def _prepare_participant_api_activity_response_context(email_suffix: str):
    from app.models import Activity

    token, participant_id, study_id = _create_participant_invitation_for_api(email_suffix)

    with client:
        landing = client.get(f'/join-study?token={token}', follow_redirects=False)
        assert landing.status_code == 303
        consent = post_with_csrf('/join-study', data={'consent': 'true'}, follow_redirects=False)
        assert consent.status_code == 303

        exchange = _exchange_participant_api_session(token)
        assert exchange.status_code == 200
        api_token = exchange.json()['session']['access_token']

    with SessionLocal() as db:
        activity_row = db.scalar(
            select(Activity)
            .where(Activity.study_id == study_id)
            .order_by(Activity.position.asc(), Activity.id.asc())
        )
        assert activity_row is not None
        activity_id = activity_row.id

    return {
        'token': token,
        'api_token': api_token,
        'participant_id': participant_id,
        'study_id': study_id,
        'activity_id': activity_id,
    }


def test_participant_api_activity_response_requires_bearer_challenge():
    context = _prepare_participant_api_activity_response_context('api-activity-response-auth')

    with client:
        missing = client.put(
            f"/api/v1/participant/activities/{context['activity_id']}/draft",
            json={'answer': 'draft one'},
            follow_redirects=False,
        )
        assert missing.status_code == 401
        assert missing.headers.get('www-authenticate') == 'Bearer'

        invalid = client.put(
            f"/api/v1/participant/activities/{context['activity_id']}/draft",
            json={'answer': 'draft one'},
            headers={'Authorization': 'Bearer invalid-token'},
            follow_redirects=False,
        )
        assert invalid.status_code == 401
        assert invalid.headers.get('www-authenticate') == 'Bearer'


def test_participant_api_activity_response_cookie_only_does_not_authenticate_and_html_accept_stays_json():
    context = _prepare_participant_api_activity_response_context('api-activity-response-cookie-only')

    with client:
        landing = client.get(f"/join-study?token={context['token']}", follow_redirects=False)
        assert landing.status_code == 303

        cookie_only = client.put(
            f"/api/v1/participant/activities/{context['activity_id']}/draft",
            json={'answer': 'draft cookie only'},
            follow_redirects=False,
        )
        assert cookie_only.status_code == 401
        assert cookie_only.headers.get('www-authenticate') == 'Bearer'

        html_accept = client.put(
            f"/api/v1/participant/activities/{context['activity_id']}/draft",
            json={'answer': 'draft html accept'},
            headers={'Accept': 'text/html'},
            follow_redirects=False,
        )
        assert html_accept.status_code == 401
        assert html_accept.headers.get('www-authenticate') == 'Bearer'
        assert html_accept.headers.get('content-type', '').startswith('application/json')
        assert 'csrf_session=' not in (html_accept.headers.get('set-cookie') or '')


def test_participant_api_activity_response_draft_create_and_update_return_single_row():
    from app.models import ActivityResponse

    context = _prepare_participant_api_activity_response_context('api-activity-response-draft-update')

    with client:
        created = client.put(
            f"/api/v1/participant/activities/{context['activity_id']}/draft",
            json={'answer': 'draft one', 'choices': []},
            headers={'Authorization': f"Bearer {context['api_token']}"},
            follow_redirects=False,
        )
        assert created.status_code == 200
        assert created.headers.get('cache-control') == 'no-store'
        first_body = created.json()
        assert first_body['status'] == 'draft'
        assert first_body['response_id'] > 0

        updated = client.put(
            f"/api/v1/participant/activities/{context['activity_id']}/draft",
            json={'answer': 'draft two', 'choices': ['alpha']},
            headers={'Authorization': f"Bearer {context['api_token']}"},
            follow_redirects=False,
        )
        assert updated.status_code == 200
        second_body = updated.json()
        assert second_body['status'] == 'draft'
        assert second_body['response_id'] == first_body['response_id']

    with SessionLocal() as db:
        rows = list(
            db.scalars(
                select(ActivityResponse).where(
                    ActivityResponse.activity_id == context['activity_id'],
                    ActivityResponse.participant_id == context['participant_id'],
                )
            )
        )
        assert len(rows) == 1
        assert rows[0].submitted_at is None
        assert json.loads(rows[0].value_json)['answer'] == 'draft two'


def test_participant_api_activity_response_submit_sets_final_state_and_is_idempotent_for_identical_payload():
    from app.models import ActivityResponse

    context = _prepare_participant_api_activity_response_context('api-activity-response-submit')

    with client:
        submitted = client.post(
            f"/api/v1/participant/activities/{context['activity_id']}/submit",
            json={'answer': 'final answer', 'choices': []},
            headers={'Authorization': f"Bearer {context['api_token']}"},
            follow_redirects=False,
        )
        assert submitted.status_code == 200
        submitted_body = submitted.json()
        assert submitted_body['status'] == 'submitted'
        assert submitted_body['response_id'] > 0
        assert submitted_body['submitted_at']
        assert submitted_body['updated_at']

        repeat = client.post(
            f"/api/v1/participant/activities/{context['activity_id']}/submit",
            json={'answer': 'final answer', 'choices': []},
            headers={'Authorization': f"Bearer {context['api_token']}"},
            follow_redirects=False,
        )
        assert repeat.status_code == 200
        assert repeat.json()['response_id'] == submitted_body['response_id']

        conflict = client.post(
            f"/api/v1/participant/activities/{context['activity_id']}/submit",
            json={'answer': 'different final answer', 'choices': []},
            headers={'Authorization': f"Bearer {context['api_token']}"},
            follow_redirects=False,
        )
        assert conflict.status_code == 409

        draft_after_submit = client.put(
            f"/api/v1/participant/activities/{context['activity_id']}/draft",
            json={'answer': 'attempted edit after submit'},
            headers={'Authorization': f"Bearer {context['api_token']}"},
            follow_redirects=False,
        )
        assert draft_after_submit.status_code == 409

        activities = client.get(
            '/api/v1/participant/activities',
            headers={'Authorization': f"Bearer {context['api_token']}"},
            follow_redirects=False,
        )
        assert activities.status_code == 200
        by_id = {item['activity_id']: item for item in activities.json()['data']}
        assert by_id[context['activity_id']]['response']['status'] == 'submitted'
        assert by_id[context['activity_id']]['response']['submitted_at'] is not None

        portal = client.get(
            '/api/v1/participant/portal',
            headers={'Authorization': f"Bearer {context['api_token']}"},
            follow_redirects=False,
        )
        assert portal.status_code == 200
        portal_items = {item['activity_id']: item for item in portal.json()['responses']}
        assert portal_items[context['activity_id']]['status'] == 'submitted'
        assert portal_items[context['activity_id']]['submitted_at'] is not None

    with SessionLocal() as db:
        row = db.scalar(
            select(ActivityResponse).where(
                ActivityResponse.activity_id == context['activity_id'],
                ActivityResponse.participant_id == context['participant_id'],
            )
        )
        assert row is not None
        assert row.status == 'submitted'
        assert row.submitted_at is not None


def test_participant_api_activity_response_rejects_out_of_scope_consent_withdrawn_and_missing_enrolment():
    from app.models import Activity, Participant, Study, StudyEnrolment

    context = _prepare_participant_api_activity_response_context('api-activity-response-scope')

    with SessionLocal() as db:
        scoped_activity = db.get(Activity, context['activity_id'])
        assert scoped_activity is not None
        scoped_study = db.get(Study, context['study_id'])
        assert scoped_study is not None
        second_study = Study(
            organisation_id=scoped_study.organisation_id,
            project_id=scoped_study.project_id,
            title='Out of scope study',
            code=unique_value('OUTSCOPE').upper(),
            description='Used by API scope regression tests.',
            methodology=scoped_study.methodology,
            status=scoped_study.status,
            created_by_id=scoped_study.created_by_id,
        )
        db.add(second_study)
        db.flush()
        second_activity = Activity(
            organisation_id=scoped_activity.organisation_id,
            study_id=second_study.id,
            title='Out of scope activity',
            prompt='Should return not found for this participant scope',
            activity_type='long_text',
            required=True,
            position=1,
            release_offset_days=0,
            due_offset_days=None,
        )
        db.add(second_activity)
        db.commit()
        out_of_scope_id = second_activity.id

    with client:
        wrong_scope = client.put(
            f'/api/v1/participant/activities/{out_of_scope_id}/draft',
            json={'answer': 'should not be allowed'},
            headers={'Authorization': f"Bearer {context['api_token']}"},
            follow_redirects=False,
        )
        assert wrong_scope.status_code == 404

    with SessionLocal() as db:
        participant_row = db.get(Participant, context['participant_id'])
        assert participant_row is not None
        participant_row.consent_status = 'withdrawn'
        db.commit()

    with client:
        withdrawn = client.put(
            f"/api/v1/participant/activities/{context['activity_id']}/draft",
            json={'answer': 'denied by consent'},
            headers={'Authorization': f"Bearer {context['api_token']}"},
            follow_redirects=False,
        )
        assert withdrawn.status_code == 403
        assert withdrawn.json() == {'detail': 'Participant consent is no longer active.'}

    with SessionLocal() as db:
        participant_row = db.get(Participant, context['participant_id'])
        assert participant_row is not None
        participant_row.consent_status = 'granted'
        enrolment = db.scalar(
            select(StudyEnrolment).where(
                StudyEnrolment.study_id == context['study_id'],
                StudyEnrolment.participant_id == context['participant_id'],
            )
        )
        assert enrolment is not None
        db.delete(enrolment)
        db.commit()

    with client:
        not_enrolled = client.put(
            f"/api/v1/participant/activities/{context['activity_id']}/draft",
            json={'answer': 'denied by enrolment'},
            headers={'Authorization': f"Bearer {context['api_token']}"},
            follow_redirects=False,
        )
        assert not_enrolled.status_code == 403
        assert not_enrolled.json() == {'detail': 'Participant is not enrolled in this study.'}


def test_participant_api_activity_response_rejects_invalid_payload_and_leaves_no_partial_rows():
    from app.models import ActivityResponse

    context = _prepare_participant_api_activity_response_context('api-activity-response-invalid-payload')

    with client:
        invalid = client.put(
            f"/api/v1/participant/activities/{context['activity_id']}/draft",
            json={'answer': 'draft', 'evidence_id': 0},
            headers={'Authorization': f"Bearer {context['api_token']}"},
            follow_redirects=False,
        )
        assert invalid.status_code == 422

    with SessionLocal() as db:
        row = db.scalar(
            select(ActivityResponse).where(
                ActivityResponse.activity_id == context['activity_id'],
                ActivityResponse.participant_id == context['participant_id'],
            )
        )
        assert row is None


def test_participant_api_activity_response_submit_required_activity_needs_value_and_has_no_partial_write():
    from app.models import Activity, ActivityResponse

    context = _prepare_participant_api_activity_response_context('api-activity-response-required')

    with SessionLocal() as db:
        activity_row = db.get(Activity, context['activity_id'])
        assert activity_row is not None
        activity_row.required = True
        db.commit()

    with client:
        empty_submit = client.post(
            f"/api/v1/participant/activities/{context['activity_id']}/submit",
            json={'answer': '', 'choices': []},
            headers={'Authorization': f"Bearer {context['api_token']}"},
            follow_redirects=False,
        )
        assert empty_submit.status_code == 400
        assert empty_submit.json() == {'detail': 'A response is required.'}

    with SessionLocal() as db:
        row = db.scalar(
            select(ActivityResponse).where(
                ActivityResponse.activity_id == context['activity_id'],
                ActivityResponse.participant_id == context['participant_id'],
            )
        )
        assert row is None


def test_participant_api_activity_response_submit_required_activity_rejects_blank_choices_only():
    from app.models import Activity, ActivityResponse

    context = _prepare_participant_api_activity_response_context('api-activity-response-required-blank-choices')

    with SessionLocal() as db:
        activity_row = db.get(Activity, context['activity_id'])
        assert activity_row is not None
        activity_row.required = True
        db.commit()

    with client:
        blank_choice_submit = client.post(
            f"/api/v1/participant/activities/{context['activity_id']}/submit",
            json={'answer': '', 'choices': ['   ', '']},
            headers={'Authorization': f"Bearer {context['api_token']}"},
            follow_redirects=False,
        )
        assert blank_choice_submit.status_code == 400
        assert blank_choice_submit.json() == {'detail': 'A response is required.'}

    with SessionLocal() as db:
        row = db.scalar(
            select(ActivityResponse).where(
                ActivityResponse.activity_id == context['activity_id'],
                ActivityResponse.participant_id == context['participant_id'],
            )
        )
        assert row is None


def test_participant_api_activity_response_rejects_unsupported_content_type():
    context = _prepare_participant_api_activity_response_context('api-activity-response-content-type')

    with client:
        response = client.put(
            f"/api/v1/participant/activities/{context['activity_id']}/draft",
            data='answer=text-body',
            headers={
                'Authorization': f"Bearer {context['api_token']}",
                'Content-Type': 'text/plain',
            },
            follow_redirects=False,
        )
        assert response.status_code == 415


def test_participant_api_activity_response_idempotency_key_header_bounds_are_enforced():
    context = _prepare_participant_api_activity_response_context('api-activity-response-idempotency-header')

    with client:
        too_short = client.put(
            f"/api/v1/participant/activities/{context['activity_id']}/draft",
            json={'answer': 'draft with short key'},
            headers={
                'Authorization': f"Bearer {context['api_token']}",
                'Idempotency-Key': 'short7!',
            },
            follow_redirects=False,
        )
        assert too_short.status_code == 422

        too_long = client.put(
            f"/api/v1/participant/activities/{context['activity_id']}/draft",
            json={'answer': 'draft with long key'},
            headers={
                'Authorization': f"Bearer {context['api_token']}",
                'Idempotency-Key': 'x' * 129,
            },
            follow_redirects=False,
        )
        assert too_long.status_code == 422


def test_participant_api_activity_response_integrity_race_maps_to_conflict(monkeypatch):
    from sqlalchemy.exc import IntegrityError
    import app.main as main_module

    context = _prepare_participant_api_activity_response_context('api-activity-response-integrity-race')

    def _raise_integrity_error(*_args, **_kwargs):
        raise IntegrityError('insert', {}, Exception('unique conflict'))

    monkeypatch.setattr(main_module, 'resolve_or_create_activity_response', _raise_integrity_error)

    with client:
        draft_conflict = client.put(
            f"/api/v1/participant/activities/{context['activity_id']}/draft",
            json={'answer': 'draft attempt'},
            headers={'Authorization': f"Bearer {context['api_token']}"},
            follow_redirects=False,
        )
        assert draft_conflict.status_code == 409
        assert draft_conflict.json() == {'detail': 'Activity response state conflict.'}

        submit_conflict = client.post(
            f"/api/v1/participant/activities/{context['activity_id']}/submit",
            json={'answer': 'submit attempt'},
            headers={'Authorization': f"Bearer {context['api_token']}"},
            follow_redirects=False,
        )
        assert submit_conflict.status_code == 409
        assert submit_conflict.json() == {'detail': 'Activity response state conflict.'}


def test_participant_api_activity_response_status_transition_race_maps_to_conflict(monkeypatch):
    import app.main as main_module

    context = _prepare_participant_api_activity_response_context('api-activity-response-status-race')

    with client:
        created = client.put(
            f"/api/v1/participant/activities/{context['activity_id']}/draft",
            json={'answer': 'initial draft'},
            headers={'Authorization': f"Bearer {context['api_token']}"},
            follow_redirects=False,
        )
        assert created.status_code == 200

    monkeypatch.setattr(main_module, '_update_activity_response_if_not_submitted', lambda *_args, **_kwargs: False)

    with client:
        draft_conflict = client.put(
            f"/api/v1/participant/activities/{context['activity_id']}/draft",
            json={'answer': 'draft lost race'},
            headers={'Authorization': f"Bearer {context['api_token']}"},
            follow_redirects=False,
        )
        assert draft_conflict.status_code == 409
        assert draft_conflict.json() == {'detail': 'Activity response has already been submitted.'}

        submit_conflict = client.post(
            f"/api/v1/participant/activities/{context['activity_id']}/submit",
            json={'answer': 'submit lost race'},
            headers={'Authorization': f"Bearer {context['api_token']}"},
            follow_redirects=False,
        )
        assert submit_conflict.status_code == 409
        assert submit_conflict.json() == {'detail': 'Activity response has already been submitted.'}


def test_participant_api_activity_response_invalid_evidence_reference_does_not_mutate_existing_draft():
    from app.models import ActivityResponse

    context = _prepare_participant_api_activity_response_context('api-activity-response-evidence-rollback')

    with client:
        first = client.put(
            f"/api/v1/participant/activities/{context['activity_id']}/draft",
            json={'answer': 'stable draft', 'choices': ['alpha']},
            headers={'Authorization': f"Bearer {context['api_token']}"},
            follow_redirects=False,
        )
        assert first.status_code == 200

        invalid_evidence = client.put(
            f"/api/v1/participant/activities/{context['activity_id']}/draft",
            json={'answer': 'mutating draft', 'choices': ['beta'], 'evidence_id': 999999},
            headers={'Authorization': f"Bearer {context['api_token']}"},
            follow_redirects=False,
        )
        assert invalid_evidence.status_code == 400

    with SessionLocal() as db:
        row = db.scalar(
            select(ActivityResponse).where(
                ActivityResponse.activity_id == context['activity_id'],
                ActivityResponse.participant_id == context['participant_id'],
            )
        )
        assert row is not None
        payload = json.loads(row.value_json or '{}')
        assert payload['answer'] == 'stable draft'
        assert payload['choices'] == ['alpha']
        assert row.status == 'draft'
