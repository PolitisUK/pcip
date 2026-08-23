// GENERATED FILE - do not edit by hand.

class LegalDocument {
  const LegalDocument({required this.id, required this.title, required this.summary, required this.sections});
  final String id;
  final String title;
  final String summary;
  final List<LegalSection> sections;
}

class LegalSection {
  const LegalSection(this.heading, this.paragraphs, {this.bullets = const [], this.level = 2});
  final String heading;
  final List<String> paragraphs;
  final List<String> bullets;
  final int level;
}

const legalPackVersion = '1.1';
const legalPackEffectiveDate = '18 August 2026';
const legalContactEmail = 'info@politisconsulting.co.uk';
const legalCompanyName = 'Politis Ltd';
const legalCompanyNumber = '13661766';
const legalIcoReference = 'ZB738312';

const platformPrivacyNoticeDocument = LegalDocument(
  id: "privacy",
  title: "Platform Privacy Notice",
  summary: "How Politis Ltd handles personal information when operating Citizen Centric.",
  sections: [
    LegalSection("Publication details", [
      "Operator — Politis Ltd (company number 13661766)",
      "Version — 1.1",
      "Effective date — 18 August 2026",
    ],
      level: 2,
    ),
    LegalSection("Important information", [
      "This is the platform-level privacy notice. Each research study must also provide study-specific privacy information identifying its controller, purposes, lawful bases, data uses and retention arrangements.",
    ],
      level: 2,
    ),
    LegalSection("About this notice", [
      "Citizen Centric is a research participation and study-management platform operated by Politis Ltd. It includes the participant mobile application, public websites and APIs, and researcher and organisation administration services.",
      "This notice explains the processing for which Politis Ltd is responsible. It should be read with the Participant Information Sheet and privacy notice supplied by the organisation responsible for the relevant study.",
    ],
      level: 2,
    ),
    LegalSection("When Politis Ltd is controller", [
      "Politis Ltd acts as controller when it decides why and how personal information is used to operate, secure, administer and support Citizen Centric, including customer and researcher account administration, platform security, service support and operational diagnostics.",
    ],
      level: 3,
    ),
    LegalSection("When Politis Ltd is processor", [
      "For information collected and used for a particular research study (Study Data), the research organisation normally acts as controller and Politis Ltd acts as its processor. Politis Ltd processes that Study Data on the controller's documented instructions. The study-specific privacy notice identifies the controller and explains the arrangements for that study.",
      "Any different allocation of responsibilities must be documented before the study begins.",
    ],
      level: 3,
    ),
    LegalSection("Information handled by Citizen Centric", [
      "Depending on how the Platform and a study are configured, Citizen Centric may handle:",
    ],
      bullets: [
        "account and access information, including researcher and organisation account details, participant invitation records, and session and authentication information;",
        "study participation information, including enrolment, research-consent status, withdrawal status, activity responses, diary entries and structured responses;",
        "participant-submitted material, including text, photographs, documents and audio, with associated submission metadata;",
        "messages and support enquiries;",
        "technical and security information, including IP address, device or browser information, timestamps, diagnostic events, audit logs and security events;",
        "information stored on a participant's device for operation of the app, including drafts, cached content and queued submissions awaiting upload; and",
        "where a study enables an approved AI-assisted feature, processing inputs and researcher-facing outputs such as transcriptions, translations, summaries, suggested codes or themes.",
      ],
      level: 2,
    ),
    LegalSection("Why Politis Ltd uses information", [
      "Where Politis Ltd acts as controller, it uses personal information for the following purposes and lawful bases:",
      "Where Politis Ltd relies on legitimate interests, it considers whether the processing is necessary and balances those interests against the rights and interests of the individuals affected.",
      "The study controller selects and documents the lawful basis for Study Data and, where relevant, a condition for special-category or criminal-offence data. Consent to participate in research is not automatically the same as consent used as a data-protection lawful basis.",
    ],
      bullets: [
        "to provide the Platform and perform agreements with customers and users, where processing is necessary for the performance of a contract;",
        "to administer customer and researcher relationships and provide support, where necessary for contract performance or for Politis Ltd's legitimate interest in managing its services and business relationships;",
        "to protect accounts, prevent misuse, investigate security events, maintain auditability and operate a reliable service, based on Politis Ltd's legitimate interests in security, integrity and service continuity;",
        "to comply with legal, regulatory and accounting obligations, where processing is necessary to comply with law; and",
        "to diagnose faults and improve operational reliability, based on Politis Ltd's legitimate interest in maintaining a secure and dependable service.",
      ],
      level: 2,
    ),
    LegalSection("Sensitive information", [
      "A study may collect special-category information, such as health information or information revealing political opinions, ethnicity, religion or sexual orientation, where this is necessary for the approved research design. The study controller must identify a valid Article 9 condition, provide suitable privacy information and complete any required ethics review or Data Protection Impact Assessment before launch.",
      "If criminal-offence data is processed, the study controller must also identify and document an applicable legal condition. Politis Ltd processes this information only within the applicable instructions and Platform controls.",
    ],
      level: 2,
    ),
    LegalSection("AI-assisted processing", [
      "Approved server-side AI services may be enabled for a study to support functions such as transcription, translation, summarisation, semantic search, suggested qualitative codes, accessibility processing, content moderation, security screening or support. A feature is not treated as active unless it has been deployed, tested and governed under the applicable AI Services Schedule.",
    ],
      bullets: [
        "The participant mobile application does not send material directly to third-party AI endpoints; authorised processing is mediated through services operated or controlled by Politis Ltd.",
        "Participant material and Study Data are not used to train or improve public or shared foundation models.",
        "AI outputs are research-assistance material and require human review.",
        "Citizen Centric does not use AI as the sole basis for decisions producing legal or similarly significant effects on participants.",
        "Any active study-specific AI processing must be explained in the study's Participant Information Sheet and privacy notice where required.",
      ],
      level: 2,
    ),
    LegalSection("Cookies, local storage and telemetry", [
      "The participant app does not include advertising or marketing-tracking software. Operational diagnostics, security logging and service-performance telemetry may be used to operate and protect the service. They are not used for advertising, cross-site behavioural tracking or participant marketing profiles.",
      "The mobile app uses secure device storage for session credentials and local device storage for drafts, cached content and safe offline queueing. Website cookies and similar technologies are described in the Citizen Centric Cookie and App Technologies Policy. Non-essential technologies requiring consent will not be enabled before valid consent is obtained.",
    ],
      level: 2,
    ),
    LegalSection("Who receives information", [
      "Politis Ltd uses contracted service providers, including Microsoft Azure services, to host, secure and operate Citizen Centric. The current Sub-processor Schedule identifies active providers and services. Providers may process information only for the contracted service and subject to appropriate confidentiality, security and data-protection obligations.",
    ],
      bullets: [
        "Study Data is not sold.",
        "Access is limited to authorised personnel, the relevant study organisation and approved collaborators with a legitimate role.",
        "Information may be disclosed to professional advisers, insurers, auditors, regulators, courts or public authorities where reasonably necessary or legally required.",
        "The study controller is responsible for identifying study-specific sponsors, funders, collaborators or other recipients in its own privacy notice.",
      ],
      level: 2,
    ),
    LegalSection("Where information is processed", [
      "Citizen Centric's approved platform policy is to host and process personal information in the United Kingdom and/or the European Union or European Economic Area. Primary production services are hosted in the United Kingdom. Supplier support or service arrangements may involve access or processing from another country.",
      "Where processing creates a restricted international transfer, the relevant controller and processor will use an appropriate legal mechanism, such as adequacy regulations, the UK International Data Transfer Agreement or the UK Addendum to approved EU Standard Contractual Clauses, with supplementary safeguards where required. Study-specific arrangements must be stated in the relevant study privacy notice.",
    ],
      level: 2,
    ),
    LegalSection("How long information is kept", [
      "Study Data follows the retention period or retention criteria approved and documented by the study controller before launch. There is no single retention period that is appropriate for every study. When Politis Ltd acts as processor, it follows the controller's documented retention and deletion instructions, subject to limited legal, regulatory, security, dispute-resolution and backup requirements.",
    ],
      bullets: [
        "Operational and security records are kept only for as long as reasonably necessary for their purpose and applicable legal obligations.",
        "Local drafts and queued items are cleared through the relevant app workflows, subject to successful synchronisation and any study-specific requirements.",
        "After confirmed deletion from active systems, protected production backups expire within up to 14 days and are not used for ordinary research access.",
        "Irreversibly anonymised information is no longer personal information and may be retained for approved research, statistical or analytical purposes. Pseudonymised information remains personal information.",
      ],
      level: 2,
    ),
    LegalSection("Security", [
      "Politis Ltd uses technical and organisational measures designed to protect personal information, including scoped access controls, encryption in transit using HTTPS, protected cloud storage, audit and security logging, file-validation controls, tenant and study separation, and secure session handling. No internet-connected service can be guaranteed completely secure.",
      "Suspected security incidents or data-protection concerns may be reported to info@politisconsulting.co.uk.",
    ],
      level: 2,
    ),
    LegalSection("Your choices and rights", [
      "Withdrawal from a study, deletion of Study Data and deletion of a Citizen Centric account are separate actions. The study's information must explain their consequences. Withdrawal does not necessarily require deletion of information already lawfully processed or retained, and information already irreversibly anonymised or incorporated into completed analysis may no longer be linkable to an individual.",
      "Depending on the circumstances and lawful basis, individuals may have rights to be informed, access personal information, correct inaccurate information, request erasure, restrict processing, object to processing, receive eligible information in a portable format, and safeguards relating to solely automated decisions. Statutory conditions and research exemptions may apply.",
    ],
      level: 2,
    ),
    LegalSection("Important information", [
      "Right to object: where processing is based on legitimate interests or a public task, you may have the right to object. This right is brought to your attention separately because it depends on the purpose and lawful basis for the processing.",
      "For Study Data, contact the controller named in the study-specific privacy notice. You may also contact Politis Ltd. Further details are provided in the Citizen Centric Data Rights Policy.",
    ],
      level: 2,
    ),
    LegalSection("Data-protection complaints", [
      "You may make a data-protection complaint to the relevant study controller or to Politis Ltd using the contact details below. Politis Ltd will provide a clear route for complaints, acknowledge a complaint within 30 days, take appropriate steps to investigate it without undue delay, keep the complainant appropriately informed and communicate the outcome.",
      "You also have the right to complain to the Information Commissioner's Office. Visit https://ico.org.uk/make-a-complaint/ or telephone 0303 123 1113. You do not have to contact Politis Ltd before contacting the ICO, although doing so may allow the concern to be resolved more quickly.",
    ],
      level: 2,
    ),
    LegalSection("Children and young people", [
      "Citizen Centric is invitation-only. A study involving children or young people must establish appropriate age, capacity, parental-responsibility, safeguarding, ethics and transparency arrangements before launch. The study controller must provide information in a form the intended participants can understand. No universal parental-consent age is imposed by this platform notice because the applicable requirements depend on the study, its legal basis and its ethics arrangements.",
    ],
      level: 2,
    ),
    LegalSection("Changes and contact", [
      "Material changes to this notice will be versioned and published with an updated effective date. Study-specific notices are separately versioned. Continued use will not be treated as a substitute where renewed consent or acceptance is legally required.",
      "Politis Ltd The Old Courthouse, Orsett Road, Grays, Essex, England, RM17 5DD Email: info@politisconsulting.co.uk ICO registration reference: ZB738312",
    ],
      level: 2,
    ),
  ],
);

