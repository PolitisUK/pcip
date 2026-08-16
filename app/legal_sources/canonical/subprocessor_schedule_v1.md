<!-- Canonical source: 04_Citizen_Centric_Subprocessor_Schedule_v1.0.docx -->

Citizen Centric Subprocessor Schedule

Customer-facing schedule of active/planned services treated as active for publication

| Version | Effective date | Operator |
| --- | --- | --- |
| 1.0 | 15 August 2026 | Politis Ltd |

This Schedule identifies third-party service providers that Politis Ltd uses, or intends to use as active production services, to provide Citizen Centric. For this Version 1.0 schedule, services previously described as planned are treated as active at the owner’s instruction. Actual production deployment, region and contractual configuration should remain subject to release and supplier-account controls.

1. Microsoft Azure / Microsoft Corporation

| Provider | Service | Purpose | Data | Location | Transfer / training position |
| --- | --- | --- | --- | --- | --- |
| Microsoft | Azure hosting, compute, networking, database and storage services | Host and operate the Citizen Centric backend, data stores, APIs, media and supporting infrastructure. | Customer account data, Study Data, participant submissions/media, operational metadata. | UK and/or EU/EEA configured regions. | Restricted transfers, if any, require an applicable lawful mechanism and safeguards. |
| Microsoft | Azure Application Insights / Azure Monitor | Operational telemetry, diagnostics, reliability and security monitoring. | Technical events, request/diagnostic metadata, identifiers and IP/device information where logged; content only if intentionally configured. | UK and/or EU/EEA configured regions. | Operational telemetry only; not advertising or marketing profiling. |
| Microsoft | Azure OpenAI Service | Approved server-side AI research assistance, including summarisation, coding/thematic assistance and related analysis where enabled. | Approved Study Data and participant material necessary for the configured AI task. | UK and/or EU/EEA deployment where available/configured. | Customer/participant data must not be used to train public/shared foundation models; provider terms and deployment controls apply. |
| Microsoft | Azure AI Speech | Speech-to-text/transcription and related approved audio processing. | Participant audio and resulting transcription data/metadata. | UK and/or EU/EEA deployment where available/configured. | No use for public/shared model training under the Citizen Centric contractual position. |
| Microsoft | Azure AI Document Intelligence | Extraction/processing of approved uploaded documents. | Participant/customer documents and extracted text/structure. | UK and/or EU/EEA deployment where available/configured. | Processing limited to contracted service purpose; no public/shared model training. |
| Microsoft | Azure AI Search | Indexing and retrieval of authorised study/research material for platform search and approved AI-assisted workflows. | Authorised Study Data, indexed text, metadata and derived search indexes. | UK and/or EU/EEA deployment where available/configured. | Access remains tenant/study scoped; no public/shared model training. |

2. Processing safeguards

Subprocessors may process personal data only to provide the contracted Citizen Centric service and associated support/security functions.

Politis Ltd requires appropriate confidentiality, security and data-protection terms and remains responsible for its processor obligations under the DPA.

Production customer and participant data is intended to be held in the UK and/or EU/EEA. Any restricted transfer must use a lawful transfer mechanism and appropriate safeguards.

AI services are invoked server-side. Participant applications do not directly call AI providers.

Participant material and Study Data must not be used to train public or shared foundation models.

Internal researcher AI outputs are not participant-facing.

Customer-specific study governance, including lawful basis, Article 9 condition, DPIA/ethics and retention, must be approved before launch.

3. Changes to subprocessors

Politis Ltd may update this Schedule as the production architecture changes. Customers will be given reasonable advance notice of material additions or replacements where required by the DPA and will have the opportunity to raise a reasonable objection on data-protection grounds.

4. Region verification

The contractual data-location position for Citizen Centric is UK and/or EU/EEA. The precise Azure resource region(s) used for a production customer should be verified from the deployed Azure configuration and recorded through onboarding/governance. This Schedule does not represent that a particular Azure region has been technically verified merely by publication of this document.

5. Contact

Questions about subprocessors or data processing should be sent to info@politisconsulting.co.uk.
