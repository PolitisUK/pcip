<!-- Canonical source: AI Services Schedule - Revised.docx -->

Effective Date: 15 August 2026 | Version: 1.0

AI SERVICES SCHEDULE

1.1 SCOPE AND APPLICATION

1.1.1 This Schedule governs the use of artificial intelligence, machine learning, inference and related automated processing capabilities ("AI Services") within the Citizen Centric platform operated by Politis Ltd ("Service Provider"). It forms part of the Organisation SaaS Terms Agreement and is incorporated into it by reference.

1.1.1A Politis Ltd is a company registered in England and Wales (company number 13661766), with registered office at The Old Courthouse, Orsett Road, Grays, Essex, England, RM17 5DD. Politis Ltd is registered with the Information Commissioner’s Office under reference ZB738312.

1.1.2 This Schedule applies to all AI-assisted processing performed server-side on or in connection with Study Data, Participant Material and related content submitted through the platform. It does not govern any processing performed solely on a Participant's device.

1.1.3 Where this Schedule conflicts with the main Organisation SaaS Terms Agreement or the Data Processing Agreement (Schedule A), this Schedule prevails in respect of AI Services.

1.2 CONFIRMED AND UNCONFIRMED AI FEATURES

1.2.1 The following AI-assisted functions are identified as potential or planned uses within the platform architecture. No function listed in this clause 1.2 shall be described as active, deployed or available to Customers unless and until the Service Provider has confirmed in writing that the relevant feature has been deployed, tested and governed in accordance with clause 1.5:

1.2.1.1 transcription of voice diary recordings and audio submissions;

1.2.1.2 translation of Participant Material into alternative languages;

1.2.1.3 summarisation of study submissions for researcher review;

1.2.1.4 semantic search across study content;

1.2.1.5 suggested qualitative labels, codes or themes for researcher use;

1.2.1.6 accessibility processing of uploaded materials;

1.2.1.7 content moderation and security screening of uploads; and

1.2.1.8 help and support functions.

1.2.2 Current approved server-side AI service categories include Microsoft Azure OpenAI, Azure AI Speech, Azure AI Document Intelligence and Azure AI Search, used only where the relevant contracted/study feature is enabled. Upload security and malware scanning is also used for supported uploads. The participant mobile application does not send Participant Material directly to AI-provider endpoints. Internal researcher outputs such as suggested codes, themes, confidence scores, researcher notes and contradiction analysis are not participant-facing. Participant-facing transcription is not currently exposed as a mobile-app feature.

1.2.3 Features not confirmed as active under clause 1.2.2 must not be represented to Customers or Participants as available, and no contractual reliance may be placed upon them.

1.3 AI INPUTS AND PERMITTED USES

1.3.1 AI Services may process the following categories of input only to the extent necessary for the confirmed permitted purpose and the Customer's documented instructions:

1.3.1.1 Participant Material submitted through the platform, including text responses, audio recordings, photographs, documents and associated metadata;

1.3.1.2 study configuration data and researcher-defined parameters; and

1.3.1.3 technical and diagnostic data required for platform operation and security.

1.3.2 The Service Provider shall process Participant Material through AI Services solely:

1.3.2.1 on the Customer's instructions as documented in the applicable Order Form or study configuration; or

1.3.2.2 as strictly necessary for platform security, integrity and the provision of the contracted services.

1.3.3 The Customer shall not instruct the Service Provider to apply AI Services to Participant Material in a manner that would constitute solely automated decision-making producing legal or similarly significant effects on Participants without a lawful assessed basis, appropriate safeguards and, where required, prior notification to Participants.

1.4 RESTRICTION ON MODEL TRAINING

1.4.1 The Service Provider shall not use, and shall ensure that its employees, contractors and AI sub-processors do not use, Participant Material or Study Data:

1.4.1.1 to train, fine-tune, adapt or improve any public, shared or third-party foundation model;

