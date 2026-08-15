/// Controlled, participant-facing platform legal content.
///
/// Study-specific information, privacy information, legal bases and retention
/// periods remain the controller's responsibility and must be supplied for the
/// relevant study. They are deliberately not inferred here.
class LegalDocument {
  const LegalDocument({
    required this.id,
    required this.title,
    required this.summary,
    required this.sections,
  });

  final String id;
  final String title;
  final String summary;
  final List<LegalSection> sections;
}

class LegalSection {
  const LegalSection(this.heading, this.paragraphs);

  final String heading;
  final List<String> paragraphs;
}

const legalPackVersion = '1.0';
const legalPackEffectiveDate = '15 August 2026';
const legalContactEmail = 'info@politisconsulting.co.uk';
const legalCompanyName = 'Politis Ltd';
const legalCompanyNumber = '13661766';
const legalIcoReference = 'ZB738312';

const participantInformationDocument = LegalDocument(
  id: 'participant-information',
  title: 'Participant information',
  summary: 'What to check before you decide whether to take part.',
  sections: [
    LegalSection('Before you decide', [
      'Taking part is your choice. Your research team should give you information about the purpose of this study, what it asks of you, who is running it and how to ask questions before you consent.',
      'This platform page explains Citizen Centric. It does not replace the study-specific information supplied by the research organisation.',
    ]),
    LegalSection('Taking part through Citizen Centric', [
      'You join using a private invitation code. There is no normal participant email-and-password sign-in.',
      'You can provide text, messages, photographs, documents or audio only when the relevant study asks for them and you choose to use those features.',
    ]),
    LegalSection('Your choices', [
      'You can ask to withdraw from a study or request deletion of your data. They are different requests. The study information and privacy information explain how the research organisation handles records that may already have been anonymised or cannot be linked back to you.',
    ]),
  ],
);

const privacyAtAGlanceDocument = LegalDocument(
  id: 'privacy-at-a-glance',
  title: 'Privacy at a glance',
  summary: 'A short explanation of how this app handles your information.',
  sections: [
    LegalSection('Who handles study information', [
      'The research organisation running your study may control its Study Data. Politis Ltd provides Citizen Centric and may process Study Data for that organisation.',
      'The study-specific privacy information tells you who to contact about that study and its data-protection arrangements.',
    ]),
    LegalSection('Using the app', [
      'Your responses are sent securely to Citizen Centric. Session credentials are stored using secure device storage. Drafts and queued text may temporarily remain on your device so they are not lost while you are offline.',
      'Photographs, documents and audio are uploaded only when you choose those features. The app asks for device permissions only when you try to use the relevant feature.',
    ]),
    LegalSection('AI and research support', [
      'Where a study uses authorised server-side processing, it is handled through Citizen Centric. The app does not send your material directly to public or shared AI services, and participant material is not used to train public or shared foundation models.',
      'You will not see researcher notes, working themes, suggested codes, Evidence Confidence or other internal research analysis in this app.',
    ]),
  ],
);

const privacyNoticeDocument = LegalDocument(
  id: 'privacy',
  title: 'Privacy notice',
  summary:
      'How Citizen Centric supports research organisations and participants.',
  sections: [
    LegalSection('Our role', [
      'Citizen Centric is provided by Politis Ltd. In many studies, the research organisation is the controller for Study Data and Politis Ltd processes that data on its documented instructions. The study-specific privacy information explains the arrangement for your study.',
      'Politis Ltd is registered in England and Wales. Registered office: The Old Courthouse, Orsett Road, Grays, Essex, England, RM17 5DD. Company number 13661766. ICO registration reference ZB738312.',
    ]),
    LegalSection('Keeping information', [
      'Information is kept only for as long as necessary for its purpose. Study Data follows the controller-approved retention period documented for the study. Where Politis Ltd acts as processor, it follows the controller’s documented retention and deletion instructions, subject to legal obligations.',
      'We do not use a single arbitrary retention period for every study.',
    ]),
    LegalSection('Your rights and requests', [
      'You can use the app to ask to withdraw from a study or request deletion of your data. These requests are sent to the server for handling; they are not a local-only action. You can also contact the research organisation named in your study information or Politis Ltd at info@politisconsulting.co.uk.',
    ]),
    LegalSection('Where information is processed', [
      'The approved platform policy is to host and process personal data in the UK and/or EU/EEA. Your study information should identify any study-specific arrangements that apply.',
    ]),
  ],
);

