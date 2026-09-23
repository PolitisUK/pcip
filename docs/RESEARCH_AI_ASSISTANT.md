# Research AI Assistant security and methodology design

## Scope and release posture

The researcher-facing **Ask AI** page is part of the web Analysis Workbench. It is not a participant or mobile feature. Version 1 is stateless: it creates no conversation table, vector index, embedding, saved answer, code, theme, memo, finding, or participant-data copy.

The page may be visible when Research Intelligence is enabled, but an outbound model request is possible only when all of these controls are present:

- `RESEARCH_INTELLIGENCE_ENABLED=true`;
- the existing approved-provider gate `RESEARCH_INTELLIGENCE_AI_CODING_ENABLED=true`;
- an HTTPS `AZURE_OPENAI_ENDPOINT`;
- an `AZURE_OPENAI_API_KEY` supplied server-side (normally through Key Vault);
- a fixed server-side `AZURE_OPENAI_DEPLOYMENT`.

The browser never receives provider credentials and cannot select an endpoint, provider, deployment, organisation, or arbitrary data source. This change does not activate any provider or production flag.

## Tenant and permission boundary

Every request begins with the ordinary authenticated project workspace check. The selected study must be in the studies returned by that user's existing project/study access rules. A caller-supplied inaccessible study identifier returns an unavailable/not-found response before retrieval.

Retrieval queries repeat both `organisation_id` and `study_id` predicates for source responses and every researcher-analysis type. This deliberately provides defence in depth beyond route-level permission checks. The assistant has read access only; it exposes no analytical mutation or participant mutation operation.

Only one explicit study can be selected per request. Project-wide, cross-study, cross-organisation and global retrieval are not implemented. Participant display names, email addresses, phone numbers, notes and demographics are excluded; source labels use the study-local participant reference.

## Retrieval and citations

Retrieval is deterministic and request-scoped. It searches submitted textual responses and, when the researcher opts in, active codes, themes, memos, findings, verified coded passages, and researcher-created analytical relationships. Archived analytical records, malformed passage anchors, missing/deleted responses, and empty source text are omitted.

Lexical ranking bounds each request to 20 sources and 20,000 source characters. The provider receives opaque citation IDs such as `response:123` or `coding:45`, not database access. Returned citation IDs are checked against that exact retrieval set. A missing, empty, malformed, or forged citation set rejects the whole answer. Citation links lead back to the authoritative Analysis Workbench record.

## Methodology decisions

The assistant reuses the confirmed, version-pinned study methodology and controlled methodology library.

- **ALLOW** — the requested retrieval task is permitted by both the study configuration and methodology record.
- **WARN** — retrieval may continue, but wording invokes claims the assistant cannot establish (including causation, prevalence, representativeness, saturation, objectivity, or automatic emergence). The warning is sent with the grounded request and displayed to the researcher.
- **BLOCK** — the task is unsupported, AI is disabled for the study, methodology is unconfirmed/inconsistent, or the task is not allowed by the study and method. No provider call occurs.

Supported tasks are bounded evidence retrieval and negative/contrasting-case retrieval. The assistant cannot choose a methodology, decide sampling or saturation, create a final finding, claim causal or population inference, or overwrite participant voice.

## Prompt-injection and output controls

The fixed system instruction treats all participant and researcher-authored source content as untrusted data, never as instructions. Research text is placed in a structured JSON payload separate from the system instruction. The provider is instructed to use only supplied sources and return a fixed JSON shape. The server validates the shape and source IDs before rendering. Jinja auto-escaping applies to questions, answers, limitations, labels and source excerpts.

The assistant cannot call tools, browse, retrieve outside the server-built bundle, or mutate application state. Provider errors or invalid output produce a bounded in-product failure and no fabricated fallback answer.

## Audit, privacy and lifecycle

Each attempted question records an existing `AuditEvent` with actor, organisation, project, study, task, methodology decision, source count, analysis-inclusion flag, provider identifier, and outcome. The raw question, answer, participant text, prompt payload, provider key and participant identity are not written to the audit detail.

There is no chat retention and no model-training path. Existing startup validation prevents participant training, shared-model training, or cross-customer learning flags from being enabled. Provider processing remains subject to the existing approved Azure region and organisational agreement before activation.

Because the assistant adds no stored participant derivative, participant deletion and anonymisation need no new cleanup ordering. Deleted responses cannot be retrieved on later requests. Existing persisted Analysis Workbench objects and historic AI suggestions continue to follow their established lifecycle and export behavior.

## Deliberately excluded from version 1

- persistent chat threads or cross-session memory;
- embeddings, vector databases, or semantic indexes;
- autonomous code/theme/finding creation or bulk mutation;
- participant cohort, project-wide or cross-study assistant scopes;
- image, audio, video or document-content transmission;
- automatic conversion of an answer into researcher-authored analysis.

If a researcher wishes to retain an interpretation, they must use the existing researcher-authored codebook, memo, theme or finding workflows and make the analytical judgement themselves. Adding saved conversations, embeddings, broader scopes, new providers, or conversion actions requires a separate privacy and security review.

## Security and privacy review

| Risk | Control in version 1 | Residual/rollout requirement |
| --- | --- | --- |
| Cross-tenant or IDOR retrieval | Existing workspace permission resolution plus organisation-and-study predicates on every retrieval query; browser scope values are resolved against authorised studies | Keep forged-ID and membership tests in the release gate |
| Prompt injection in research text | Fixed system instruction; research text is isolated in structured source objects; no tools or arbitrary retrieval; citations are allowlisted | Provider output remains untrusted and must continue to be escaped and reviewed |
| Excessive disclosure | Pseudonymous references, bounded excerpts, no contact/account data, maximum candidate/source/input/output limits | Activation requires confirmation that the selected Azure deployment, region, retention, abuse-monitoring and training terms satisfy the controller's agreement |
| Hallucinated or overclaimed analysis | Required citations, citation allowlist, methodology ALLOW/WARN/BLOCK, prohibited-claim instruction, provisional labelling | A human researcher must check source material; model prose is never a finding of record |
| Persistent leakage or stale deleted data | No chats, answers, prompts, embeddings or caches are persisted; every request reads current authoritative rows | Any future persistence or semantic index needs lifecycle deletion design before implementation |
| Provider outage or misconfiguration | Multiple server-side gates, HTTPS endpoint requirement, bounded error handling, no demo/fallback answers | Availability depends on the separately approved provider configuration |
| Secret exposure | Endpoint/deployment are server-selected, API key remains server-side, and audit records contain metadata only | Operational logs and Key Vault access remain governed by existing production controls |
