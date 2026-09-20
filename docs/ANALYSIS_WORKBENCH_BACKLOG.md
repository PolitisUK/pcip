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
PostgreSQL scope checks reject cross-organisation or cross-study references,
including researcher attribution to a user outside the target organisation.
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

## AW-02 — Researcher Codebook — complete

AW-02 introduces `ResearchCode`, a researcher-authored analytical label that
is deliberately distinct from `ResearchTheme`. Codes are scoped to one study,
retain creator and timestamps, can have one optional parent, and may be
archived/restored without hard deletion. They do not store participant content
and participant deletion does not remove the codebook.

Alembic revision `0026` adds the model, indexes, and SQLite/PostgreSQL guards
for organisation-scoped creator and parent references, self-parenting, circular
hierarchies, and archived parents. Existing children remain attached when a
parent is archived, preserving future analytical provenance; an archived code
cannot be edited or selected as a new parent until restored.

The study codebook UI follows existing study permissions: anyone with study
read access can inspect it; edit/manage access can create, edit, re-parent,
archive, and restore. Significant operations emit existing audit events.
Tests cover migration guards, hierarchy operations, archive/restore, and the
server-rendered workflow. AW-03 remains intentionally unimplemented.

## AW-03 — Passage-level coding — complete

`CodeApplication` links a researcher, active `ResearchCode`, and response
`AnalysisTarget` using a versioned JSON anchor with validated UTF-16-independent
Python offsets and a selected-passage SHA-256 fingerprint. Applications do not
copy participant text. Exact duplicate applications are prevented; overlap and
nested passages remain valid. Privacy deletion removes applications before their
targets/responses but retains the codebook.

## AW-04 — Text annotations — complete

`ResearchAnnotation` stores a researcher-authored analytical comment against a
versioned, fingerprinted exact-passage anchor without copying participant text.
The Entries workflow reconstructs and verifies the source excerpt, fails closed
when an anchor cannot be verified, and supports Unicode code-point offsets,
authorship and timestamps. Study editors can create annotations; authors and
study managers can edit or remove permitted annotations. Read-only users may
inspect them without seeing write controls.

Alembic revision `0028` adds SQLite/PostgreSQL guards for organisation, study,
target and author scope. Significant operations are audited without participant
text, and privacy deletion removes participant-linked annotations before their
analysis targets.

## AW-05 — Researcher memos — complete

`ResearchMemo` provides researcher-authored analytical writing scoped to a
study, participant/case, response, `AnalysisTarget`, `ResearchCode`, or
`ResearchTheme`. Memos retain authorship and creation/update timestamps and use
an archive/restore lifecycle rather than silently disappearing. Authors may
change their own memos; study managers may manage all memos; read-only study
users can inspect them without write controls.

The study memo workspace offers labelled, validated scope choices and supports
creation, editing, archiving, restoration and archived-history inspection.
Alembic revision `0029` enforces shape plus organisation/study scope for every
pointer and researcher at database level on SQLite and PostgreSQL. Audit events
record actions without memo or participant text. Participant deletion removes
case-, response-, and participant-derived target memos while retaining reusable
study/code/theme memos.

## AW-06 — Coding retrieval — complete

The project workspace now includes a paginated researcher passage-coding
retrieval view. It filters accessible material by study, `ResearchCode`,
participant/case, applying researcher, application date and authoritative entry
text. Results reconstruct and fingerprint-check each coded excerpt, show useful
counts, retain archived codes for historical retrieval, and drill directly back
to the original filtered Entry and its context.

The view is read-only for all authorised study readers, remains explicitly
distinct from legacy response-level code chips, uses bounded result and filter
loads, and derives passages from current source material rather than persisting
another participant-text copy.

## AW-07 — Multimedia / image-region annotation — complete

Clean image evidence now has a progressive-enhancement region-analysis page.
Researchers can drag a rectangle or enter its accessible fractional coordinates,
then attach one or more active `ResearchCode` records and/or an analytical
annotation. Rectangles use a versioned, resolution-independent anchor and the
original evidence object is never modified.

Each region is a researcher-authored evidence `AnalysisTarget`; existing
`CodeApplication` and `ResearchAnnotation` provenance and database scope guards
are reused rather than duplicated. Historic archived codes remain visible,
study permissions govern creation/removal, IDs are organisation/study/evidence
scoped, actions are audited without participant content, and privacy deletion
removes region applications before evidence targets and files.

## AW-08 — Analytical relationships — complete

`AnalyticalRelationship` records directional researcher assertions between
analysis targets, code applications, annotations, memos, codes and themes. The
controlled relationship vocabulary covers supports, contradicts, explains,
relates to, precedes, follows and refines; rationale, author and timestamp are
retained. Self-links and exact duplicate assertions are rejected.

The study relationship workspace provides labelled object selection, inspection
and permitted removal. Alembic revision `0030` validates both polymorphic ends,
the author, organisation and study on INSERT and UPDATE in SQLite and
PostgreSQL. The model is the canonical relationship system intended for later
canvas use rather than a UI-specific graph store.

