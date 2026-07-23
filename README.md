# Citizen Centric

by Politis

Current version: **0.6.0**

Citizen Centric is a multi-tenant civic research platform for councils and public-sector research teams. The internal engineering codename `PCIP` remains in repository and infrastructure identifiers.

## Local installation on macOS

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

Demo login:

- Email: `admin@politis.local`
- Password: `PolitisDemo!`

## Participant workflow

1. Create or import a participant.
2. Enrol them in a study.
3. Send an invitation from the study page.
4. In local mode, open the invitation link from **Email outbox**.
5. Accept consent and enter the participant portal.
6. Save drafts, submit responses, upload evidence and send messages.

## Email

Without SMTP configuration, outgoing emails are captured in the local Email outbox. Add SMTP settings to `.env` to send real messages.

## Storage

Local evidence files are placed in `data/uploads`. Production deployment should replace this with encrypted cloud object storage, malware scanning and lifecycle policies.

## Tests

```bash
PYTHONPATH=. python -m pytest -q
```

Expected result for this release candidate: `65 passed`.

See `RELEASE_NOTES_0.6.0.md` for the latest cumulative release context.
Release-candidate operational material is documented in `RELEASE_CANDIDATE_1_NOTES.md`, `DEPLOYMENT_CHECKLIST_RC1.md`, and `PILOT_OPERATOR_GUIDE.md`.

## Dependency security

CI includes dependency vulnerability scanning, security linting, and release smoke verification.
For technical dependency-update workflow guidance, see `DEPENDENCY_SECURITY_GUIDE.md`.

## Enterprise foundation in v0.5.0

### Database migrations

For a new or upgraded deployment, run:

```bash
alembic upgrade head
```

The application retains a small compatibility migration for older local SQLite demonstrations, but Alembic is now the intended migration mechanism.

### Evidence controls

Uploads are restricted by file extension and size. Evidence receives a SHA-256 integrity hash. Set `CLAMAV_HOST` to a reachable ClamAV daemon to enable antivirus scanning. Without it, files are recorded with a `not_configured` scanning status so the missing production control remains visible.

### Study permissions

Owners and administrators can assign individual users either view or edit access from the Study access section. Owners and administrators always retain management access.


## Azure evidence storage

Set `STORAGE_BACKEND=azure_blob` and `AZURE_STORAGE_ACCOUNT_URL` in Azure. The application uses `DefaultAzureCredential`, which resolves to the App Service managed identity in Azure. Uploaded evidence remains blocked until Microsoft Defender for Storage records a clean scan result. See `infra/README.md` and `RELEASE_NOTES_0.5.0.md`.

## Microsoft Azure deployment (v0.6.0)

Version 0.6.0 includes a cumulative Azure deployment template and GitHub Actions workflow.

Key files:

- `infra/main.bicep`
- `infra/dev.bicepparam.example`
- `.github/workflows/deploy-azure.yml`
- `scripts/configure_entra.sh`
- `scripts/configure_github_oidc.sh`
- `RELEASE_NOTES_0.6.0.md`

The container runs `alembic upgrade head` before starting the web application. Set `RUN_MIGRATIONS=false` only when migrations are managed separately.

Microsoft Entra account creation is deliberately controlled. Existing invited users are linked by email. Automatic provisioning requires all of `ENTRA_AUTO_PROVISION=true`, a valid `ENTRA_DEFAULT_ORGANISATION_SLUG`, and any desired domain allow-list.

## Production deployment documentation

- `DEPLOYMENT_GUIDE_AZURE.md`
- `AZURE_CONFIGURATION_GUIDE.md`
- `ENVIRONMENT_VARIABLES.md`
