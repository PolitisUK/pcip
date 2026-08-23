// Controlled, participant-facing platform legal content.
// Study-specific information, privacy information, legal bases and retention
// periods remain the controller's responsibility and must be supplied for the
// relevant study. They are deliberately not inferred here.
import 'legal_content.generated.dart';

export 'legal_content.generated.dart';

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
      'You can withdraw from this study, withdraw and delete identifiable active study data, or delete your Citizen Centric account for this organisation. These are different actions. Information that has already been irreversibly anonymised or aggregated cannot be linked back to you; pseudonymised information remains personal data.',
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

const participantLegalDocuments = platformLegalDocuments;
