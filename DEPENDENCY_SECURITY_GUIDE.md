# Dependency Security and Update Guide

This guide defines a practical technical process for dependency hygiene in this repository.

## CI checks

CI performs:
- `pip check` to detect broken/incompatible dependency resolution.
- `pip-audit -r requirements.txt` to identify known vulnerabilities.
- `bandit` on `app/` for Python security anti-patterns.

## Update cadence

Recommended technical cadence:
- Weekly: review available dependency updates.
- Monthly: apply non-breaking updates and run full test suite.
- Urgent: patch critical/high CVEs immediately.

## Suggested update workflow

1. Create an update branch.
2. Upgrade targeted packages in `requirements.txt`.
3. Run:
   - `python -m pip install -r requirements.txt`
   - `python -m pip check`
   - `python -m pip-audit -r requirements.txt`
   - `python -m pytest -q`
4. Verify release artifact build still succeeds.
5. Merge with release notes summarizing upgraded packages and risk.

## Prioritisation guidance

Prioritise upgrades in this order:
1. Known exploited vulnerabilities.
2. Critical/high CVEs in internet-exposed components.
3. Auth/session/crypto/networking dependencies.
4. Remaining medium/low vulnerabilities.

## Runtime impact target

Security checks are kept lightweight and are intended to add minimal runtime by:
- running security checks in a dedicated parallel CI job,
- keeping release verification to a short health-endpoint smoke test.