const dataRightsPolicyDocument = LegalDocument(
  id: "data-rights",
  title: "Data Rights Policy",
  summary: "How to exercise data-protection rights and raise a complaint.",
  sections: [
    LegalSection("Publication details", [
      "Operator — Politis Ltd (company number 13661766)",
      "Version — 1.1",
      "Effective date — 18 August 2026",
    ],
      level: 2,
    ),
    LegalSection("Important information", [
      "For information collected for a research study, the research organisation named in the study privacy notice is normally the controller and decides how a rights request is handled. Politis Ltd will provide reasonable assistance when acting as processor.",
    ],
      level: 2,
    ),
    LegalSection("Scope", [
      "This policy explains how individuals may exercise rights under the UK GDPR and Data Protection Act 2018 in connection with Citizen Centric. It complements the Platform Privacy Notice and the privacy information supplied for each study.",
    ],
      level: 2,
    ),
    LegalSection("To be informed", [
      "You are entitled to clear information about how personal information is collected and used. The Platform Privacy Notice and study-specific information provide this.",
    ],
      level: 3,
    ),
    LegalSection("Access", [
      "You may ask whether your personal information is being processed and request a copy together with supporting information about the processing.",
    ],
      level: 3,
    ),
    LegalSection("Rectification", [
      "You may ask for inaccurate personal information to be corrected and incomplete information to be completed.",
    ],
      level: 3,
    ),
    LegalSection("Erasure", [
      "You may ask for personal information to be erased in circumstances set out in law, including where it is no longer needed or consent is withdrawn where consent is the lawful basis. This right is not absolute.",
    ],
      level: 3,
    ),
    LegalSection("Restriction", [
      "You may ask for processing to be restricted in circumstances set out in law, including while accuracy or an objection is being considered.",
    ],
      level: 3,
    ),
    LegalSection("Data portability", [
      "Where processing is automated and based on consent or contract, you may be entitled to receive personal information you provided in a structured, commonly used and machine-readable format, or ask for it to be transmitted to another controller where technically feasible.",
    ],
      level: 3,
    ),
    LegalSection("Automated decisions", [
      "Where a solely automated decision has legal or similarly significant effects, you may have rights to obtain human intervention, express your point of view and contest the decision. Citizen Centric does not use AI as the sole basis for such decisions about participants.",
    ],
      level: 3,
    ),
    LegalSection("Important information", [
      "You may object to processing based on legitimate interests or a public task. The controller must stop unless it demonstrates compelling legitimate grounds overriding your interests, rights and freedoms, or the processing is needed for legal claims. An objection to direct marketing is absolute; Citizen Centric does not use participant information for direct marketing.",
    ],
      level: 2,
    ),
    LegalSection("Limits and exemptions", [
      "Rights depend on the purpose and lawful basis for processing and may be subject to statutory conditions or exemptions. A research exemption is not automatic: the controller must assess whether its legal requirements are met in the particular circumstances.",
    ],
      bullets: [
        "Irreversibly anonymised information is not personal information and cannot be linked back to an individual by reasonably available means.",
        "Pseudonymised information remains personal information and continues to be protected.",
        "A response may need to protect the rights and confidentiality of another person, including through proportionate redaction.",
        "Information may be retained where erasure is not required, including to meet legal obligations, establish or defend legal claims, or where a valid research-related exemption applies.",
      ],
      level: 2,
    ),
    LegalSection("How to make a request", [
      "A request may be made in the app where the relevant option is available, by contacting the controller named in the study-specific privacy notice, or by contacting Politis Ltd using the details below. You do not need to use special wording or a particular form.",
      "Please explain which right you wish to exercise and provide enough information to identify the relevant account, organisation or study. Do not send a password, full invitation code, session token or verification code by email.",
      "We may request information reasonably necessary to confirm identity or authority. We will not request more identification than is proportionate to the risk.",
    ],
      level: 2,
    ),
    LegalSection("Response times", [
      "A valid rights request will be handled without undue delay and normally within one month of receipt, or within one month after receiving information reasonably required to confirm identity or authority. The exact deadline is calculated by calendar month, not as a fixed 30-day period.",
      "The period may be extended by up to a further two months where a request is complex or the same person has made a number of requests. If an extension is needed, the requester will be told within the initial one-month period and given the reasons.",
      "Where clarification is reasonably required to identify the information or processing requested, the response clock may pause while clarification is awaited. Advice and assistance will be provided to help clarify the request.",
    ],
      level: 2,
    ),
    LegalSection("Study Data and processor assistance", [
      "The study controller determines the substantive response to a request about Study Data. If Politis Ltd receives such a request while acting as processor, it will route the request securely to the relevant controller and assist in accordance with the applicable Data Processing Agreement. Politis Ltd decides requests relating to processing for which it acts as controller.",
    ],
      level: 2,
    ),
    LegalSection("Children and people needing support", [
      "Data-protection rights belong to children as well as adults. Whether a child can exercise a right directly, or whether a person with parental responsibility or another authorised representative may act, depends on the child's understanding, the circumstances and applicable law. Information and assistance will be provided in an accessible and age-appropriate way where reasonably required.",
      "A person may authorise someone else to act for them. Reasonable evidence of authority may be requested before information is disclosed.",
    ],
      level: 2,
    ),
    LegalSection("AI-assisted processing", [
      "Approved AI-assisted functions may support transcription, translation, thematic organisation, summarisation and search. Outputs are research-assistance tools subject to human review. Participant material is not used to train public or shared foundation models, and active study-specific AI processing must be disclosed in the relevant study information.",
    ],
      level: 2,
    ),
    LegalSection("Data-protection complaints", [
      "A concern about the handling of personal information may be raised with the relevant study controller or with Politis Ltd. A complaint does not need to use legal terminology. It should describe the concern and provide enough information for it to be investigated.",
      "You may complain to the Information Commissioner's Office at any time. Visit https://ico.org.uk/make-a-complaint/ or telephone 0303 123 1113. You do not have to complete Politis Ltd's complaints process first.",
    ],
      bullets: [
        "Politis Ltd will provide a clear route for making a data-protection complaint.",
        "The complaint will be acknowledged within 30 days of receipt.",
        "Appropriate steps will be taken to investigate it without undue delay.",
        "The complainant will be kept appropriately informed and told the outcome.",
      ],
      level: 2,
    ),
    LegalSection("Contact and updates", [
      "Politis Ltd The Old Courthouse, Orsett Road, Grays, Essex, England, RM17 5DD Email: info@politisconsulting.co.uk ICO registration reference: ZB738312",
      "Material changes to this policy will be versioned and published with an updated effective date.",
    ],
      level: 2,
    ),
  ],
);

