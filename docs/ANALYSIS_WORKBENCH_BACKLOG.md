# Analysis Workbench backlog

## AW-01 — Analysis Workbench Foundation — complete

AW-01 introduces `AnalysisTarget`: the small, durable bridge between existing
participant-derived material and future researcher analysis.  It is deliberately
not a codebook, annotation editor, theme workflow, or analysis UI.

### Architecture and migration

Alembic revision `0025` adds organisation- and study-scoped targets for exactly
one of three authoritative sources:

- an activity response, including a future exact-text anchor;
- an evidence file, including a future image-region anchor; or
- a participant/case in an enrolled study.

The source links are concrete foreign keys, not a polymorphic type-and-ID
relationship. Database check constraints enforce one valid source shape and
make researcher, system, and AI-suggestion authorship explicit. SQLite and
PostgreSQL scope checks reject cross-organisation or cross-study references.
The study/type index supports deterministic study queries at longitudinal
dataset scale; source indexes support efficient future annotation lookups.

The migration is additive from released revision `0024`; it does not rewrite
participant evidence or existing themes, AI suggestions, or confidence records.

### Privacy and deletion

Targets never duplicate participant text or media. Participant privacy deletion
removes response, evidence, and case targets in the same transaction before the
underlying source records are removed. Existing withdrawal and anonymisation
behaviour is unchanged: withdrawal does not silently remove research material,
while deletion follows the established lifecycle and retention safeguards.

### Tests and review coverage

Migration tests cover upgrade, target constraints, and tenant-scope rejection.
The participant-deletion lifecycle test verifies that response, evidence, and
case targets are removed with the participant. Existing migration rehearsal and
Alembic metadata checks remain part of CI.

### Important decisions

- Targets only identify source material; they are not analysis claims and do
  not snapshot original content.
- `anchor_json` is intentionally an extensibility seam. AW-02+ must define and
  validate versioned anchor schemas before writing text offsets or image regions.
- `authorship` is distinct from participant evidence and reserves clear state
  for future AI suggestions; no AI creation path is introduced here.
- Analytical objects added later should reference targets and retain their own
  author, provenance, and audit records.

## AW-02 — researcher codebook and coding

Next, introduce researcher-managed codes and hierarchical codebooks, then bind
code applications to `AnalysisTarget`. Define code lifecycle, permissions,
audit events, anchor validation, and deletion interactions before adding an
editing UI. Themes, findings, relationships, matrices, visual maps, and AI
suggestion workflows remain later backlog items.
