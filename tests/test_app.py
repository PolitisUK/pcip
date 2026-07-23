import os
os.environ['DATABASE_URL'] = 'sqlite:///./data/test.db'
from pathlib import Path
Path('data/test.db').unlink(missing_ok=True)
from fastapi.testclient import TestClient
from app.main import app
from datetime import timedelta
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import User
from app.main import now

client = TestClient(app)


def login():
    return client.post('/login', data={'email': 'admin@politis.local', 'password': 'PolitisDemo!'}, follow_redirects=False)


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
        p = client.post('/projects', data={'title': 'Access Study', 'code': 'ACC-001', 'description': 'Test', 'status_value': 'live'}, follow_redirects=False)
        assert p.status_code == 303
        page = client.get('/projects'); assert 'Access Study' in page.text
        project_id = int(page.text.split('/projects/')[1].split('"')[0])
        s = client.post(f'/projects/{project_id}/studies', data={'title': 'Access diary', 'code': 'ACC-D01', 'description': 'Diary', 'methodology': 'diary', 'status_value': 'recruiting'}, follow_redirects=False)
        assert s.status_code == 303
        detail = client.get(s.headers['location'])
        assert 'Access diary' in detail.text


def test_participant_enrolment_activity_and_invitation():
    with client:
        auth()
        p = client.post('/participants', data={'reference': 'P-101', 'name': 'Alex Participant', 'email': 'alex.participant@example.org', 'phone': '', 'status_value': 'prospective', 'consent_status': 'pending', 'communication_preference': 'email', 'tags': 'ward 1', 'notes': ''}, follow_redirects=False)
        assert p.status_code == 303
        participant_id = int(p.headers['location'].rsplit('/', 1)[-1])
        studies = client.get('/studies')
        study_id = int(studies.text.split('/studies/')[1].split('"')[0])
        e = client.post(f'/studies/{study_id}/enrol', data={'participant_id': participant_id}, follow_redirects=False)
        assert e.status_code == 303
        a = client.post(f'/studies/{study_id}/activities', data={'title': 'Rate the visit', 'prompt': 'How was it?', 'activity_type': 'rating', 'options': '', 'required': 'true', 'release_offset_days': '1', 'due_offset_days': '3'}, follow_redirects=False)
        assert a.status_code == 303
        invite = client.post(f'/studies/{study_id}/invite/{participant_id}', follow_redirects=False)
        assert invite.status_code == 303
        outbox = client.get('/outbox')
        assert 'alex.participant@example.org' in outbox.text and 'Invitation:' in outbox.text


def test_researcher_invite_and_admin_pages():
    with client:
        auth()
        p = client.post('/researchers/invite', data={'name': 'Alex Researcher', 'email': 'alex.researcher@example.org', 'role': 'researcher'}, follow_redirects=False)
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
        p = client.post('/participants', data={'reference': 'P-202', 'name': 'Jamie Resident', 'email': 'jamie@example.org', 'phone': '', 'status_value': 'prospective', 'consent_status': 'pending', 'communication_preference': 'email', 'tags': '', 'notes': ''}, follow_redirects=False)
        participant_id = int(p.headers['location'].rsplit('/', 1)[-1])
        studies = client.get('/studies')
        study_id = int(studies.text.split('/studies/')[1].split('"')[0])
        client.post(f'/studies/{study_id}/enrol', data={'participant_id': participant_id}, follow_redirects=False)
        client.post(f'/studies/{study_id}/invite/{participant_id}', follow_redirects=False)
        with SessionLocal() as db:
            email = db.scalar(select(OutboxEmail).where(OutboxEmail.recipient == 'jamie@example.org').order_by(OutboxEmail.id.desc()))
            token = email.body.split('token=')[1].strip()
        page = client.get(f'/join-study?token={token}')
        assert page.status_code == 200 and 'Research invitation' in page.text
        accepted = client.post('/join-study', data={'token': token, 'consent': 'true'})
        assert accepted.status_code == 200 and "You're enrolled" in accepted.text

def test_invalid_status_and_activity_validation():
    with client:
        auth()
        r = client.post('/projects', data={'title':'Invalid','code':'BAD-1','status_value':'nonsense'})
        assert r.status_code == 400
        from app.db import SessionLocal
        from app.models import Project
        from sqlalchemy import select
        with SessionLocal() as db:
            project_id = db.scalar(select(Project.id).order_by(Project.id.asc()))
        study = client.post(f'/projects/{project_id}/studies', data={'title':'Validation study','code':'VAL-1','methodology':'diary','status_value':'draft'}, follow_redirects=False)
        assert study.status_code == 303
        study_id = int(study.headers['location'].split('/')[-1])
        r = client.post(f'/studies/{study_id}/activities', data={'title':'Bad choice','activity_type':'single_choice','options':'Only one','release_offset_days':'0','due_offset_days':'0','required':'true'})
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
        p = client.post('/participants', data={'reference':'P-303','name':'Portal User','email':'portal@example.org','phone':'','status_value':'prospective','consent_status':'pending','communication_preference':'email','tags':'','notes':''}, follow_redirects=False)
        participant_id = int(p.headers['location'].rsplit('/',1)[-1])
        with SessionLocal() as db:
            first_activity=db.scalar(select(Activity).order_by(Activity.id.asc()))
            study_id=first_activity.study_id
            activity_id=first_activity.id
        client.post(f'/studies/{study_id}/enrol', data={'participant_id':participant_id})
        client.post(f'/studies/{study_id}/invite/{participant_id}')
        with SessionLocal() as db:
            email=db.scalar(select(OutboxEmail).where(OutboxEmail.recipient=='portal@example.org').order_by(OutboxEmail.id.desc()))
            token=email.body.split('token=')[1].strip()
        client.post('/join-study', data={'token':token,'consent':'true'})
        portal=client.get(f'/participant-portal?token={token}')
        assert portal.status_code==200 and 'Your activities' in portal.text
        draft=client.post(f'/participant-portal/activity/{activity_id}', data={'token':token,'action':'draft','answer':'draft answer'}, follow_redirects=False)
        assert draft.status_code==303
        submit=client.post(f'/participant-portal/activity/{activity_id}', data={'token':token,'action':'submit','answer':'final answer'}, follow_redirects=False)
        assert submit.status_code==303
        msg=client.post('/participant-portal/message', data={'token':token,'body':'Hello research team'}, follow_redirects=False)
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
        r=client.post('/participants/import', files={'file':('participants.csv',BytesIO(csv_data),'text/csv')}, follow_redirects=False)
        assert r.status_code==303
        page=client.get('/participants?q=Bulk')
        assert 'Bulk Person' in page.text
        reset=client.post('/forgot-password', data={'email':'admin@politis.local'})
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
        study_id = int(page.text.split('/studies/')[1].split('"')[0])
        detail = client.get(f'/studies/{study_id}')
        assert 'Study access' in detail.text
        assert 'Skip to main content' in detail.text


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
        response = client.post(f'/studies/{study_id}/access', data={'user_id': researcher_id, 'permission': 'view'}, follow_redirects=False)
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
    with client:
        for _ in range(settings.login_max_failed_attempts):
            response = client.post(
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