const accessibilityPolicyDocument = LegalDocument(
  id: "accessibility",
  title: "Accessibility Policy",
  summary: "Our approach to accessible participation and reasonable adjustments.",
  sections: [
    LegalSection("Publication details", [
      "Operator — Politis Ltd (company number 13661766)",
      "Version — 1.1",
      "Effective date — 18 August 2026",
    ],
      level: 2,
    ),
    LegalSection("Important information", [
      "Citizen Centric is designed to make participation usable for as many people as reasonably possible. Accessibility is an ongoing product requirement, not a one-off certification exercise.",
    ],
      level: 2,
    ),
    LegalSection("Scope and commitment", [
      "This policy applies to the Citizen Centric participant mobile application, public website and researcher and organisation administration services operated by Politis Ltd.",
      "Politis Ltd takes account of its duties as a service provider under the Equality Act 2010, including the anticipatory duty to make reasonable adjustments for disabled people. We review barriers and consider reasonable changes to practices, digital features and methods of providing information.",
    ],
      level: 2,
    ),
    LegalSection("Design approach", [
      "Citizen Centric is designed and tested with accessibility in mind. Depending on the interface and supported device, our approach includes:",
      "We use the Web Content Accessibility Guidelines (WCAG) 2.2 as a reference for accessible design and aim toward Level AA where applicable to the interface and technology.",
    ],
      bullets: [
        "meaningful labels and semantic information for interactive controls;",
        "support for scalable text and layouts intended to tolerate larger text;",
        "touch-target, contrast and colour-use checks;",
        "logical headings, focus order and navigation in web interfaces;",
        "plain-language participant journeys and clear confirmation of significant actions;",
        "explanations before camera, microphone or photo-library permissions are requested;",
        "status information that does not rely on colour alone; and",
        "accessibility checks within regression and release quality assurance.",
      ],
      level: 2,
    ),
    LegalSection("Current conformance position", [
      "Citizen Centric has not been independently certified as fully conformant with WCAG 2.2 AA. Testing continues with assistive technologies, larger text settings, keyboard navigation where applicable, and real devices. Coverage cannot include every combination of device, operating-system version, browser and assistive technology.",
      "Third-party operating-system dialogues and device behaviour may vary and are not fully controlled by Politis Ltd. We will not claim certification or complete compatibility that has not been independently verified.",
    ],
      level: 2,
    ),
    LegalSection("Known limitations", [
      "At the effective date, comprehensive independent accessibility auditing and exhaustive assistive-technology testing across all supported combinations have not been completed. Some study-specific documents or media supplied by research organisations may not be accessible in every format unless an alternative is provided.",
      "If a barrier is reported, we will investigate it, record any confirmed limitation and consider an interim alternative or reasonable adjustment while remediation is assessed.",
    ],
      level: 2,
    ),
    LegalSection("Consent, privacy and significant choices", [
      "Consent screens, privacy choices and preference controls should be operable at enlarged text sizes, understandable without relying on colour alone and usable with supported assistive technologies. Optional cookie or similar-technology controls will not be pre-selected, and rejecting optional technologies will be as easy as accepting them.",
    ],
      level: 2,
    ),
    LegalSection("Getting help or requesting an adjustment", [
      "If you cannot access information or complete a task because of an accessibility barrier, contact your research team or Politis Ltd. If possible, tell us:",
      "You do not need to disclose a diagnosis. We will consider a reasonable alternative method of access and investigate the reported barrier. Reasonable adjustments will not be charged to the person requiring them.",
    ],
      bullets: [
        "the content or function you need to access;",
        "the device, operating system and browser you are using;",
        "any assistive technology or accessibility setting involved; and",
        "the format or adjustment that would help.",
      ],
      level: 2,
    ),
    LegalSection("Study-specific information", [
      "The research organisation responsible for a study controls its participant information, questionnaires, prompts and uploaded study materials. It is responsible for ensuring those materials are suitable for the intended participants and for providing reasonable alternative formats where required, such as accessible electronic text, large print, audio or plain-language information.",
      "Politis Ltd's platform commitments do not remove the research organisation's separate equality, accessibility, safeguarding or ethics responsibilities.",
    ],
      level: 2,
    ),
    LegalSection("Feedback and response", [
      "Accessibility feedback may be sent to info@politisconsulting.co.uk or to the postal address below. We will acknowledge the concern, investigate the reported barrier, consider any immediate adjustment and explain the outcome or planned next step. Urgent study-participation questions should also be raised with the research team named in the Participant Information Sheet.",
    ],
      level: 2,
    ),
    LegalSection("Review and contact", [
      "This policy is reviewed after material platform changes, following significant accessibility findings and periodically as testing develops. Changes will be versioned and published with an updated effective date.",
      "Politis Ltd The Old Courthouse, Orsett Road, Grays, Essex, England, RM17 5DD Email: info@politisconsulting.co.uk ICO registration reference: ZB738312",
    ],
      level: 2,
    ),
  ],
);