1.4.1.2 as input training data or prompts in any generative AI tooling or technology operated by or accessible to any party other than the Service Provider acting within the scope of this Agreement; or

1.4.1.3 to develop, benchmark or evaluate any AI model or system for purposes beyond the contracted services.

1.4.2 The restriction in clause 1.4.1 applies whether processing occurs directly or indirectly and whether Participant Material is identifiable or pseudonymised. Aggregated or anonymised information may only be used outside the contracted study where it has been rendered genuinely anonymous so that no individual is identifiable by reasonably available means, and where that use is lawful and consistent with the applicable notices and Agreement.

1.4.3 The Service Provider shall obtain equivalent contractual restrictions from each AI sub-processor engaged in connection with the platform, as further described in clause 1.7.

1.5 GOVERNANCE AND DEPLOYMENT REQUIREMENTS

1.5.1 Before activating any AI feature that processes Participant Material, the Service Provider shall:

1.5.1.1 identify and document the AI provider, model, processing location and data retention period applicable to that feature;

1.5.1.2 conduct or commission a Data Protection Impact Assessment where required under UK GDPR Article 35 and document the outcome;

1.5.1.3 assess whether the feature requires a research ethics review and, if so, obtain the relevant approval before deployment;

1.5.1.4 implement human oversight proportionate to the risk profile of the feature, including defined escalation and review procedures; and

1.5.1.5 notify the Customer in writing of the feature's activation, the applicable provider and processing location, and any material change to those details.

1.5.2 The AI feature register shall record the approved provider/service, processing purpose, UK/EU/EEA processing location, data categories, human oversight and retention criteria for each enabled feature. For the current approved service categories: Current approved server-side AI service categories include Microsoft Azure OpenAI, Azure AI Speech, Azure AI Document Intelligence and Azure AI Search, used only where the relevant contracted/study feature is enabled. Upload security and malware scanning is also used for supported uploads. The participant mobile application does not send Participant Material directly to AI-provider endpoints. Internal researcher outputs such as suggested codes, themes, confidence scores, researcher notes and contradiction analysis are not participant-facing. Participant-facing transcription is not currently exposed as a mobile-app feature.

1.6 CONFIDENTIALITY OF AI OUTPUTS

1.6.1 The following categories of AI-generated output are designated as internal researcher outputs and must not be displayed to, accessible by or inferred by Participants at any time:

1.6.1.1 suggested qualitative codes or labels;

1.6.1.2 Evidence Confidence scores or ratings;

1.6.1.3 researcher notes generated or assisted by AI;

1.6.1.4 working themes or thematic groupings; and

1.6.1.5 contradiction analysis or consistency assessments.

1.6.2 The Service Provider shall implement and maintain technical controls to enforce the separation described in clause 1.6.1, and shall not design or configure the platform in a manner that would expose internal researcher AI outputs through the Participant-facing application, API responses or notifications.

1.6.3 The Customer shall not configure studies or instruct the Service Provider in a manner that would cause internal AI outputs to be disclosed to Participants.

1.7 AI SUB-PROCESSORS AND PROVIDER DILIGENCE

1.7.1 The Service Provider shall, before engaging any third-party AI provider to process Participant Material or Study Data:

1.7.1.1 conduct due diligence on the provider's data protection practices, model-training policies, data retention terms and processing locations;

1.7.1.2 enter into a written agreement with the provider that includes obligations equivalent to those in this Schedule, including the model-training restriction in clause 1.4 and the confidentiality obligations in clause 1.6;

1.7.1.3 confirm that the provider's terms do not permit the use of Customer or Participant data to train, improve or develop the provider's models or services; and

1.7.1.4 notify the Customer of the identity of each AI sub-processor and the nature of its involvement, in accordance with the sub-processor notification procedure in the Data Processing Agreement.

