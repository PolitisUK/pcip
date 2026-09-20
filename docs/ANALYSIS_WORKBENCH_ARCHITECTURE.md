# Analysis Workbench architecture

This document defines the internal extension boundary established at AW-11.5.
It complements the feature history in `ANALYSIS_WORKBENCH_BACKLOG.md`.

## Composition boundary

`app/analysis_router.py` owns the Analysis Workbench GET route registry and
registers it as a tagged FastAPI router. `app/main.py` remains the application
composition root and supplies the existing handlers during this incremental
refactor. New workbench route groups should live behind the analysis router
boundary rather than adding another unrelated application surface.

This is intentionally not a framework-wide rewrite: existing URLs, templates,
dependencies and permissions are preserved while cohesive services move out of
the composition root.

## Shared coded-passage projection

`coded_passage_projections` in `app/analysis_projections.py` is the reusable
read contract for source-traceable coding consumers. It:

- requires an organisation and explicit study IDs;
- optionally filters an explicit set of code IDs;
- caps every request at 5,000 rows and reports truncation;
- returns the application, target, source response, participant/case, code,
  researcher, activity and whitelisted response context;
- reconstructs and fingerprint-verifies the passage from the authoritative
  response using canonical Unicode code-point offsets; and
- never creates a participant-text copy in persistent analytical data.

Matrix and longitudinal views use this contract. Later query, canvas, finding
and export work should extend or compose projection services rather than copy
template-specific joins.

## Analytical object contract

`resolve_analytical_object` in `app/analysis_objects.py` is an allow-listed
resolver, not a generic ORM/model lookup. Supported types are analysis targets,
code applications, annotations, memos, codes, themes, canonical relationships
and enrolled participant cases. Resolution requires a current user and study, applies the established
study-access policy, enforces organisation and study scope, and returns a
bounded label/summary, navigation link where meaningful, and resolved
editability.

Unknown types, invalid IDs, inaccessible studies and cross-tenant or
cross-study objects fail closed with no object result. Add future object types
explicitly with tests; never accept an arbitrary model/table name from a
request.

## Relationships and lifecycle

`AnalyticalRelationship` remains the canonical directed relationship model.
Relationship creation resolves both endpoints through the shared object
contract with edit permission. Canvas or finding features must call the same
relationship service rather than store UI-specific graph edges.

`remove_analytical_references` in `app/analysis_lifecycle.py` is the central
cleanup hook for canonical relationships before analytical objects are
deleted. Participant privacy deletion and current remove operations use this
hook. Callers still own deletion order and their transaction; the hook neither
commits nor weakens the existing fail-safe deletion workflow.

## Performance boundary

Workbench projections must be tenant/study scoped and bounded before material
is assembled for templates. The existing analysis target, code application,
theme-code and relationship scope/source indexes match current joins and
filters. AW-11.5 introduces no migration or speculative materialized view.
Future indexes require a concrete query shape or measurement and should be
delivered through the normal SQLite/PostgreSQL migration rehearsal.

## Visual canvas contract

`AnalysisCanvas` and `AnalysisCanvasNode` persist only a researcher's visual
study layout. A node contains a typed pointer plus x/y coordinates; labels,
summaries and participant-derived excerpts are always resolved from the shared
analytical object service. The database validates the canvas owner, study and
every allow-listed object pointer on both insert and update.

The canvas is deliberately not a graph model. Visible edges are bounded queries
over `AnalyticalRelationship`, and creating or removing an edge calls the same
relationship permission and audit services used by the relationship record.
Removing a node changes only layout. Deleting an underlying analytical object
removes its placement through `remove_analytical_references` before the object
is deleted.
