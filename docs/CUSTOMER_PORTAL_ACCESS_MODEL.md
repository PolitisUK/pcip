# Customer portal access model

Citizen Centric separates platform operations from customer research work.

| Experience | Authority | Scope |
| --- | --- | --- |
| Politis platform administrator | Explicit `users.is_platform_admin` grant through the controlled bootstrap process | Platform operational overview only; it is not conferred by an organisation role. |
| Organisation owner / administrator | `organisation_memberships.role` of `owner` or `admin` | Their active organisation, subject to server-side object and study checks. |
| Researcher | `organisation_memberships.role` of `researcher` plus `study_access` where required | Assigned studies in their active organisation. |
| Participant | Invitation-bound participant session | Their invitation, participant and enrolled study only. |

Organisation identifiers are carried only in authenticated server-side session
context. Routes resolve studies, participants, evidence, messages, governance,
exports and documents with the active organisation before returning an object.
The browser navigation is a convenience only; it is not an authorisation
boundary.

`/admin` is intentionally a separate Politis operational view. It requires the
explicit platform grant and responds as not found to organisation accounts, so a
customer cannot discover or enumerate platform administration through the UI.
Customer administrators cannot grant the platform flag through organisation
team management. Initial platform provisioning is an audited, explicitly
confirmed operational bootstrap action.