1.7.2 Microsoft Azure is the approved cloud/AI service family for the AI capabilities described in this Schedule. Relevant production processing is configured for UK and/or EU/EEA locations. The active service categories are Azure OpenAI, Azure AI Speech, Azure AI Document Intelligence and Azure AI Search where the relevant contracted/study feature is enabled. Equivalent contractual restrictions on model training and confidentiality apply to each enabled service.

1.7.3 Where a Customer raises a reasonable objection to an AI sub-processor on data protection grounds, the parties shall cooperate in good faith to identify an alternative solution. If no alternative is available and the objection cannot be resolved, either party may terminate the affected AI feature on written notice without liability for that termination alone.

1.8 PERSONAL DATA AND SPECIAL-CATEGORY DATA

1.8.1 Where AI Services process personal data, such processing shall be conducted in accordance with the Data Processing Agreement and the applicable lawful basis documented by the Customer as controller.

1.8.2 Where AI Services may process special-category data as defined in UK GDPR Article 9 (including health data, ethnicity, religious beliefs, political opinions, trade union membership, genetic or biometric data, or data concerning sex life or sexual orientation), the Customer shall:

1.8.2.1 identify and document the applicable Article 9 condition before activating the relevant AI feature; and

1.8.2.2 ensure that the study-specific Participant privacy notice and information sheet accurately describe the AI processing and the applicable condition.

1.8.3 The Service Provider shall not apply AI Services to special-category data beyond the scope of the Customer's documented instructions and the applicable lawful basis.

1.9 OUTPUT ACCURACY, BIAS AND HALLUCINATION

1.9.1 The Service Provider shall take reasonable and proportionate steps to assess active AI features for accuracy, bias, hallucination and other material output risks before and during production use, having regard to the feature, intended purpose and reasonably foreseeable impact. No warranty is given that AI outputs will be error-free.

1.9.2 The Customer acknowledges that AI-generated outputs, including transcriptions, translations, summaries, suggested codes and themes, may contain errors, omissions, inaccuracies or content that does not reflect the source material, and that such outputs are provided as research assistance tools only.

1.9.3 The Customer shall not place sole or determinative reliance on any AI-generated output for research conclusions, ethical assessments, regulatory submissions or decisions affecting Participants without independent human review.

1.9.4 The Service Provider shall maintain proportionate records of material known limitations, validation results and bias or quality assessments for active AI features and shall make appropriate information available to the Customer on reasonable written request, subject to security, confidentiality and third-party restrictions.

1.10 HUMAN OVERSIGHT AND RESEARCH INTEGRITY

1.10.1 The Service Provider shall ensure that each active AI feature is subject to human oversight proportionate to its risk, including:

1.10.1.1 defined procedures for identifying and escalating anomalous, harmful or inaccurate outputs;

1.10.1.2 mechanisms for Customers to flag, correct or reject AI-generated outputs; and

1.10.1.3 audit logging of AI processing events sufficient to support investigation of incidents.

1.10.2 The Customer is responsible for maintaining research integrity in studies conducted on the platform, including ensuring that AI-assisted analysis is disclosed in research outputs to the extent required by applicable research governance standards and the Customer's ethics approval.

1.10.3 Neither party shall use AI Services in a manner that undermines the validity, reproducibility or ethical conduct of research studies hosted on the platform.

1.11 PROHIBITED USES OF AI SERVICES

1.11.1 The following uses of AI Services are prohibited:

1.11.1.1 processing Participant Material for any purpose unrelated to the study for which it was submitted;

1.11.1.2 using AI outputs to re-identify anonymised or pseudonymised Participants;

1.11.1.3 applying AI Services to generate content that misrepresents Participant responses or fabricates study data;

1.11.1.4 using AI Services to profile Participants for commercial, marketing or non-research purposes; and

1.11.1.5 deploying AI features that produce solely automated decisions with legal or similarly significant effects on Participants without a lawful assessed basis and appropriate safeguards.

1.12 INTELLECTUAL PROPERTY IN AI OUTPUTS

