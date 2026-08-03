# Stream B milestone 1: researcher communications

This milestone separates participant-visible communication from internal research notes and establishes the foundation for a dedicated researcher messaging workspace.

## Scope

- Participant-visible messages and internal notes must be presented as distinct workflows.
- Internal notes must never be exposed through participant-facing APIs, the participant portal, notifications, or exports intended for participants.
- Researcher messages must remain organisation- and study-scoped, CSRF-protected, authorised, and audited.
- Participant notification content must remain generic and avoid sensitive research content on a device lock screen.

## Delivery sequence

1. Separate the two communication types in the participant record UI.
2. Add focused regression tests for visibility and form intent.
3. Add a researcher conversation index grouped by participant and study.
4. Add unread/action state after the data model supports it explicitly.
5. Integrate researcher sends with the push-notification delivery service.

## Validation

```bash
PYTHONPATH=. pytest
ruff check --select F .
bandit -ll -r app
pip check
git diff --check
```
