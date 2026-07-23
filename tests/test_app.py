import os
os.environ['DATABASE_URL'] = 'sqlite:///./data/test.db'
from pathlib import Path
import re
from glob import glob
from uuid import uuid4
import pytest
from types import SimpleNamespace
from contextlib import contextmanager
Path('data/test.db').unlink(missing_ok=True)
from fastapi.testclient import TestClient
from app.main import app
from datetime import timedelta
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import User
from app.main import now, rate_limiter
from app.config import validate_runtime_settings

client = TestClient(app)


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


def test_login_and_dashboard():
    with client:
        r = auth(); assert r.status_code == 303
        d = client.get('/')
        assert d.status_code == 200 and 'Seven-day town centre diary' in d.text


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
    from app.models import ParticipantInvitation, OutboxEmail
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
        accepted = post_with_csrf('/join-study', data={'token': token, 'consent': 'true'}, follow_redirects=True)
        assert accepted.status_code == 200 and "You're enrolled" in accepted.text

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


def test_navigation_active_state_and_mobile_safe_markup():
    with client:
        auth()
        html = client.get('/projects').text
        assert 'class="active" href="/projects"' in html
        assert 'aria-label="Primary navigation"' in html


def test_participant_portal_draft_submit_and_message():
    from app.db import SessionLocal
    from app.models import OutboxEmail, Activity, ActivityResponse, ParticipantMessage
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
        post_with_csrf('/join-study', data={'token':token,'consent':'true'})
        portal=client.get(f'/participant-portal?token={token}')
        assert portal.status_code==200 and 'Your activities' in portal.text
        draft=post_with_csrf(f'/participant-portal/activity/{activity_id}', data={'token':token,'action':'draft','answer':'draft answer'}, follow_redirects=False)
        assert draft.status_code==303
        submit=post_with_csrf(f'/participant-portal/activity/{activity_id}', data={'token':token,'action':'submit','answer':'final answer'}, follow_redirects=False)
        assert submit.status_code==303
        msg=post_with_csrf('/participant-portal/message', data={'token':token,'body':'Hello research team'}, follow_redirects=False)
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
    from app.models import User, Study, StudyAccess
    from app.security import hash_password
    from sqlalchemy import select
    with client:
        auth()
        with SessionLocal() as db:
            owner = db.scalar(select(User).where(User.email == 'admin@politis.local'))
            researcher = db.scalar(select(User).where(User.email == 'permissions@example.org'))
            if not researcher:
                researcher = User(organisation_id=owner.organisation_id, name='Permissions Researcher', email='permissions@example.org', password_hash=hash_password('SecurePass123!'), role='researcher')
                db.add(researcher); db.commit(); db.refresh(researcher)
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
        'cookie_secure': True,
        'session_cookie_secure': True,
        'base_url': 'https://pilot.example.org',
        'trusted_hosts': 'pilot.example.org',
        'allowed_origins': 'https://pilot.example.org',
        'azure_defender_webhook_secret': 'required-webhook-secret',
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
    from app.models import OutboxEmail
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

        reset = post_with_csrf('/reset-password', data={'token': token, 'password': new_password}, follow_redirects=False)
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