1.12.1 AI-generated outputs produced by processing the Customer's Study Data or Participant Material shall be treated as work product of the Customer for the purposes of this Agreement, subject to any underlying rights of the AI provider in the model or tooling used to generate them.

1.12.2 The Service Provider does not warrant that AI-generated outputs are original, that intellectual property rights subsist in them, or that their use will not infringe third-party rights. The Customer is responsible for assessing the IP position of AI outputs before relying upon or publishing them.

1.12.3 The Customer shall ensure that it has the rights, permissions or other lawful authority necessary to submit Customer-provided materials for the contracted AI processing. Any indemnity relating to third-party intellectual-property claims shall apply only to the extent expressly provided in the main Agreement.

1.13 SECURITY AND INCIDENT HANDLING

1.13.1 The Service Provider shall apply to AI processing pipelines the same technical and organisational security measures required under the Data Processing Agreement, including access controls, encryption in transit and at rest, audit logging and least-privilege access.

1.13.2 The mobile client shall not transmit Participant Material directly to any AI provider's endpoint. All AI processing shall be mediated through authorised server-side services operated or controlled by the Service Provider.

1.13.3 Where a security incident affects AI processing pipelines or AI-generated outputs, the Service Provider shall notify the Customer in accordance with the incident notification procedure in the Data Processing Agreement, and shall additionally document the nature of any AI-specific risk arising from the incident.

1.14 CHANGE CONTROL

1.14.1 The Service Provider shall give the Customer reasonable prior written notice, and where practicable not less than 30 days' notice, before:

1.14.1.1 activating a new AI feature that processes Participant Material;

1.14.1.2 changing the AI provider, model or processing location for any active AI feature; or

1.14.1.3 materially altering the scope, purpose or data inputs of any active AI feature.

1.14.2 Where a proposed change would require the Customer to update its Participant privacy notices, ethics approval or lawful basis documentation, the Service Provider shall identify this in its notice and shall not implement the change until the Customer confirms in writing that the necessary updates have been made.

1.14.3 Where a proposed change would materially and adversely affect the Customer's research governance obligations and the parties cannot agree a resolution within 30 days of the notice (or such other period agreed in writing), the Customer may terminate the affected AI feature on written notice without liability for that termination alone.

1.15 RETENTION AND DELETION OF AI INPUTS AND OUTPUTS

1.15.1 Personal data is kept only for as long as it is necessary for the purpose for which it was collected, in line with the UK GDPR storage-limitation principle. There is no single fixed retention period prescribed by UK GDPR. Study Data must have a controller-approved, study-specific retention period recorded before a study is launched. Politis Ltd follows that documented instruction when acting as processor, subject to legal, regulatory, security, dispute-resolution or backup obligations that require limited further retention. Material AI-derived outputs retained as part of a study follow the same controller-approved study retention schedule as the related Study Data unless a shorter period is specified. Temporary provider-side processing artefacts must not be retained longer than necessary for the requested processing and must not be retained for model training or improvement.

1.15.2 The Service Provider shall delete or return AI inputs and outputs in accordance with the deletion and return obligations in the Data Processing Agreement upon termination of the relevant study or this Agreement, whichever is earlier, unless a longer retention period is required by law.

1.15.3 The Service Provider shall configure AI sub-processors so that Participant Material is retained only for the period necessary for the contracted processing, subject to documented security, abuse-monitoring or legal retention requirements that cannot lawfully be disabled. The Service Provider shall verify and document applicable provider retention and model-training terms before production use.

1.16 LIABILITY

1.16.1 The Service Provider's liability for loss or damage arising from AI-generated outputs, including errors, inaccuracies, bias or hallucination, is subject to the liability cap and exclusions in the main Organisation SaaS Terms Agreement.

1.16.2 The Service Provider shall not be liable for loss or damage arising from the Customer's reliance on AI-generated outputs in breach of clause 1.9.3, or from the Customer's failure to maintain human oversight of AI-assisted research processes.

