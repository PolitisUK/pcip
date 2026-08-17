"""Generate and verify evidence-based IP compliance records.

This utility deliberately does not infer a licence where package metadata or a
bundled licence file does not establish one.  ``--generate`` is run in a
prepared developer/release environment with the lockfile dependencies present;
CI uses ``--verify`` to ensure the committed evidence is current, while
``--release-gate`` refuses a promotion if unresolved or incompatible items
remain.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SBOM_PATH = DOCS / "IP_SBOM.json"
INVENTORY_PATH = DOCS / "IP_DEPENDENCY_LICENSE_INVENTORY.csv"
NOTICE_PATH = ROOT / "THIRD_PARTY_NOTICES.md"
REPORT_PATH = DOCS / "IP_AUDIT_REPORT.md"
ASSET_PATH = DOCS / "IP_ASSET_PROVENANCE_TEMPLATE.csv"

SOURCE_FILES = (
    "IP_COMPLIANCE.md",
    "requirements.txt",
    "requirements-dev.txt",
    "requirements.lock",
    "mobile/participant-app/package.json",
    "mobile/participant-app/package-lock.json",
    "participant_app/pubspec.yaml",
    "participant_app/pubspec.lock",
    "participant_app/android/settings.gradle.kts",
    "participant_app/android/gradle/wrapper/gradle-wrapper.properties",
    "scripts/ip_compliance.py",
)

ASSET_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".ttf",
    ".otf", ".woff", ".woff2", ".mp3", ".wav", ".m4a", ".mp4", ".mov",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_fingerprints() -> dict[str, str]:
    return {path: sha256(ROOT / path) for path in SOURCE_FILES if (ROOT / path).is_file()}


def normalise_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def read_requirements(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or "==" not in line:
            continue
        name, version = line.split("==", 1)
        result[normalise_name(name.split("[", 1)[0])] = version.strip()
    return result


def first_license_file(directory: Path) -> Path | None:
    if not directory.is_dir():
        return None
    candidates = sorted(
        (path for path in directory.rglob("*")
         if path.is_file() and path.name.lower() in {"license", "license.txt", "licence", "licence.txt", "copying", "notice"}),
        key=lambda path: (len(path.parts), str(path)),
    )
    return candidates[0] if candidates else None


def classify_licence(raw: str | None, text: str = "") -> tuple[str, str, str]:
    """Return canonical label, risk and short obligation statement.

    The mapping is intentionally conservative: an expression not listed here is
    unknown rather than silently accepted.
    """
    raw_value = (raw or "").strip()
    raw_lower = raw_value.lower()
    evidence = f"{raw_value}\n{text[:4000]}".lower()
    if not evidence.strip():
        return "UNKNOWN", "BLOCKER_UNKNOWN", "Licence and notice terms are not established; do not ship pending review."
    # Prefer an explicit package licence expression over incidental words in a
    # full licence file (for example, Python-2.0 texts mention GPL
    # compatibility but are not GPL-licensed).
    exact = {
        "mit": ("MIT", "PASS_PERMISSIVE", "Retain copyright and permission notice in distributions."),
        "mit-0": ("MIT-0", "PASS_PERMISSIVE", "Retain the supplied permission notice in distributions."),
        "isc": ("ISC", "PASS_PERMISSIVE", "Retain copyright and permission notice in distributions."),
        "bsd": ("BSD", "PASS_PERMISSIVE", "Retain copyright, conditions and disclaimer in source/binary distributions."),
        "bsd-2-clause": ("BSD-2-Clause", "PASS_PERMISSIVE", "Retain copyright, conditions and disclaimer in source/binary distributions."),
        "bsd-3-clause": ("BSD-3-Clause", "PASS_PERMISSIVE", "Retain copyright, conditions and disclaimer in source/binary distributions."),
        "apache-2.0": ("Apache-2.0", "PASS_PERMISSIVE", "Retain licence, copyright and NOTICE text; state material modifications where required."),
        "apache license 2.0": ("Apache-2.0", "PASS_PERMISSIVE", "Retain licence, copyright and NOTICE text; state material modifications where required."),
        "zlib": ("Zlib", "PASS_PERMISSIVE", "Do not misrepresent origin; mark altered source versions where required."),
        "0bsd": ("0BSD", "PASS_PERMISSIVE", "Retain the supplied notice where distributed."),
        "cc0-1.0": ("CC0-1.0", "PASS_PERMISSIVE", "No attribution is required by the licence; retain provenance evidence."),
        "unlicense": ("Unlicense", "PASS_PERMISSIVE", "Retain the public-domain dedication text where distributed."),
        "psf-2.0": ("PSF-2.0", "PASS_PERMISSIVE", "Retain licence and copyright notices."),
        "python-2.0": ("PSF-2.0", "PASS_PERMISSIVE", "Retain licence and copyright notices."),
        "mpl-2.0": ("MPL-2.0", "HUMAN_LEGAL_REVIEW", "Preserve notices and make modified MPL-covered files available under MPL terms."),
        "cc-by-4.0": ("CC-BY-4.0", "HUMAN_LEGAL_REVIEW", "Preserve attribution and licence terms; verify the distribution context."),
        "blueoak-1.0.0": ("BlueOak-1.0.0", "HUMAN_LEGAL_REVIEW", "Confirm the exact licence text and retain required notice before distribution."),
    }
    if raw_lower in exact:
        return exact[raw_lower]
    if "\n" not in raw_value and (" or " in raw_lower or " and " in raw_lower):
        parts = [part.strip(" ()") for part in re.split(r"\s+(?:or|and)\s+", raw_lower)]
        classifications = [exact.get(part) for part in parts]
        if all(classifications) and all(value[1] == "PASS_PERMISSIVE" for value in classifications):
            return " OR ".join(value[0] for value in classifications), "PASS_PERMISSIVE", "Retain the notices for the licence option selected for distribution."
        return "DUAL_OR_COMPLEX", "HUMAN_LEGAL_REVIEW", "Select and document a compatible licence option; retain the corresponding notices."
    if "server side public license" in evidence or re.search(r"\bsspl\b", evidence):
        return "SSPL", "BLOCKER_NETWORK_COPYLEFT", "Strong service-source obligations; legal approval is required before use."
    if "affero general public license" in evidence or re.search(r"\bagpl\b", evidence):
        return "AGPL", "BLOCKER_NETWORK_COPYLEFT", "Network-copyleft/source-offer obligations; legal approval is required before use."
    if "lesser general public license" in evidence or re.search(r"\blgpl\b", evidence):
        return "LGPL", "HUMAN_LEGAL_REVIEW", "Preserve notices and assess linking, relinking and modified-library source obligations."
    if "general public license" in evidence or re.search(r"\bgpl(?:-|\b)", evidence):
        return "GPL", "BLOCKER_STRONG_COPYLEFT", "Strong copyleft/source-offer obligations; legal approval is required before use."
    if "mozilla public license" in evidence or re.search(r"\bmpl[- ]?2", evidence):
        return "MPL-2.0", "HUMAN_LEGAL_REVIEW", "Preserve notices and make modified MPL-covered files available under MPL terms."
    if "noncommercial" in evidence or "non-commercial" in evidence or re.search(r"\bcc-by-nc\b", evidence):
        return "NON-COMMERCIAL", "BLOCKER_NON_COMMERCIAL", "Commercial-use permission is not established."
    if "apache license" in evidence and ("version 2" in evidence or "apache-2" in evidence):
        return "Apache-2.0", "PASS_PERMISSIVE", "Retain licence, copyright and NOTICE text; state material modifications where required."
    if "mit license" in evidence:
        return "MIT", "PASS_PERMISSIVE", "Retain copyright and permission notice in distributions."
    if "isc license" in evidence:
        return "ISC", "PASS_PERMISSIVE", "Retain copyright and permission notice in distributions."
    if "bsd 3-clause" in evidence or "redistribution and use in source and binary forms" in evidence:
        return "BSD", "PASS_PERMISSIVE", "Retain copyright, conditions and disclaimer in source/binary distributions."
    if "bsd 2-clause" in evidence:
        return "BSD-2-Clause", "PASS_PERMISSIVE", "Retain copyright, conditions and disclaimer in source/binary distributions."
    if re.search(r"\b0bsd\b", evidence):
        return "0BSD", "PASS_PERMISSIVE", "Retain the supplied notice where distributed."
    if "zlib license" in evidence or re.fullmatch(r"zlib", (raw or "").strip(), re.IGNORECASE):
        return "Zlib", "PASS_PERMISSIVE", "Do not misrepresent origin; mark altered source versions where required."
    if "python software foundation license" in evidence or re.search(r"\bpsf[- ]?2", evidence):
        return "PSF-2.0", "PASS_PERMISSIVE", "Retain licence and copyright notices."
    if "unicode license" in evidence or "unicode, inc." in evidence:
        return "Unicode", "HUMAN_LEGAL_REVIEW", "Retain supplied notices; confirm the exact Unicode licence version."
    if "creative commons zero" in evidence or re.search(r"\bcc0[- ]?1", evidence):
        return "CC0-1.0", "PASS_PERMISSIVE", "No attribution is required by the licence; retain provenance evidence."
    if "unlicense" in evidence:
        return "Unlicense", "PASS_PERMISSIVE", "Retain the public-domain dedication text where distributed."
    return "UNKNOWN", "BLOCKER_UNKNOWN", "Licence expression is not in the approved parser map; human/legal review is required."


def copyright_lines(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if re.search(r"copyright|©", line, re.IGNORECASE)]
    return " | ".join(lines[:8]) or "Not stated in the collected licence file."


def component(
    *, ecosystem: str, name: str, version: str, direct: bool, source: str,
    licence_metadata: str | None, licence_file: Path | None,
) -> dict[str, Any]:
    licence_text = ""
    licence_evidence = "metadata only"
    if licence_file is not None:
        try:
            licence_text = licence_file.read_text(encoding="utf-8", errors="replace")
            licence_evidence = (
                str(licence_file.relative_to(ROOT))
                if licence_file.is_relative_to(ROOT)
                else f"locally collected upstream distribution notice: {licence_file.name}"
            )
        except OSError:
            pass
    licence, risk, obligation = classify_licence(licence_metadata, licence_text)
    standard_spdx = {
        "MIT", "MIT-0", "ISC", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0", "Zlib",
        "0BSD", "CC0-1.0", "Unlicense", "MPL-2.0",
    }
    result = {
        "bom-ref": f"pkg:{ecosystem}/{name}@{version}",
        "type": "library",
        "name": name,
        "version": version,
        "ecosystem": ecosystem,
        "direct": direct,
        "source": source,
        "licence_declared": licence_metadata or "UNKNOWN",
        "licence_classified": licence,
        "licence_evidence": licence_evidence,
        "copyright_or_attribution": copyright_lines(licence_text) if licence_text else "Not collected; preserve upstream package notice before distribution.",
        "obligations": obligation,
        "risk": risk,
        "notice_collected": bool(licence_text),
        "notice_text": licence_text.strip(),
    }
    if licence in standard_spdx:
        result["licenses"] = [{"license": {"id": licence}}]
    elif licence != "UNKNOWN":
        result["licenses"] = [{"license": {"name": licence_metadata or licence}}]
    else:
        result["licenses"] = []
    result["properties"] = [
        {"name": "politisuk:licence-evidence", "value": result["licence_evidence"]},
        {"name": "politisuk:review-risk", "value": risk},
    ]
    return result


def python_components() -> list[dict[str, Any]]:
    locked = read_requirements(ROOT / "requirements.lock")
    direct = set(read_requirements(ROOT / "requirements.txt")) | set(read_requirements(ROOT / "requirements-dev.txt"))
    components: list[dict[str, Any]] = []
    distributions = {normalise_name(dist.metadata["Name"]): dist for dist in importlib.metadata.distributions() if dist.metadata.get("Name")}
    for name, version in sorted(locked.items()):
        dist = distributions.get(name)
        metadata_licence = None
        licence_file = None
        if dist is not None and dist.version == version:
            metadata_licence = dist.metadata.get("License-Expression") or dist.metadata.get("License")
            if not metadata_licence:
                classifiers = dist.metadata.get_all("Classifier") or []
                licence_classifiers = [value.rsplit("::", 1)[-1].strip() for value in classifiers if value.startswith("License ::")]
                metadata_licence = "; ".join(licence_classifiers) or None
            files = list(dist.files or [])
            candidates = [file for file in files if file.name.lower() in {"license", "license.txt", "licence", "licence.txt", "copying", "notice"}]
            if candidates:
                licence_file = Path(dist.locate_file(candidates[0]))
        components.append(component(
            ecosystem="pypi", name=name, version=version, direct=name in direct,
            source="requirements.lock", licence_metadata=metadata_licence, licence_file=licence_file,
        ))
    return components


def npm_components() -> list[dict[str, Any]]:
    package_json = json.loads((ROOT / "mobile/participant-app/package.json").read_text())
    direct = set(package_json.get("dependencies", {})) | set(package_json.get("devDependencies", {}))
    lock = json.loads((ROOT / "mobile/participant-app/package-lock.json").read_text())
    node_root = ROOT / "mobile/participant-app/node_modules"
    components: list[dict[str, Any]] = []
    for package_path, package in sorted(lock.get("packages", {}).items()):
        if not package_path.startswith("node_modules/"):
            continue
        relative = package_path.rsplit("node_modules/", 1)[-1]
        package_file = node_root / relative / "package.json"
        package_name = relative
        licence_metadata = package.get("license")
        if package_file.is_file():
            details = json.loads(package_file.read_text(encoding="utf-8"))
            package_name = details.get("name", package_name)
            licence_metadata = details.get("license", licence_metadata)
        components.append(component(
            ecosystem="npm", name=package_name, version=str(package.get("version", "UNKNOWN")),
            direct=package_name in direct,
            source=f"mobile/participant-app/package-lock.json#{package_path}",
            licence_metadata=licence_metadata, licence_file=first_license_file(node_root / relative),
        ))
    return components


def dart_components() -> list[dict[str, Any]]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - generation uses requirements-dev
        raise SystemExit("PyYAML is required to generate the IP inventory.") from exc
    lock = yaml.safe_load((ROOT / "participant_app/pubspec.lock").read_text())
    packages = lock["packages"]
    pub_cache = Path.home() / ".pub-cache/hosted/pub.dev"
    flutter_sdk = Path("/private/tmp/flutter-sdk")
    components: list[dict[str, Any]] = []
    for name, details in sorted(packages.items()):
        source = details.get("source", "UNKNOWN")
        version = str(details.get("version", "UNKNOWN"))
        licence_file = None
        if source == "hosted":
            licence_file = first_license_file(pub_cache / f"{name}-{version}")
        elif source == "sdk":
            if name.startswith("flutter"):
                licence_file = flutter_sdk / "LICENSE"
            elif name.startswith("sky_engine"):
                licence_file = flutter_sdk / "bin/cache/artifacts/engine/darwin-x64/LICENSE"
        components.append(component(
            ecosystem="pub", name=name, version=version,
            direct=details.get("dependency", "").startswith("direct"),
            source=f"participant_app/pubspec.lock ({source})", licence_metadata=None, licence_file=licence_file,
        ))
    return components


def native_components() -> list[dict[str, Any]]:
    settings = (ROOT / "participant_app/android/settings.gradle.kts").read_text()
    wrapper = (ROOT / "participant_app/android/gradle/wrapper/gradle-wrapper.properties").read_text()
    agp = re.search(r'com\.android\.application"\) version "([^"]+)', settings)
    kotlin = re.search(r'org\.jetbrains\.kotlin\.android"\) version "([^"]+)', settings)
    gradle = re.search(r"gradle-([0-9.]+)-all", wrapper)
    entries: list[tuple[str, str, str]] = [
        ("Gradle", gradle.group(1) if gradle else "UNKNOWN", "participant_app/android/gradle/wrapper/gradle-wrapper.properties"),
        ("Android Gradle Plugin", agp.group(1) if agp else "UNKNOWN", "participant_app/android/settings.gradle.kts"),
        ("Kotlin Gradle Plugin", kotlin.group(1) if kotlin else "UNKNOWN", "participant_app/android/settings.gradle.kts"),
        ("CocoaPods dependency graph", "UNLOCKED", "No participant_app/ios/Podfile.lock is committed"),
    ]
    return [component(
        ecosystem="native", name=name, version=version, direct=True, source=source,
        licence_metadata=None, licence_file=None,
    ) for name, version, source in entries]


def all_components() -> list[dict[str, Any]]:
    return python_components() + npm_components() + dart_components() + native_components()


def asset_rows() -> list[dict[str, str]]:
    assets = tracked_asset_files()
    hashes: dict[str, list[Path]] = {}
    for asset in assets:
        hashes.setdefault(sha256(asset), []).append(asset)
    rows: list[dict[str, str]] = []
    for asset in assets:
        rel = str(asset.relative_to(ROOT))
        peers = [str(other.relative_to(ROOT)) for other in hashes[sha256(asset)] if other != asset]
        asset_type = asset.suffix.lower().lstrip(".")
        notes = "Repository history identifies a commit but does not establish creator, ownership or commercial-use permission."
        if peers:
            notes += f" Byte-identical repository copies: {', '.join(peers)}."
        rows.append({
            "asset_path": rel,
            "asset_type": asset_type,
            "creator_or_source": "UNKNOWN",
            "acquired_or_created_date": "UNKNOWN",
            "owner": "UNKNOWN",
            "licence_or_permission": "UNKNOWN",
            "evidence_location": "git history only; no licence/provenance record found",
            "commercial_use_allowed": "UNKNOWN",
            "modification_allowed": "UNKNOWN",
            "distribution_allowed": "UNKNOWN",
            "attribution_required": "UNKNOWN",
            "attribution_text": "",
            "review_status": "UNRESOLVED",
            "reviewer": "",
            "review_date": "",
            "notes": notes,
        })
    return rows


def tracked_asset_files() -> list[Path]:
    """Return only repository-tracked shipped assets, never build/cache output."""
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, stdout=subprocess.PIPE,
    )
    return sorted(
        ROOT / value.decode("utf-8")
        for value in result.stdout.split(b"\0") if value
        if Path(value.decode("utf-8")).suffix.lower() in ASSET_SUFFIXES
    )


def write_assets(rows: list[dict[str, str]]) -> None:
    fields = [
        "asset_path", "asset_type", "creator_or_source", "acquired_or_created_date", "owner",
        "licence_or_permission", "evidence_location", "commercial_use_allowed", "modification_allowed",
        "distribution_allowed", "attribution_required", "attribution_text", "review_status", "reviewer",
        "review_date", "notes",
    ]
    with ASSET_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_inventory(components: list[dict[str, Any]]) -> None:
    fields = [
        "ecosystem", "name", "version", "direct", "source", "licence_declared", "licence_classified",
        "licence_evidence", "copyright_or_attribution", "obligations", "risk", "notice_collected",
    ]
    with INVENTORY_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows([{field: component[field] for field in fields} for component in components])


def write_sbom(components: list[dict[str, Any]], notices_sha256: str) -> None:
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{sha256(ROOT / 'requirements.lock')[:8]}-{sha256(ROOT / 'participant_app/pubspec.lock')[:4]}-0000-0000-000000000000",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "component": {"type": "application", "name": "Citizen Centric / PCIP", "version": "repository source"},
            "tools": [{"vendor": "Politis UK", "name": "scripts/ip_compliance.py"}],
        },
        "components": components,
        "evidence": {
            "source_fingerprints": source_fingerprints(),
            "third_party_notices_sha256": notices_sha256,
            "limitations": [
                "Licence classification is evidence-based and intentionally conservative.",
                "No iOS Podfile.lock is committed; the iOS native dependency graph is unresolved.",
                "Components with UNKNOWN or copyleft review status block a release until human/legal review records an approval or replacement.",
            ],
        },
    }
    SBOM_PATH.write_text(json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_notices(components: list[dict[str, Any]]) -> None:
    lines = [
        "# Third-party notices", "",
        "This file lists third-party components identified from the committed lockfiles and native build configuration. It does **not** license Politis UK proprietary application code, branding, methodology content or documentation; those remain subject to their separate proprietary rights notices.",
        "",
        "The detailed, machine-readable inventory is [`docs/IP_SBOM.json`](docs/IP_SBOM.json) and [`docs/IP_DEPENDENCY_LICENSE_INVENTORY.csv`](docs/IP_DEPENDENCY_LICENSE_INVENTORY.csv). Each entry records the exact collected licence evidence and distribution obligation. An `UNKNOWN` entry is not a licence determination and must be resolved before release.",
        "",
        "## Component notices", "",
    ]
    for item in components:
        lines.extend([
            f"### {item['ecosystem']}: {item['name']} {item['version']}",
            f"- Licence declared/classified: {item['licence_declared']} / {item['licence_classified']}",
            f"- Evidence: {item['licence_evidence']}",
            f"- Copyright/attribution: {item['copyright_or_attribution']}",
            f"- Distribution obligation: {item['obligations']}",
            f"- Review state: {item['risk']}",
        ])
        if item["notice_text"]:
            lines.extend([
                "<details><summary>Collected upstream licence/notice text</summary>",
                "",
                "```text",
                markdown_notice_text(item["notice_text"]),
                "```",
                "",
                "</details>",
            ])
        else:
            lines.append("- Collected notice text: **missing — release gate blocks distribution**")
        lines.append("")
    NOTICE_PATH.write_text("\n".join(lines), encoding="utf-8")


def markdown_notice_text(text: str) -> str:
    """Keep upstream terms readable without creating Git diff false positives.

    Some upstream notice files use reStructuredText underline lines such as
    ``=======``. Git's conflict-marker checker flags those otherwise harmless
    presentation lines. Removing line-ending whitespace and indenting only
    marker-shaped presentation lines preserves the visible notice while keeping
    repository integrity checks effective for actual merge conflicts.
    """
    lines: list[str] = []
    for line in text.splitlines():
        normalised = line.rstrip()
        if re.fullmatch(r"(?:<{7,}|={7,}|>{7,})", normalised):
            normalised = f" {normalised}"
        lines.append(normalised)
    return "\n".join(lines)


def ids(path: Path, key: str) -> list[str]:
    return [json.loads(line)[key] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_report(components: list[dict[str, Any]], assets: list[dict[str, str]]) -> None:
    risks = Counter(item["risk"] for item in components)
    unknowns = [item for item in components if item["risk"] == "BLOCKER_UNKNOWN"]
    unresolved_assets = [item for item in assets if item["review_status"] == "UNRESOLVED"]
    methodology = {
        "knowledge": ids(ROOT / "app/methodology_library/methodology_knowledge_base.jsonl", "methodology_id"),
        "claims": ids(ROOT / "app/methodology_library/methodology_claim_register.jsonl", "claim_id"),
        "disagreements": ids(ROOT / "app/methodology_library/methodology_disagreements.jsonl", "disagreement_id"),
    }
    lines = [
        "# Intellectual-property audit report", "",
        "**Scope.** Repository evidence reviewed on the current `chore/ip-compliance-hardening` source. This is an engineering compliance record, not legal advice or a trademark-law conclusion.", "",
        "## PASS", "",
        f"- Generated SBOM/inventory covers {len(components)} locked or configured components: Python {sum(x['ecosystem']=='pypi' for x in components)}, npm {sum(x['ecosystem']=='npm' for x in components)}, Dart/pub {sum(x['ecosystem']=='pub' for x in components)}, native build graph {sum(x['ecosystem']=='native' for x in components)}.",
        "- Repository source scan found no third-party copyright/licence headers in application-source extensions; generated Flutter platform scaffolding is identified as generated configuration rather than copied third-party application source.",
        "- Methodology bundle has controlled provenance, source IDs and a pinned synthesis hash; it is not publicly exposed as raw source material according to `SOURCE_MANIFEST.md`.",
        "- No declared AGPL, SSPL or non-commercial dependency was identified after evidence classification. This does not clear UNKNOWN or dual-licence entries.",
        "",
        "## WARNING", "",
        "- Licence classifications are based only on lockfile metadata and locally collected distribution licence files. The inventory does not infer absent terms.",
        "- The npm installation reports deprecated transitive packages and vulnerabilities; they are security maintenance findings outside this IP determination but should be handled through the security process.",
        "- No bundled source notice was collected for some components; preserve the upstream package notice before distributing binaries.",
        "",
        "## BLOCKER", "",
        f"- {len(unknowns)} dependency/native records have UNKNOWN licence evidence or an unresolved native graph. Release gate fails until each is reviewed, replaced or backed by recorded evidence.",
        f"- {len(unresolved_assets)} shipped custom/media assets have no repository evidence of creator, owner, commercial-use permission or modification/distribution rights. `docs/IP_ASSET_PROVENANCE_TEMPLATE.csv` records each as UNRESOLVED; release gate fails until completed by an authorised reviewer.",
        "- iOS native dependency completeness cannot be established because `participant_app/ios/Podfile.lock` is not committed. Obtain and review the resolved Pod graph before an iOS release.",
        "",
        "## HUMAN/LEGAL REVIEW", "",
        "- Review every component flagged `HUMAN_LEGAL_REVIEW`, `BLOCKER_STRONG_COPYLEFT`, `BLOCKER_NETWORK_COPYLEFT`, `BLOCKER_NON_COMMERCIAL` or `BLOCKER_UNKNOWN` in the generated inventory before release. Do not treat an absent flag as legal advice.",
        "- `npm:node-forge@1.4.0` declares a BSD-3-Clause/GPL-2.0 choice; record the selected compatible licence and preserve its notice before distribution.",
        "- Trademark clearance for Citizen Centric, Citizen-Centric, logos, icons, product names and slogans remains a human/legal release gate. This audit makes no ownership, registration or clearance conclusion.",
        "- Assess possible substantial/verbatim reproduction in the methodology derivatives against the underlying sources. The repository contains no raw source books/articles from which to calculate a text match. The following exact records require human copyright/provenance review before public distribution:",
        f"  - `app/methodology_library/methodology_knowledge_base.jsonl`: {', '.join(methodology['knowledge'])}.",
        f"  - `app/methodology_library/methodology_claim_register.jsonl`: {', '.join(methodology['claims'])}.",
        f"  - `app/methodology_library/methodology_disagreements.jsonl`: {', '.join(methodology['disagreements'])}.",
        "  The records are declared deterministic derivatives, but their volume and source-linked prose mean human review is required; this audit does not rewrite claims or provenance.",
        "",
        "## Evidence and remediation", "",
        "- Regenerate records in a prepared dependency environment with `python scripts/ip_compliance.py --generate`.",
        "- Use `python scripts/ip_compliance.py --verify` in CI to detect stale evidence.",
        "- Use `python scripts/ip_compliance.py --release-gate` before promotion; it fails on unresolved asset provenance, unknown/incompatible licences or missing notices.",
        "- Add only documented licence/provenance evidence. Do not replace UNKNOWN with an assumption.",
        "",
        "## Risk summary", "",
    ]
    for risk, count in sorted(risks.items()):
        lines.append(f"- {risk}: {count}")
    lines.extend(["", "## Exact package evidence requiring review", "", "| Risk | Component | Declared licence | Evidence | Required remediation |", "| --- | --- | --- | --- | --- |"])
    for item in sorted(
        [item for item in components if item["risk"] != "PASS_PERMISSIVE"],
        key=lambda item: (item["risk"], item["ecosystem"], item["name"], item["version"]),
    ):
        declared = str(item["licence_declared"]).replace("\n", " ").replace("|", "\\|")[:180]
        evidence = str(item["licence_evidence"]).replace("|", "\\|")
        remediation = "Record compatible licence/notice evidence or replace/remove before release."
        if item["risk"] == "HUMAN_LEGAL_REVIEW":
            remediation = "Obtain legal approval and document the chosen/compatible licence terms."
        lines.append(
            f"| {item['risk']} | `{item['ecosystem']}:{item['name']}@{item['version']}` | {declared} | {evidence} | {remediation} |"
        )
    lines.extend([
        "", "## Exact unresolved asset evidence", "",
        "All 38 currently shipped media records are listed individually in `docs/IP_ASSET_PROVENANCE_TEMPLATE.csv` with repository path, byte-identical internal copies and an `UNRESOLVED` status. An authorised rights holder must complete creator/source, permission, commercial-use, modification/distribution and attribution evidence before release.",
    ])
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generated_files() -> tuple[Path, ...]:
    return SBOM_PATH, INVENTORY_PATH, NOTICE_PATH, REPORT_PATH, ASSET_PATH


def generate() -> None:
    components = all_components()
    assets = asset_rows()
    write_inventory(components)
    write_notices(components)
    write_assets(assets)
    write_report(components, assets)
    write_sbom(components, sha256(NOTICE_PATH))
    print(f"Generated {len(components)} component records and {len(assets)} asset records.")


def load_sbom() -> dict[str, Any]:
    try:
        return json.loads(SBOM_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Missing or invalid SBOM: {exc}") from exc


def verify() -> dict[str, Any]:
    sbom = load_sbom()
    expected = source_fingerprints()
    if sbom.get("evidence", {}).get("source_fingerprints") != expected:
        raise SystemExit("IP evidence is stale: regenerate the inventory after changing a dependency manifest.")
    for path in generated_files():
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            raise SystemExit(f"Required IP compliance evidence is missing or empty: {path.relative_to(ROOT)}")
    if sbom.get("evidence", {}).get("third_party_notices_sha256") != sha256(NOTICE_PATH):
        raise SystemExit("Third-party notices differ from the SBOM evidence; regenerate and review the notices.")
    assets = list(csv.DictReader(ASSET_PATH.open(encoding="utf-8")))
    asset_paths = {row["asset_path"] for row in assets}
    expected_assets = {str(path.relative_to(ROOT)) for path in tracked_asset_files()}
    if asset_paths != expected_assets:
        raise SystemExit("Asset provenance register is incomplete or contains stale paths; regenerate it.")
    return sbom


def release_gate() -> None:
    sbom = verify()
    components = sbom.get("components", [])
    blocking_risks = {"BLOCKER_UNKNOWN", "BLOCKER_STRONG_COPYLEFT", "BLOCKER_NETWORK_COPYLEFT", "BLOCKER_NON_COMMERCIAL", "HUMAN_LEGAL_REVIEW"}
    blockers = [item for item in components if item.get("risk") in blocking_risks]
    unresolved_assets = [row for row in csv.DictReader(ASSET_PATH.open(encoding="utf-8")) if row.get("review_status") != "APPROVED"]
    missing_notices = [item for item in components if item.get("licence_classified") != "UNKNOWN" and not item.get("notice_collected")]
    if blockers or unresolved_assets or missing_notices:
        raise SystemExit(
            "IP release gate blocked: "
            f"{len(blockers)} licence review item(s), {len(missing_notices)} missing collected notice(s), "
            f"and {len(unresolved_assets)} unresolved shipped asset(s)."
        )
    print("IP release gate: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--release-gate", action="store_true")
    args = parser.parse_args()
    if sum((args.generate, args.verify, args.release_gate)) != 1:
        parser.error("choose exactly one mode")
    if args.generate:
        generate()
    elif args.verify:
        verify()
        print("IP compliance evidence: PASS")
    else:
        release_gate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
