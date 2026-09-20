# Analysis Workbench final QA

This report records the explicit cross-cutting QA completed after AW-18. It is
an engineering and product-language review, not a claim that software alone
can make a qualitative study methodologically sound.

## QA-01 — Methodological integrity

The workbench supports several analytical practices while leaving method,
interpretation and warrant with the researcher:

| Practice | Support in the workbench | Boundary / limitation |
|---|---|---|
| Reflexive thematic analysis | Exact-passage coding, annotations, reflexive memos, researcher-developed themes, explicit relationships and source traversal | The interface does not prescribe a reflexive stance or a universal phase sequence. Themes are developed and revised by researchers, not discovered or generated automatically. |
| Codebook thematic analysis | Study-scoped hierarchical codebook, definitions, archive history, exact passage/image application, retrieval and provenance | Agreement procedures, training and adjudication remain study decisions; application counts are not quality scores. |
| Framework analysis | Participant/case matrices, themes/codes as columns, source excerpts and case navigation | The matrix is a bounded retrieval/organisation view, not a complete prescribed framework-method workflow or a substitute for analytical summaries. |
| Qualitative content analysis | Codebook, coded-unit retrieval, Boolean combinations and separately labelled application/case/source counts | Counts describe the available study material only; they do not prove salience, prevalence or representativeness. |
| Longitudinal qualitative work | Chronological source entries, coding time, context fields, participant filters and period summaries | Temporal order and proximity do not establish change mechanisms or causality. Researchers must interpret continuity, change and context. |
| Case comparison | Participant/case matrix, exact-source links, advanced filters and cross-case retrieval | The current bounded view is organisational support, not statistical comparison or population inference. |
| Negative/contradictory cases | `contradicts` and `qualifies` relationships, negative-case query filter, and findings that retain non-supportive material | Relationships are explicit researcher assertions. The system does not infer contradiction or automatically revise a finding. |

Language was reviewed across the researcher surfaces and public worked example.
The public example now says researchers develop findings and labels the example
as a provisional interpretation; it no longer says findings or themes
automatically “emerge”. Existing count, chronology, finding and AI safeguards
remain visible in the matrix, longitudinal, advanced-query, findings and AI
views.

## QA-02 — Security and privacy

The final review covered the full analysis surface and its shared services:

- organisation, project and study access are resolved before every workbench
  read; object resolution is an allow-list and fails closed for unknown,
  cross-tenant and cross-study typed references;
- SQLite and PostgreSQL database guards cover analysis targets, code
  applications, annotations, memos, relationships, theme-code links, canvas
  nodes, findings, AI provenance and audit context;
- mutation routes use the existing CSRF dependency, while forged code,
  relationship, canvas, finding, filter and export identifiers are rejected;
- canonical Unicode anchors are bounds/fingerprint checked on input and before
  passage display/export, so a malformed or stale anchor cannot substitute the
  wrong participant text;
- participant and researcher content is rendered through autoescaped templates;
  regression tests cover script-like passages, annotations, memos,
  relationship rationale and findings, and CSP nonces remain required;
- export uses server-controlled ZIP/JSON names, `no-store`/`nosniff`, inert JSON
  strings rather than spreadsheet cells, explicit content types, scoped study
  selection and bounded components;
- participant deletion removes participant-derived targets, applications,
  annotations, relevant relationships/canvas placements, source-backed AI
  suggestions and findings converted from those suggestions. Unrelated
  study-level researcher analysis is retained. Anonymisation is reflected at
  read/export time because analysis pointers do not copy participant identity;
  withdrawal stops further access/collection but follows the configured
  controller deletion/retention process rather than claiming automatic erasure;
- AI suggestions retain source/provider/model/prompt/review provenance, remain
  visibly untrusted, obey study access and AI governance, and cannot silently
  become researcher-authored analysis.

No new security defect requiring a schema or permission change was found. The
existing integration, architecture and migration suites already exercise the
specified tenant/study IDOR, polymorphic reference, anchor, relationship,
CSRF, XSS, export, lifecycle and AI-provenance cases. The final QA adds a
durable terminology regression and retains Bandit plus the repository security
job as release gates.

## QA-03 — Performance

A disposable local PostgreSQL database was migrated from an empty schema to
Alembic `0035` and populated with synthetic data only:

- 250 participant cases;
- 1,000 submitted longitudinal responses;
- 1,000 analysis targets and 2,000 exact-passage code applications;
- 20 codes, 10 themes, 100 memos, 100 findings, 100 relationships, 100 canvas
  nodes, annotations and 500 audit events.

Three warm in-process request rounds produced the following local measurements.
They are comparative engineering observations, not production service-level
objectives:

| Workflow | Mean request time | SQL statements |
|---|---:|---:|
| Entries | 39 ms | 18 |
| Coded-passage retrieval | 27 ms | 12 |
| Case matrix | 132 ms | 10 |
| Longitudinal view | 145 ms | 12 |
| Advanced query | 121 ms | 11 |
| Relationships | 58 ms | 23 |
| Canvas | 76 ms | 28 |
| Findings | 187 ms | 24 |
| Structured export | 148 ms | 23 |

Profiling identified per-object source lookups in shared canvas/finding picker
assembly. Scoped bulk loading reduced the canvas path from 145 to 28 SQL
statements and the findings path from 141 to 24. A query-count regression test
protects the shared object picker. Database execution time remained a minority
of request time and existing scoped indexes served the measured shapes, so no
speculative index or materialized view was added.

The reusable benchmark is `scripts/benchmark_analysis.py`. It refuses a
production environment and requires a database name containing `qa` or `test`.
All major reads remain explicitly bounded (normally 5,000 source/application
records, with smaller UI-specific limits), and the UI reports truncation where
it affects interpretation.
