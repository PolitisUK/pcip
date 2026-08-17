from pathlib import Path

from scripts.ip_compliance import classify_licence, source_fingerprints


def test_ip_compliance_refuses_absent_or_copyleft_licence_evidence():
    assert classify_licence(None)[1] == "BLOCKER_UNKNOWN"
    assert classify_licence("AGPL-3.0-only")[1] == "BLOCKER_NETWORK_COPYLEFT"
    assert classify_licence("GPL-3.0-only")[1] == "BLOCKER_STRONG_COPYLEFT"
    assert classify_licence("LGPL-3.0-only")[1] == "HUMAN_LEGAL_REVIEW"
    assert classify_licence("CC-BY-NC-4.0")[1] == "BLOCKER_NON_COMMERCIAL"
    # Licence text may mention GPL compatibility without making the component
    # GPL-licensed; the explicit expression remains controlling evidence.
    assert classify_licence("Python-2.0", "GPL-compatible wording")[0] == "PSF-2.0"


def test_ip_compliance_fingerprints_all_committed_dependency_manifests():
    fingerprints = source_fingerprints()
    assert "requirements.lock" in fingerprints
    assert "mobile/participant-app/package-lock.json" in fingerprints
    assert "participant_app/pubspec.lock" in fingerprints
    assert all(len(value) == 64 for value in fingerprints.values())
    assert Path("IP_COMPLIANCE.md").is_file()
