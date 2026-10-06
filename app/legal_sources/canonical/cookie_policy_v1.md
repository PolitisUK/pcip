<!-- Canonical source: Citizen Centric Cookie Policy - Revised.docx -->

Citizen Centric Cookie and Similar Technologies Policy

Effective Date: 15 August 2026

Last Updated: 15 August 2026

Version: 1.0

About this policy

Politis Ltd (company number 13661766), whose registered office is The Old Courthouse, Orsett Road, Grays, Essex, England, RM17 5DD, operates Citizen Centric. Politis Ltd is registered with the Information Commissioner's Office under reference ZB738312.

This policy explains how cookies and similar technologies may be used on the Citizen Centric public website, researcher-facing web services and participant mobile application. It should be read with the applicable privacy notice and, for research participants, the study-specific participant information and privacy information provided by the relevant research organisation.

This register reflects the live production deployment reviewed on 2 October 2026. It is updated before a technology is added, removed or its use materially changes.

1. Cookies and similar technologies

Cookies are small data files stored by a website in a browser. Similar technologies can include browser local storage, application storage, software development kits (SDKs), device permissions and other mechanisms used to maintain sessions, remember settings, provide security or support application functions.

The participant mobile application does not use browser cookies. It uses native secure storage and local application storage to maintain a signed-in session, retain participant-selected drafts and support offline submission or upload retrying. These are not advertising or analytics cookies.

2. Categories of technology

2.1 Strictly necessary

Strictly necessary technologies are used to provide a requested service or protect the service. In Citizen Centric, these include session/authentication mechanisms, CSRF protection and the app storage needed for an active participant session and offline work.

Where the PECR strictly-necessary exemption applies, consent is not required for that storage or access. The exemption is applied narrowly and does not automatically cover analytics or convenience features.

2.2 Functional

No functional cookie or similar browser technology is active in the reviewed production deployment.

2.3 Analytics and performance

Citizen Centric uses Microsoft Azure Application Insights and Log Analytics for operational diagnostics, security logging and service performance. This telemetry is not used for advertising, behavioural profiling or cross-site marketing. The application does not configure request or response-body capture; application access-log filtering redacts bearer-style values in URLs.

2.4 Marketing and targeting

No marketing, advertising, attribution or cross-site tracking cookie or SDK is active in the reviewed production deployment. This includes Google Analytics, Meta/Facebook Pixel, behavioural advertising, session replay and heatmap services.

3. Mobile application storage and permissions

The participant app stores its API URL and access token with `flutter_secure_storage`, using native operating-system protected storage (iOS Keychain and Android Keystore-backed storage). Its sign-out and privacy-session-end flows delete this storage. The app does not control whether an operating system retains protected storage after an app is uninstalled or restored from a device backup.

The app uses `shared_preferences` for drafts, queued text submissions, cached participant/study content, message/history caches and evidence-receipt and upload-queue metadata. Queued photos, documents and voice recordings are copied to the app support directory until upload succeeds, the participant removes them, or the session is cleared. Drafts are removed after submission; queued files are removed after successful upload. The sign-out and privacy-session-end flows clear these local records and queued files. The app does not use a local database, IndexedDB or a mobile analytics, advertising or crash-reporting SDK.

Camera, microphone, photo-library or file access is controlled through operating-system permissions when the participant chooses the relevant feature. Granting an operating-system permission is not consent to analytics or marketing.

Participant material must not be sent directly from the mobile application to an AI provider. Any authorised server-side AI processing is governed separately by the applicable privacy information and AI Services arrangements.

4. Cookie and technology register

| Technology | Provider | Service | Purpose | Duration | Status / consent |
| --- | --- | --- | --- | --- | --- |
| `csrf_session` | Politis Ltd / Starlette | Interactive web pages | Holds the CSRF token and short-lived UI security state used to protect form submissions. | Browser session | Strictly necessary; no optional-consent use. |
| `session` | Politis Ltd | Researcher and administrator web service | Authenticates a signed-in staff user and their selected organisation. | Up to 12 hours | Strictly necessary; no optional-consent use. |
| `public_auth_session` | Politis Ltd | Password reset, researcher invitation and participant-portal web flows | Maintains a server-revocable, HttpOnly public-flow session after a one-time link is exchanged. | 15 minutes for password reset; 1 hour for researcher invitation; up to 12 hours for participant portal | Strictly necessary; no optional-consent use. |
| `flutter_secure_storage` | Apple / Google device security services | Participant mobile app | Stores the API URL and access token in operating-system protected storage. | Until sign-out or privacy-session-end clearing; operating-system behaviour governs removal on uninstall or backup restore. | Strictly necessary for an authenticated app session; not a browser cookie and no optional-consent use. |
| `shared_preferences` and app support files | Participant device | Participant mobile app | Stores drafts, queued submissions, cached participant/study content, evidence receipts, upload metadata and queued participant-selected files for offline use and retrying. | Until submitted, uploaded, removed by the participant or cleared when the session ends. | Strictly necessary for the requested offline and retry functions; not a browser cookie and no optional-consent use. |
| Azure Application Insights and Log Analytics | Microsoft Azure | Web service and backend | Security, error diagnosis, application logs, request/dependency performance and service reliability. Request and response bodies are not configured for capture. | 30 days in the configured Log Analytics workspace | Operational telemetry; not used for marketing, advertising or cross-site tracking. |

5. Managing choices

The reviewed production deployment has no optional cookie or similar technology for a user to manage. Browser settings can delete or block browser cookies, although blocking strictly necessary cookies may prevent protected web functions from working. Mobile operating systems provide separate controls for permissions such as camera, microphone, photos and notifications.

6. Third parties and international transfers

Microsoft Azure provides the operational telemetry in the register. The applicable privacy notice explains processing locations and international-transfer safeguards.

7. Retention

Cookies and similar technologies are retained for the durations in the register. Study Data is retained under the controller-approved, study-specific retention period and the applicable privacy notice.

8. Changes to this policy

Politis Ltd updates this policy and register when deployed technologies, services or legal requirements change. Material changes affecting choices or privacy will be communicated through an appropriate channel.

9. Contact

Questions about this policy or Citizen Centric's use of cookies and similar technologies can be sent to:

Politis Ltd
The Old Courthouse, Orsett Road, Grays, Essex, England, RM17 5DD
ICO reference: ZB738312
Email: info@politisconsulting.co.uk

Individuals may also raise data-protection concerns with the Information Commissioner's Office. The applicable privacy notice should contain the current complaints information and contact route.
