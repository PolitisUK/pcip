# Rivermere fictional demonstration data

This package defines two repeatable, explicitly fictional ethnographic datasets:

- `RIV-2035` — **Rivermere 2035: Everyday Life and the Future of Our Town**
- `RIV-CHAPEL` — **Chapel Lane: Living With an Unresolved Planning Breach**

The command in `scripts/seed_rivermere_demo.py` refuses non-development environments, non-SQLite databases, non-local storage, and database or storage paths outside the current checkout. It also requires an explicit confirmation flag.

The seed uses the platform's native Organisation → Project → Study → Activity → Participant → Response → Evidence structure. The current schema has no hierarchical codebook, coded-segment or memo table. Deterministic researcher-demo code assignments therefore live in each response's flexible JSON payload, while `project_analysis_manifest()` exposes the codebook and memo set for verification. No AI analysis job is fabricated.

The four JPEG seed assets are synthetic, non-identifying scenes generated for this fictional dataset. Remaining evidence rows are unique text artefacts explicitly marked as fictional demonstration material and stored through the configured local evidence backend.

Create both projects:

```bash
PYTHONPATH=. .venv/bin/python scripts/seed_rivermere_demo.py --confirm-local-development
```

Remove only one project:

```bash
PYTHONPATH=. .venv/bin/python scripts/seed_rivermere_demo.py --confirm-local-development --remove everyday-life
PYTHONPATH=. .venv/bin/python scripts/seed_rivermere_demo.py --confirm-local-development --remove chapel-lane
```
