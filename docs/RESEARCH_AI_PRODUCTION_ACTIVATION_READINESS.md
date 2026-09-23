# Research AI production activation readiness

This is a decision and change package, not approval to activate production AI.
Production provider infrastructure, provider settings, and
`RESEARCH_INTELLIGENCE_AI_CODING_ENABLED` remain absent or disabled until the
separately protected activation sequence is authorised.

## Provider privacy boundary

Citizen Centric uses stateless chat completions. Microsoft states that prompts
and completions are not available to other customers, OpenAI, or other model
providers, and are not used to train or improve foundation models or Microsoft,
OpenAI, or third-party products without explicit customer permission or
instruction. Models are stateless and do not store prompts or completions in
the model.

This does not mean zero retention. Standard Azure abuse monitoring evaluates
prompts and completions. Flagged material can be selected for a separate abuse-
monitoring data store and controlled human review by authorised Microsoft
employees using secured, just-in-time access. Microsoft says reviewers for EEA
deployments are located in the EEA. Current public documentation does not state
a fixed retention period that Citizen Centric can promise for that store.

The planned `DataZoneStandard` deployment uses a Sweden Central resource.
Processing can occur within the Azure EU Data Boundary, not necessarily only in
Sweden. Microsoft states that at-rest data, including the DataZone abuse-
monitoring store, remains in the designated Azure geography.

Citizen Centric stores a metadata-only audit event: task, methodology decision,
source count/types, provider/model identifiers, and outcome. It does not store
the question, retrieved passage copies, provider answer, chat history, or an
embedding index, and it creates no cross-tenant memory. This application
persistence boundary is separate from Azure inference, content filtering, and
abuse monitoring.

Authoritative Microsoft references:

- <https://learn.microsoft.com/azure/foundry/responsible-ai/openai/data-privacy>
- <https://learn.microsoft.com/azure/foundry/openai/concepts/abuse-monitoring>
- <https://learn.microsoft.com/azure/foundry/responsible-ai/openai/limited-access>
- <https://learn.microsoft.com/azure/foundry/foundry-models/concepts/deployment-types>

## Modified abuse monitoring

Microsoft limits modified abuse monitoring to customers and partners managed
by a Microsoft account team or covered by an eligible programme, with
additional use-case requirements. An organisational email is required. A
non-managed customer may submit the same form, but Microsoft determines whether
an eligible programme is available. Microsoft gives an indicative response
time of 5–10 business days and notes that it can take longer.

Apply using the **Modified abuse monitoring** form linked from Microsoft's
limited-access documentation. Eligibility for subscription
`fcc2b24e-3b8f-4997-b3f3-10dd9801acff` is currently unknown: enabled Azure
subscription metadata does not prove Microsoft account-team or eligible-
programme status. Do not treat an application as approval.

Microsoft describes verification for an approved Azure subscription. Retain
the approval record and confirm that it covers the intended production
subscription, use case, and resource. On the exact production resource, the
portal JSON view or `az cognitiveservices account show` must expose:

```json
{"name":"ContentLogging","value":"false"}
```

The property is absent when abuse-monitoring storage has not been disabled.
Modified abuse monitoring removes the described storage and human review;
automated safety review can remain.

## Planned production provider

The validated but undeployed template resolves to:

- subscription: `fcc2b24e-3b8f-4997-b3f3-10dd9801acff`;
- resource group: `rg-pcip-prod`;
- App Service: `citizencentric-pcip-prod`;
- Azure OpenAI resource: `pcip-production-research-ai-rx6kbu`;
- endpoint: `https://pcip-production-research-ai-rx6kbu.openai.azure.com/`;
- allowed host: `pcip-production-research-ai-rx6kbu.openai.azure.com`;
- deployment: `research-assistant-gpt41mini`;
- model/version: `gpt-4.1-mini` / `2025-04-14`;
- SKU: `DataZoneStandard`, capacity 10, `NoAutoUpgrade`;
- Azure OpenAI location: Sweden Central;
- VNet: `pcip-production-research-ai-vnet`, UK South;
- integration subnet: `app-integration` (`10.24.1.0/24`);
- private-endpoint subnet: `private-endpoints` (`10.24.2.0/24`);
- private endpoint: `pcip-production-research-ai-pe`, UK South;
- private DNS zone: `privatelink.openai.azure.com`;
- VNet link: `production-research-ai-vnet-link`;
- diagnostics: `research-ai-metadata-only` to
  `pcip-production-nevsxr-log`;