const consentNoticeDocument = LegalDocument(
  id: "consent",
  title: "Consent Notice",
  summary: "How research participation consent is obtained, recorded and withdrawn.",
  sections: [
    LegalSection("Publication details", [
      "Operator — Politis Ltd (company number 13661766)",
      "Version — 1.1",
      "Effective date — 18 August 2026",
    ],
      level: 2,
    ),
    LegalSection("Important information", [
      "This platform notice explains the general consent process used by Citizen Centric. It does not enrol anyone in a study and does not replace the participant information, privacy notice and consent statements approved for the particular study.",
    ],
      level: 2,
    ),
    LegalSection("Scope", [
      "This notice applies to people invited to take part in research through Citizen Centric, the research participation and study-management platform operated by Politis Ltd. The research organisation running each study is responsible for the study design, participant information, consent wording and ethics or governance approvals.",
      "Before deciding whether to take part, you should receive study-specific information explaining:",
    ],
      bullets: [
        "who is running and funding the study and how to contact the research team;",
        "the study's purpose, duration and what participation involves;",
        "any reasonably foreseeable risks, burdens, benefits or payments;",
        "what information will be collected, including any photographs, audio, documents or other media;",
        "how personal information will be used, shared, protected and retained;",
        "whether approved AI-assisted processing will be used; and",
        "how to withdraw, what withdrawal changes, and what may happen to information already provided.",
      ],
      level: 2,
    ),
    LegalSection("Voluntary participation", [
      "Taking part is voluntary. You may decline an invitation, ask questions before deciding, or withdraw later without giving a reason. Declining or withdrawing should not affect any service or benefit to which you are otherwise entitled. Any study-specific effect on a payment or incentive must be explained before you consent.",
      "You may choose not to provide optional material. A study may identify information that is needed to complete a particular activity; if you do not provide it, that activity may not be capable of submission. The study information should make this clear.",
    ],
      level: 2,
    ),
    LegalSection("What your consent confirms", [
      "When you give study-participation consent through Citizen Centric, you confirm that:",
      "Consent must be an affirmative choice. Optional consent choices will not be pre-selected or bundled with unrelated matters. If you do not understand the information, contact the research team before agreeing to participate.",
    ],
      bullets: [
        "you have been given the current participant information and study privacy notice;",
        "you have had a reasonable opportunity to read or receive that information and ask questions;",
        "you understand what the study asks you to do and any material risks or burdens explained to you;",
        "you understand that participation is voluntary and how to withdraw;",
        "you understand what will happen to information already submitted if you withdraw; and",
        "you agree to take part and affirm any additional study-specific consent statements shown to you.",
      ],
      level: 2,
    ),
    LegalSection("Important information", [
      "Consent to participate in research is not automatically the same as consent used as a lawful basis for processing personal information under the UK GDPR.",
      "The research organisation acting as controller must identify and explain the applicable UK GDPR Article 6 lawful basis and, where special-category information is processed, the applicable Article 9 condition. These may be consent or another lawful basis or condition. Where data-protection consent is relied upon, the study documentation must explain how it can be withdrawn and the effect of withdrawal on processing already carried out lawfully.",
    ],
      level: 2,
    ),
    LegalSection("How consent is recorded", [
      "Citizen Centric records consent through the study's server-authorised consent process. The record links the affirmative response to the relevant participant, study, consent wording or version, and date and time. The research organisation controls the approved wording and determines how long the record must be retained for research governance and accountability.",
      "An invitation code provides access to an invited participant journey; it is not, by itself, a record of informed consent. Device permissions for the camera, microphone or photo library are also separate from consent to participate and from any data-protection consent.",
    ],
      level: 2,
    ),
    LegalSection("Optional activities and material changes", [
      "A study may ask separately for agreement to genuinely optional activities, such as providing audio, photographs or other additional material. Refusing an optional activity should not be treated as refusing the whole study unless the activity is an essential part of the approved study design and this was made clear.",
      "If the study's purpose, procedures, risks, data collection or other material terms change, the research organisation must provide updated information and obtain renewed consent where required before further participation under the changed arrangements. Continued app use will not be treated as renewed consent where an affirmative confirmation is required.",
    ],
      level: 2,
    ),
    LegalSection("Withdrawing from a study", [
      "You may ask to withdraw using the option provided in the app or by contacting the research team named in the participant information. The consequences must be shown before an in-app request is sent, and the service will confirm when the request has been processed.",
      "Withdrawal from participation, deletion of identifiable Study Data and deletion of a Citizen Centric account are different actions. Withdrawal does not retrospectively make earlier participation or processing unlawful and does not always require deletion of information already collected. The controller must apply the study information, applicable law and any valid research safeguards or exemptions.",
    ],
      bullets: [
        "Identifiable information remains personal information and must continue to be protected.",
        "Pseudonymised information remains personal information even when direct identifiers are held separately.",
        "Information that has been irreversibly anonymised so that it can no longer be linked to you is no longer personal information and cannot ordinarily be retrieved as your data.",
        "A withdrawal or deletion request will not be described as complete until the server-authorised process confirms the relevant action.",
      ],
      level: 2,
    ),
    LegalSection("Children, capacity and supported participation", [
      "A study involving children, young people or adults who may need support must establish appropriate age, capacity, parental-responsibility, safeguarding and ethics arrangements before launch. There is no single platform-wide age at which parental permission is always required; the correct arrangement depends on the study, the participant's understanding, applicable law and the study's approvals.",
      "Information should be provided in a form the intended participant can understand. A supporter may help a person read information or operate the app where the approved study arrangements permit this, but must not answer, submit material or give consent on the participant's behalf unless they have lawful authority and that arrangement is permitted and documented for the study.",
    ],
      level: 2,
    ),
    LegalSection("AI-assisted processing", [
      "Where approved AI-assisted functions are active for a study, their purpose and relevant safeguards must be explained in the study-specific participant information and privacy notice. Functions may support tasks such as transcription, translation, thematic organisation or summarisation. Outputs are research-assistance tools subject to human review. Participant material is not used to train public or shared foundation models.",
    ],
      level: 2,
    ),
    LegalSection("Accessibility and questions", [
      "You may ask for participant information or consent material in a reasonably accessible format. If you need help understanding the study, an adjustment, or more time to decide, contact the research team before consenting. You do not have to disclose a diagnosis when describing an accessibility barrier.",
      "Questions about the study, its consent statements or the consequences of withdrawal should be directed first to the research team named in the participant information. Questions about the Citizen Centric platform may also be sent to Politis Ltd using the contact details below.",
    ],
      level: 2,
    ),
    LegalSection("Contact and updates", [
      "Politis Ltd The Old Courthouse, Orsett Road, Grays, Essex, England, RM17 5DD Email: info@politisconsulting.co.uk ICO registration reference: ZB738312",
      "Material changes to this platform notice will be versioned and published with an updated effective date. Study-specific participant information and consent wording are separately controlled and versioned by the research organisation.",
    ],
      level: 2,
    ),
  ],
);

const platformLegalDocuments = [
  platformPrivacyNoticeDocument,
  dataRightsPolicyDocument,
  accessibilityPolicyDocument,
  consentNoticeDocument,
];
