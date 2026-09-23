# Research AI production hardening

## Approval status

This design prepares infrastructure; it does not approve or activate production
AI. `RESEARCH_INTELLIGENCE_AI_CODING_ENABLED` and
`RESEARCH_INTELLIGENCE_SEMANTIC_SEARCH_ENABLED` must remain `false` until a
separate owner approval.

The pre-existing `ccaird20260812` resource and its `qual-coder` deployment are
R&D assets and are not production providers.

## Governed provider design

The dedicated resource is defined by `infra/research-ai.bicep`:

- Azure OpenAI resource owned by the target staging or production resource group;
- Sweden Central resource location;
- deployment `research-assistant-gpt41mini`;
- `gpt-4.1-mini`, version `2025-04-14`;
- `DataZoneStandard`, limiting processing to the Azure EU Data Zone;
- `NoAutoUpgrade`, so a replacement model version requires an explicit change;
- public network access and local/API-key authentication disabled;
- private endpoint, private DNS, and App Service VNet integration;
- production App Service managed identity assigned only `Cognitive Services
  OpenAI User` on this resource;
- only audit, request-usage, and metrics diagnostics; no `RequestResponse` log
  routing.

The subscription catalogue was checked on 23 September 2026 and exposed
`DataZoneStandard` for `gpt-4.1-mini` version `2025-04-14`. Reconfirm model,
SKU, capacity, and the current Microsoft deployment documentation immediately
before deployment. Global Standard is not permitted by this template.

References:

- [Azure model deployment types](https://learn.microsoft.com/azure/ai-foundry/foundry-models/concepts/deployment-types)
- [Azure OpenAI data, privacy and security](https://learn.microsoft.com/azure/foundry/responsible-ai/openai/data-privacy)
- [Azure OpenAI abuse monitoring](https://learn.microsoft.com/azure/foundry/openai/concepts/abuse-monitoring)
- [Azure OpenAI keyless authentication](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/managed-identity)

## Authentication and endpoint boundary

The application requests a Microsoft Entra token for
`https://cognitiveservices.azure.com/.default`. The endpoint and deployment are
server configuration, never browser input. The exact endpoint hostname must
also appear in `AZURE_OPENAI_ALLOWED_HOSTS` and must use an Azure OpenAI domain.
HTTP, credentials in URLs, nonstandard ports, paths, query strings, malformed
URLs, suffix-confusion hosts, and non-allow-listed resources fail closed before
research material is sent.

API-key authentication remains available only as an explicit fallback. If an
exception is approved, its key must be stored in Key Vault, exposed only to the
server process, and rotated through secret versions. The production design does
not require this fallback and disables local authentication on the AI resource.

## Logging boundary

The application audit stores task and methodology decisions, source counts and
types, provider/model identifiers, and outcome. It does not store the question,
retrieved passages, or answer. Application Insights captures ordinary request,
dependency, exception, and trace metadata; no custom request/response-body
capture is implemented. Provider credentials and headers are not logged.

The AI resource diagnostic setting deliberately excludes the Azure OpenAI
`RequestResponse` category. Do not add that category without a new privacy and
retention review.

## Provider use and retention

Microsoft states that prompts and completions are not made available to OpenAI
and are not used to train foundation models without customer permission or
instruction. This is distinct from safety processing and abuse monitoring.

By default, flagged prompts and completions may be stored for controlled human
review. Current Microsoft documentation does not provide a sufficiently firm
retention duration for Citizen Centric to claim zero or fixed-duration
retention. Modified abuse monitoring removes the described storage and human
review when Microsoft approves it, but automated safety processing can remain.

### Required owner/admin action

An eligible managed customer administrator must apply using the **Apply for
modified abuse monitoring** link in Microsoft's current abuse-monitoring
documentation. After Microsoft responds, verify the actual production resource
shows the capability `ContentLogging=false`. Save the approval and resource
evidence in the controlled compliance record; do not store it in application
source code.

Production activation is blocked until either:

1. Microsoft approval is recorded and `ContentLogging=false` is verified on the
   exact production resource; or
2. Thomas explicitly accepts the documented standard storage and possible
   human-review boundary.

## Technical data-processing statement

Research AI is available only to authorised researchers. Each request is
checked against the researcher's organisation, project, and study permissions.
Citizen Centric retrieves a bounded set of relevant material for that request
and transmits it to the configured Azure OpenAI deployment. Participant identity
is minimised by using pseudonymous references instead of names where possible.

Citizen Centric does not use participant material to train models. It does not
retain an application conversation history, provider answer, or separate copy
of retrieved passages, and one organisation cannot retrieve another
organisation's AI context. A metadata-only audit event records that assistance
was requested. Provider training, automated safety processing, monitoring,
storage, human review, and geographic processing are governed separately by the
selected Azure configuration and Microsoft's applicable terms.

AI answers are provisional, source-linked research assistance. They are not
researcher findings and do not become analysis without researcher judgement.

## Staging acceptance gate

Deploy the same template to the isolated staging environment first. Configure
its exact output endpoint/host/deployment with managed identity, retain the two
AI feature flags as false, then use a separately approved temporary staging gate
with wholly synthetic records for the acceptance run.

The run must cover connectivity, free-text questions, supporting and
contradictory evidence, methodology ALLOW/WARN/BLOCK, valid and forged
citations, organisation and study isolation, injected instructions in source
text, provider outage, invalid responses, timeout, deleted-source removal, and
metadata-only audit. No production participant or research content may be used.

Record the immutable application revision, resource ID, endpoint hostname,
deployment/model/version/SKU, `ContentLogging` capability, diagnostic settings,
and test results. Remove or retain synthetic data under the staging policy.

## Dark application deployment

The merged Research Assistant application can be promoted through the standard
staging-first protected workflow without any AI endpoint or credential. The
release must preserve:

- `RESEARCH_INTELLIGENCE_ENABLED=true`;
- `RESEARCH_INTELLIGENCE_AI_CODING_ENABLED=false`;
- `RESEARCH_INTELLIGENCE_SEMANTIC_SEARCH_ENABLED=false`;
- `RUN_MIGRATIONS=false` after release;
- Alembic revision `0037`.

Use an immutable candidate, release-window enforcement, the protected
environment approval, and the normal production backup/recovery process. A
fresh owner-approved release window is required. No migration accompanies this
change.