## AW-09 — Theme development — complete

The existing researcher-created `ResearchTheme` capability now supports an
iterative thematic-analysis workflow: researchers can create and define themes,
refine their definitions, connect active `ResearchCode` records, inspect the
verified coded extracts supporting those codes, and archive or restore themes.
Creator, code-link author, and timestamps remain visible; archived themes and
codes remain readable as historical analytical provenance.

Alembic revision `0031` adds the scoped `ResearchThemeCode` join and theme
archive provenance. SQLite and PostgreSQL guards enforce organisation, study,
theme, code, creator, linker and archiver integrity on INSERT and UPDATE. No
participant text is copied into theme records or joins: excerpts are rebuilt
from authoritative responses and fingerprint-checked code anchors. Reviewed AI
analysis may be referenced as optional provenance, but is never promoted into a
theme without an explicit researcher creation action.

## AW-10 — Case / framework matrices — complete

The project research workspace now derives participant/case × `ResearchCode`
or researcher-developed `ResearchTheme` matrices from scoped
`CodeApplication` and `ResearchThemeCode` records. Researchers can filter by
accessible study, switch analytical dimension, and focus a single code or
theme. Each populated cell exposes verified coded excerpts with links back to
the authoritative source entry; empty cells remain explicit for comparison.

Matrices are read-only query views, bounded to 5,000 applications and 50
columns, and create no persistent matrix or participant-text copy. Archived
codes/themes remain available for historical analysis. This stage adds no
database migration because it composes the existing tenant-guarded analytical
records.

## AW-11 — Longitudinal analysis — complete

The project research workspace now provides a chronological qualitative view
of submitted participant/case material and its researcher passage coding.
Researchers can filter by accessible study, participant/case, ResearchCode,
researcher-developed theme, and response context key/value, then compare
descriptive monthly entry and coding counts. Each event keeps the source
submission timestamp distinct from the later coding timestamp, reconstructs
verified coded passages, and links back to the original entry and context.

The UI explicitly states that temporal order and proximity do not establish
causation. It is a bounded, paginated read-only view derived from existing
responses and analytical records; it stores no timeline or participant-text
copy and introduces no migration.

## AW-11.5 — Analysis architecture consolidation — complete

The Analysis Workbench HTTP surface is now registered through a dedicated
router contract rather than accumulating route declarations in the application
composition root. Existing handler behaviour and URLs remain unchanged. New
workbench capabilities can be added behind this boundary without creating a
second application or frontend stack.

Shared services now provide a bounded coded-passage projection for coding,
matrix and longitudinal consumers; an allow-listed analytical-object resolver
with tenant, study and study-permission enforcement; and one lifecycle hook for
removing canonical relationship references. `AnalyticalRelationship` remains
the only analytical edge model. Participant privacy deletion uses the shared
lifecycle hook and retains its existing transaction and fail-safe semantics.

The projection reconstructs exact passages from authoritative responses and
does not persist participant text. Queries remain explicitly bounded to 5,000
coding rows and preserve fingerprint verification. The existing query shapes
already use scope/source indexes introduced by AW-01 through AW-09, so this
consolidation adds no speculative index or database migration. Dedicated tests
cover resolver scope and permission enforcement, Unicode projection behaviour,
canonical relationship creation, lifecycle cleanup and router registration.

The internal contracts and extension rules are documented in
`docs/ANALYSIS_WORKBENCH_ARCHITECTURE.md`. AW-12 builds on these services and
was intentionally kept out of the consolidation change itself.

## AW-12 — Visual analysis canvas — complete

Researchers now have a personal, study-scoped visual canvas for arranging
existing analytical objects. The canvas supports analysis targets (including
participant/case and image-evidence targets), coded passages, annotations,
memos, codes and themes. Cards retain bounded labels and summaries, link back
to their authoritative source, and reconstruct coded passages from the current
response with fingerprint verification rather than storing another text copy.

Canvas positions are presentation metadata only. Alembic revision `0032` adds
one canvas per researcher/study and typed node placements containing object IDs
and bounded coordinates; it stores no participant content. SQLite and
PostgreSQL guards validate canvas owner/study scope and every supported object
pointer on INSERT and UPDATE. Canvas loading is capped at 100 nodes and 500
visible canonical relationships, while the add-object catalogue is bounded per
object type.

Dragging and zoom/pan use modest progressive JavaScript. Each card also exposes
keyboard-accessible numeric position controls, source navigation and a normal
form for removing the card without deleting the underlying object. Read-only
study users may inspect and arrange their personal layout but cannot create or
remove analytical relationships.

Canvas connections create the existing `AnalyticalRelationship` records via
the shared relationship service; there is no second edge store. Relationship
type, rationale, researcher and date remain inspectable, and existing
permission/audit rules govern creation and removal. Cross-tenant and
cross-study forged objects fail closed at the service, route and database
levels. Participant deletion removes affected placements through the shared
lifecycle hook while leaving unrelated layout and reusable study analysis
unchanged.

