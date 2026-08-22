# Rivermere fictional demonstration data

The versioned files in `app/demo_data/content/` are the authored Rivermere v1.1
source pack. They contain two explicitly fictional datasets:

- `RIV-2035` — **Rivermere 2035: Everyday Life and the Future of Our Town**
- `RIV-CHAPEL-LANE` — **Chapel Lane: Living With an Unresolved Planning Breach**

The importer uses the existing Organisation → Project → Study → Activity →
Participant → ActivityResponse → EvidenceFile structure. It stores the
authored hierarchical code labels as response-level coding assignments because
the platform has no passage-level coding model. It maps authored analytical
memos to the existing researcher-authored `ResearchTheme` model, never to an
AI suggestion. The Analysis screen labels them as researcher-authored memos.

Media are safe JSON manifest attachments, not claimed photographs or external
URLs. Every manifest is linked to its source entry and is available through the
normal evidence route. No generated image, official council document or real
case file is represented.

The source safeguards individual authorship and consent: no proxy submissions,
no pooled complaint material, no sharing of another participant's reference,
and no research-directed monitoring, photography or reporting. Chapel Lane
accounts describe historical individual civic actions only; those actions are
separate from the research submission.

## Local development

The command refuses a non-local database, non-local storage and any environment
other than development/test unless separately confirmed. It also checks the
requested environment and organisation slug before writing.

```bash
PYTHONPATH=. .venv/bin/python scripts/seed_rivermere_demo.py \
  --environment development \
  --organisation-slug rivermere-town-council \
  --confirm-local-development
```

Verify without writing:

```bash
PYTHONPATH=. .venv/bin/python scripts/seed_rivermere_demo.py \
  --environment development \
  --organisation-slug rivermere-town-council \
  --verify
```

Remove exactly one project:

```bash
PYTHONPATH=. .venv/bin/python scripts/seed_rivermere_demo.py \
  --environment development \
  --organisation-slug rivermere-town-council \
  --confirm-local-development --remove everyday-life

PYTHONPATH=. .venv/bin/python scripts/seed_rivermere_demo.py \
  --environment development \
  --organisation-slug rivermere-town-council \
  --confirm-local-development --remove chapel-lane
```

On a local database, the importer also removes only the exact pre-v1.1 bundled
Rivermere projects when they are present. If that legacy organisation contains
unrelated records, it is retained and those records are not changed.

## Staging and production

Staging is an explicit non-local operation and assumes the deployment has its
own `ENVIRONMENT`, database and storage configuration:

```bash
PYTHONPATH=. .venv/bin/python scripts/seed_rivermere_demo.py \
  --environment staging \
  --organisation-slug rivermere-town-council \
  --confirm-nonlocal-demo \
  --create-staging-demo-organisation
```

`--create-staging-demo-organisation` is accepted only in staging. It creates
only the exact fictional organisation and its non-login demo researcher when
they are absent. Production continues to require both records to be provisioned
separately before import.

Verify staging without writing:

```bash
PYTHONPATH=. .venv/bin/python scripts/seed_rivermere_demo.py \
  --environment staging \
  --organisation-slug rivermere-town-council \
  --verify
```

Production is disabled by default. Direct use requires the organisation and a
Rivermere demo researcher to exist already:

```bash
PYTHONPATH=. .venv/bin/python scripts/seed_rivermere_demo.py \
  --environment production \
  --organisation-slug rivermere-town-council \
  --confirm-nonlocal-demo --confirm-production-demo
```

The production release workflow provides a separately approved one-time route.
It remains behind the existing immutable-image, backup, rollback and production
environment gates. When explicitly selected, it creates only the exact
fictional organisation and non-login demo researcher, requires exactly one
active platform administrator, grants that administrator owner access to the
fictional workspace, imports idempotently, verifies the complete v1.1 pack,
clears the startup flag and restarts production. It fails closed if platform
administrator ownership is ambiguous or the designated slug is already used by
anything other than the exact fictional organisation.
