import os
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
from sqlalchemy import select

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
