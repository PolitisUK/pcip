# Legal and privacy implementation audit

Reviewed: 16 August 2026
Legal Pack: version 1.0, effective 15 August 2026

This is an implementation inventory, not legal advice or a substitute for a
controller's study-specific assessment.

## Participant-facing legal content

The web application publishes Privacy Notice, Terms, Cookie Notice,
Accessibility, Acceptable Use, Legal Information and Contact pages. The mobile
participant app provides a Legal & Privacy centre, Privacy at a glance and
links from consent to participant information and privacy content.

The published pack identifies Politis Ltd (company number 13661766), The Old
Courthouse, Orsett Rd, Grays, Essex RM17 5DD, ICO registration ZB738312, and
info@politisconsulting.co.uk. Study-specific controller, lawful basis,
retention and contact decisions are not supplied by platform defaults.

## Data, retention and participant controls

- The participant service handles invitation/session data, profile and contact
  preferences, responses, messages, evidence files and privacy requests.
- The mobile app stores participant session material in platform secure storage
  and retains drafts and pending material only to support participant recovery.
- Automated retention is disabled by default. It can run only after a
  controller-approved retention period is explicitly configured. This platform
  setting is not a replacement for a study-specific retention schedule.
- Withdrawal and deletion are server-side requests. The mobile app does not
  promise a deletion outcome or remove unsent participant material without an
  explicit participant action.

## Analytics, diagnostics and location

- The mobile dependency set contains no analytics, advertising or marketing
  SDK. It communicates with the Citizen Centric API only.
- Application Insights can be enabled by an environment connection string for
  operational telemetry. It is not a participant marketing or profiling tool;
  controller review of its data handling is still required before enabling it.
- Browser participant location collection exists only for an explicit
  participant-portal "Use my location" action. The Flutter app does not
  request location permission.
- Cookie/session handling is used for the authenticated web application. No
  optional analytics-cookie implementation was found in this review.

## AI and external processing boundary

- Participant mobile clients do not call OpenAI, Azure OpenAI, Azure Speech,
  Document Intelligence or Search directly.
- Evidence storage, scanning and any optional research intelligence processing
  are server-side. Research intelligence is disabled by default and its
  researcher-only outputs are not returned by participant APIs.
- Azure resource location is parameterised from the deployment resource group.
  The configured production and backup regions, transfer safeguards and any
  processor/subprocessor arrangements require controller confirmation.

## Governance and launch controls

Studies cannot be made live until an authorised user records controller
identity/contact, participant information, privacy information, lawful basis,
consent, retention approach, withdrawal/deletion handling, enabled features,
special-category assessment, ethics, DPIA, international-transfer assessment
and security considerations. AI research support additionally requires explicit
disclosure/approval in the study record.

## Remaining controller decisions

Before production launch, the controller must provide or approve:

1. study-specific participant information and privacy material, including
   version/reference and contact details;
2. lawful basis and any Article 9 condition where special-category data is
   involved;
3. study-specific retention, deletion/anonymisation and backup handling;
4. completed DPIA/ethics/transfer assessments and feature-specific safeguards;
5. operational telemetry, processor/subprocessor and Azure-region decisions;
6. the procedure for handling data-subject requests, including identity checks
   and statutory exceptions.

The present backend does not expose participant-facing withdrawal/deletion
status, message read state or voice transcription, and it does not provide a
resumable media-upload contract. Those capabilities have not been represented
as available in participant legal copy.