1.16.3 Nothing in this Schedule limits either party's liability for death or personal injury caused by negligence, fraud or fraudulent misrepresentation, or any other liability that cannot be excluded or limited under applicable law.

1.17 PARTICIPANT-FACING TERMS

1.17.1 Where any active AI feature processes Participant Material in a manner that requires disclosure to Participants under UK GDPR Articles 13 or 14, the Customer shall ensure that the applicable study-specific Participant privacy notice and Participant information sheet accurately describe:

1.17.1.1 the nature of the AI processing and its purpose;

1.17.1.2 the identity of any AI sub-processor involved, to the extent required by transparency obligations;

1.17.1.3 the lawful basis and, where applicable, the Article 9 condition; and

1.17.1.4 the fact that AI-generated outputs used in the research are subject to human review.

1.17.2 The Service Provider shall provide the Customer with sufficient technical information about each active AI feature to enable the Customer to fulfil its transparency obligations under this clause 1.17.

1.17.3 Participant-facing interfaces shall not display, reference or imply the existence of internal researcher AI outputs described in clause 1.6.1.

1.18 DATA PROTECTION ROLES AND INSTRUCTIONS

1.18.1 Unless the parties expressly agree otherwise for a particular processing activity, the Customer determines the research purposes and lawful basis for Study Data and Participant Material and acts as controller, while Politis Ltd processes such data as processor on the Customer’s documented instructions. Nothing in this Schedule overrides the allocation of roles in the Data Processing Agreement.

1.18.2 The Service Provider shall not use Participant Material to train public or shared foundation models and shall not permit Participant-facing mobile clients to call AI-provider endpoints directly. AI processing of Participant Material must be mediated through authorised server-side services.

1.19 AI GOVERNANCE RECORDS

1.19.1 The Service Provider shall maintain proportionate records for active AI Services, including feature purpose, provider, data categories, processing location, retention configuration, risk assessment, human oversight, material changes and incidents. These records may form part of the Service Provider’s DPIA, records of processing, security documentation or AI feature register.

1.19.2 Where an AI feature could materially change the risks to Participants, the Service Provider and Customer shall review the relevant DPIA, transparency information, ethics position and safeguards before activation.

1.20 PARTICIPANT SAFEGUARDS

1.20.1 Internal Researcher AI Outputs, including suggested qualitative codes, Evidence Confidence, researcher notes, working themes and contradiction analysis, are researcher-facing material and shall not be exposed through participant interfaces.

1.20.2 AI Services shall not be used to make solely automated decisions producing legal or similarly significant effects on Participants unless the parties have expressly agreed the use, established a lawful basis, completed the necessary assessment and implemented all required safeguards. Nothing in this Schedule authorises such use by default.

Defined terms:

"AI Services" means artificial intelligence, machine learning, inference and related automated processing capabilities applied server-side within or in connection with the Citizen Centric platform, including the features described in clause 1.2.1 to the extent confirmed as active under clause 1.2.2.

"AI Sub-Processor" means a third-party provider engaged by the Service Provider to perform AI or inference processing on Participant Material or Study Data in connection with the platform, as recorded in the Service Provider's current sub-processor and AI feature records.

"Customer" means the research organisation that has entered into the Organisation SaaS Terms Agreement with the Service Provider and is accessing the platform for research purposes.

"Internal Researcher AI Outputs" means AI-generated outputs designated for researcher use only, including suggested qualitative codes or labels, Evidence Confidence scores or ratings, AI-assisted researcher notes, working themes or thematic groupings, and contradiction analysis or consistency assessments.

"Participant Material" means material submitted by or about a Participant through the platform in connection with a study, including text, audio, photographs, documents and associated metadata.

"Study Data" means data and content relating to a Customer's study that is processed through the platform, including Participant Material and study configuration data.