## AW-13 — Advanced analytical queries — complete

The project workspace now provides a bounded advanced qualitative query view
over the shared coded-passage projection. Researchers can combine codes using
case-level AND or OR logic, exclude cases containing selected codes with NOT,
and narrow results by accessible study, participant/case, applying researcher,
coding date, researcher-developed theme, or an explicit canonical relationship
type such as `contradicts`.

Every result remains an individual `CodeApplication` with a fingerprint-checked
exact passage, participant/case, source entry, response context, researcher and
coding timestamp plus direct source navigation. Results are paginated and the
source scan is capped at 5,000 applications. Picker IDs are resolved only from
the user's accessible organisation/studies, and forged cross-tenant or
cross-study values fail closed.

The summary deliberately separates coded applications, distinct participant
cases and distinct source entries. A bounded code co-occurrence table reports
same-source-entry pairs with both entry and case counts, while the interface
states that frequency and co-occurrence do not establish importance,
representativeness, conceptual association or causality. This is a derived
read-only query layer and adds no migration or participant-text copy.

## AW-14 — Researcher findings — complete

`ResearchFinding` is now a first-class researcher-authored analytical
conclusion with organisation/study scope, substantive title and text, creator,
timestamps, and auditable edit/archive/restore lifecycle. A finding is kept
explicitly distinct from a code, theme, memo and AI suggestion. Its workspace
supports read-only inspection and permission-gated creation or change, with
participant-derived and researcher content escaped in every rendered view.

Findings connect to existing analytical objects through the canonical
`AnalyticalRelationship` service and store rather than a finding-specific edge
table. The vocabulary now includes `qualifies`, `illustrates`, `derived_from`
and `informed_by` alongside support and contradiction, so a finding can retain
negative and qualifying material. Linked coded passages are reconstructed from
the authoritative response and fingerprint checked, while each link retains
researcher/date/rationale provenance and source navigation.

Alembic revision `0033` creates the finding model and extends the relationship
and canvas allow-lists. SQLite and PostgreSQL INSERT/UPDATE guards validate the
finding study, creator and archiver plus finding relationship endpoints and
canvas pointers. The production-shaped constraint upgrade and
downgrade/re-upgrade paths are rehearsed. Participant deletion removes links to
deleted participant-derived objects while retaining unrelated study-level
researcher findings; no participant source material is copied into relationship
or canvas records.

## AW-15 — AI analytical assistance — complete

The existing `ResearchAnalysisSuggestion` record remains the single machine
assistance architecture. Suggestions are visibly labelled as AI-generated and
retain their authoritative source response, creation time, provider/model,
prompt and human-review provenance. Existing suggestions remain inspectable
even when suggestion creation is unavailable. This deployment fails closed:
there is no fabricated local output or external-provider call when an approved
provider-backed job has not been configured.

Researchers with study edit/manage permission can explicitly accept, reject or
dismiss a suggestion. Rejection and dismissal require a recorded reason.
Nothing in those dispositions creates or changes a researcher analytical
object. An accepted suggestion can instead be converted through a separate
researcher form into a new `ResearchFinding`; the researcher supplies the
finding title and substantive text, becomes its author, and the original AI
record changes to the `converted` disposition rather than having its authorship
rewritten.

Alembic revision `0034` adds the one-to-one originating-suggestion provenance
pointer. SQLite and PostgreSQL INSERT/UPDATE guards require that any pointer
belongs to the same organisation and study. The findings view exposes the
originating suggestion and provider/model without presenting it as authorship.
Review and conversion actions are audited, read-only study users receive no
controls, and scoped lookups reject forged tenant/study identifiers. Participant
deletion removes participant-derived suggestions and any converted findings
that depend on them, including canonical relationship/canvas references, while
unrelated study-level findings remain intact.

## AW-16 — Analysis audit trail — complete

The project research workspace now includes an Analysis history view backed by
the existing canonical `AuditEvent` store. It does not introduce a competing
event log. Authorised project researchers and administrators can inspect code,
passage-coding, annotation, memo, relationship, image-region, theme, finding
and AI-suggestion-review history with actor, action, analytical object, time and
study context.

Filters cover accessible study, actor, action family, object type and date
range, while pagination preserves the active query. The read path is bounded to
the 5,000 most recent matching organisation events and explicitly reports that
limit. Project/study permissions are applied before projection, forged study or
actor filters fail closed, and organisation-wide operational/security events
are not exposed in the researcher analysis view. Audit details remain short
operational descriptions rather than copies of participant responses.

Alembic revision `0035` extends the canonical audit record with nullable,
indexed project/study context so deletion events remain attributable after the
analytical object is gone. Existing records are resolved through their current
canonical objects where possible. SQLite and PostgreSQL INSERT/UPDATE guards
reject forged cross-organisation or inconsistent project/study context, and the
fresh-schema plus downgrade/re-upgrade paths are rehearsed.