const termsDocument = LegalDocument(
  id: 'terms',
  title: 'Terms of use',
  summary: 'Using Citizen Centric as an invited participant.',
  sections: [
    LegalSection('Using the app', [
      'Use Citizen Centric only through an invitation from your research team and keep your invitation code private. The app supports participation in the study; it does not replace emergency, medical, legal or safeguarding services.',
    ]),
    LegalSection('Your content', [
      'Only submit material you are entitled to share. Do not upload content that is unlawful, harmful or intended to compromise another person’s privacy or security.',
    ]),
    LegalSection('Questions', [
      'For questions about your study, contact the research team named in your participant information. For platform contact, email info@politisconsulting.co.uk.',
    ]),
  ],
);

const cookiesDocument = LegalDocument(
  id: 'cookies',
  title: 'Cookies and app technologies',
  summary: 'The technologies used to keep the service working.',
  sections: [
    LegalSection('Website cookies', [
      'The web service uses strictly necessary session and security cookies where needed to provide authenticated access and protect requests. They are not used for advertising or cross-site behavioural tracking.',
    ]),
    LegalSection('This mobile app', [
      'Mobile drafts and secure session storage are not cookies. The app uses secure device storage for session credentials and local storage for the participant material needed to provide drafts and safe offline queueing.',
    ]),
    LegalSection('Analytics and tracking', [
      'Citizen Centric does not include marketing or participant-profiling tracking in this app. Operational diagnostics, security logging and service-performance telemetry may be used to run and protect the service. Non-essential analytics must not be enabled without the appropriate controls.',
    ]),
  ],
);

const accessibilityDocument = LegalDocument(
  id: 'accessibility',
  title: 'Accessibility',
  summary: 'Our approach to making participation usable for more people.',
  sections: [
    LegalSection('Our approach', [
      'Citizen Centric is designed with clear labels, meaningful status messages, scalable text, accessible touch targets and controls that do not rely on colour alone. We continue to test with assistive technologies and real devices.',
      'We do not claim a certification or full assistive-technology conformance that has not been independently verified.',
    ]),
    LegalSection('Getting help', [
      'If you experience a barrier, contact your research team or email info@politisconsulting.co.uk with enough detail for us to understand the problem.',
    ]),
  ],
);

const acceptableUseDocument = LegalDocument(
  id: 'acceptable-use',
  title: 'Acceptable use',
  summary: 'Using Citizen Centric safely and respectfully.',
  sections: [
    LegalSection('Please do', [
      'Use your own invitation, keep it private, and share only material relevant to the study that you are comfortable providing.',
    ]),
    LegalSection('Please do not', [
      'Do not try to access another participant’s information, bypass the app’s security, upload malicious files, or use the service to harass or harm anyone.',
    ]),
  ],
);

const consentInformationDocument = LegalDocument(
  id: 'consent-information',
  title: 'Consent information',
  summary: 'How consent works in this participant experience.',
  sections: [
    LegalSection('Research participation consent', [
      'Before taking part, you are asked to confirm that you understand and agree to participate. This is research participation consent. It is distinct from the data-protection lawful basis selected by the research organisation.',
      'Citizen Centric records consent only through the study’s server-side consent process. The study-specific consent wording, version and any required statements remain controlled by the research organisation.',
    ]),
    LegalSection('Changing your mind', [
      'You can ask to withdraw later. The consequences are explained before you send the request and are handled according to the study’s information and server-authorised process.',
    ]),
  ],
);

const dataRightsDocument = LegalDocument(
  id: 'data-rights',
  title: 'Your data rights',
  summary: 'How to ask for help with your information.',
  sections: [
    LegalSection('Requests in the app', [
      'The Privacy choices area lets you ask to withdraw from a study or request deletion. A deletion request is not the same as an immediate deletion, and the app will not promise that it has already been completed.',
    ]),
    LegalSection('Other requests', [
      'For access, correction or other data-protection requests, contact the research organisation named in your study information. You can also contact Politis Ltd at info@politisconsulting.co.uk about the Citizen Centric service.',
    ]),
  ],
);

const legalInformationDocument = LegalDocument(
  id: 'legal-information',
  title: 'Legal information',
  summary: 'Company and contact information for Citizen Centric.',
  sections: [
    LegalSection('Citizen Centric', [
      'Citizen Centric is provided by Politis Ltd. Company number 13661766. Registered office: The Old Courthouse, Orsett Road, Grays, Essex, England, RM17 5DD.',
      'ICO registration/reference: ZB738312. Contact: info@politisconsulting.co.uk.',
    ]),
  ],
);

const participantLegalDocuments = [
  privacyAtAGlanceDocument,
  privacyNoticeDocument,
  participantInformationDocument,
  consentInformationDocument,
  termsDocument,
  cookiesDocument,
  accessibilityDocument,
  acceptableUseDocument,
  dataRightsDocument,
  legalInformationDocument,
];