- authentication: production App Service system-managed identity;
- role: `Cognitive Services OpenAI User`, scoped only to this Azure OpenAI
  resource;
- public network access and local/key authentication: disabled;
- request/response-body diagnostic logging: disabled.

Template validation did not deploy or change any production resource or
setting.

## Required production settings

These exact settings are required only after the provider is deployed and
verified:

```text
RESEARCH_INTELLIGENCE_ENABLED=true
RESEARCH_INTELLIGENCE_AI_CODING_ENABLED=true
RESEARCH_INTELLIGENCE_SEMANTIC_SEARCH_ENABLED=false
AZURE_OPENAI_ENDPOINT=https://pcip-production-research-ai-rx6kbu.openai.azure.com/
AZURE_OPENAI_ALLOWED_HOSTS=pcip-production-research-ai-rx6kbu.openai.azure.com
AZURE_OPENAI_DEPLOYMENT=research-assistant-gpt41mini
AZURE_OPENAI_AUTHENTICATION=managed_identity
```

No API key is required or permitted by this production design.

## Protected activation sequence

1. Deploy the validated provider template through an approved infrastructure
   change.
2. Verify model, version, SKU, `NoAutoUpgrade`, private endpoint, private DNS,
   VNet integration, public-access denial, and local-auth denial.
3. Verify private DNS and HTTPS connectivity from App Service without research
   content.
4. Verify managed-identity token acquisition and the single resource-scoped
   `Cognitive Services OpenAI User` assignment.
5. Apply the fixed endpoint, exact-host allow-list, deployment, managed-
   identity authentication, and disabled feature flags while preserving every
   unrelated setting.
6. Verify metadata-only diagnostics and that `RequestResponse` logging is off.
7. Deploy the Research Assistant release through the normal staging-first
   protected release if production is not already on that code.
8. Run a no-content connectivity probe and verify fail-closed behaviour.
9. Record either the owner's standard-monitoring acceptance or Microsoft's
   modified-monitoring approval and `ContentLogging=false` evidence.
10. Use the queue-mediated
    `set-research-intelligence-ai-coding-enabled` operation to set only the
    final boolean gate to true.
11. Run limited acceptance in an explicitly approved fictional production
    workspace only.
12. Check audit metadata and telemetry for content leakage and errors.
13. Permit real research use only after all preceding evidence is accepted.

## Owner decision

### Option A — accept standard abuse monitoring

> I approve Citizen Centric production Research AI use with Microsoft's
> standard Azure abuse-monitoring controls. I understand that prompts and
> completions are not shared with OpenAI or other customers and are not used
> for shared-model training without our permission. I also understand that
> Microsoft may select flagged prompts and completions for provider-side
> storage and controlled human review, and that Microsoft does not publish a
> fixed retention duration Citizen Centric can promise. For the planned EU
> DataZone deployment, processing can occur across the Azure EU Data Boundary
> and provider-side at-rest data remains in the designated Azure geography.
> Citizen Centric itself stores metadata-only audit records and does not
> persist questions, retrieved passage copies, answers, or chat history. I
> authorise the separately protected production activation process on this
> basis.

### Option B — wait for modified abuse monitoring

Do not deploy or activate the production provider for real research data until
Microsoft has approved modified abuse monitoring for the relevant subscription
and the exact production resource shows `ContentLogging=false`. Until then,
provider-side abuse-monitoring storage and possible human review remain outside
the accepted privacy boundary.
