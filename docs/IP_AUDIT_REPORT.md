# Intellectual-property audit report

**Scope.** Repository evidence reviewed on the current `chore/ip-compliance-hardening` source. This is an engineering compliance record, not legal advice or a trademark-law conclusion.

## PASS

- Generated SBOM/inventory covers 1241 locked or configured components: Python 79, npm 1051, Dart/pub 107, native build graph 4.
- Repository source scan found no third-party copyright/licence headers in application-source extensions; generated Flutter platform scaffolding is identified as generated configuration rather than copied third-party application source.
- Methodology bundle has controlled provenance, source IDs and a pinned synthesis hash; it is not publicly exposed as raw source material according to `SOURCE_MANIFEST.md`.
- No declared AGPL, SSPL or non-commercial dependency was identified after evidence classification. This does not clear UNKNOWN or dual-licence entries.

## WARNING

- Licence classifications are based only on lockfile metadata and locally collected distribution licence files. The inventory does not infer absent terms.
- The npm installation reports deprecated transitive packages and vulnerabilities; they are security maintenance findings outside this IP determination but should be handled through the security process.
- No bundled source notice was collected for some components; preserve the upstream package notice before distributing binaries.

## BLOCKER

- 8 dependency/native records have UNKNOWN licence evidence or an unresolved native graph. Release gate fails until each is reviewed, replaced or backed by recorded evidence.
- 38 shipped custom/media assets have no repository evidence of creator, owner, commercial-use permission or modification/distribution rights. `docs/IP_ASSET_PROVENANCE_TEMPLATE.csv` records each as UNRESOLVED; release gate fails until completed by an authorised reviewer.
- iOS native dependency completeness cannot be established because `participant_app/ios/Podfile.lock` is not committed. Obtain and review the resolved Pod graph before an iOS release.

## HUMAN/LEGAL REVIEW

- Review every component flagged `HUMAN_LEGAL_REVIEW`, `BLOCKER_STRONG_COPYLEFT`, `BLOCKER_NETWORK_COPYLEFT`, `BLOCKER_NON_COMMERCIAL` or `BLOCKER_UNKNOWN` in the generated inventory before release. Do not treat an absent flag as legal advice.
- `npm:node-forge@1.4.0` declares a BSD-3-Clause/GPL-2.0 choice; record the selected compatible licence and preserve its notice before distribution.
- Trademark clearance for Citizen Centric, Citizen-Centric, logos, icons, product names and slogans remains a human/legal release gate. This audit makes no ownership, registration or clearance conclusion.
- Assess possible substantial/verbatim reproduction in the methodology derivatives against the underlying sources. The repository contains no raw source books/articles from which to calculate a text match. The following exact records require human copyright/provenance review before public distribution:
  - `app/methodology_library/methodology_knowledge_base.jsonl`: M01, M02, M03, M04, M05, M06, M07, M08, M09, M10, M11, M12, M13, M14, M15, M16, M17, M18, M19, M20, M21, M22, M23, M24, M25, M26, M27.
  - `app/methodology_library/methodology_claim_register.jsonl`: CL01, CL02, CL03, CL04, CL05, CL06, CL07, CL08, CL09, CL10, CL11, CL12, CL13, CL14, CL15, CL16, CL17, CL18, CL19, CL20, CL21, CL22, CL23, CL24, CL25, CL26, CL27, CL28, CL29, CL30, CL31, CL32, CL33, CL34, CL35, CL36, CL37.
  - `app/methodology_library/methodology_disagreements.jsonl`: D01, D02, D03, D04, D05, D06, D07, D08, D09, D10, D11, D12, D13, D14, D15, D16, D17, D18.
  The records are declared deterministic derivatives, but their volume and source-linked prose mean human review is required; this audit does not rewrite claims or provenance.

## Evidence and remediation

- Regenerate records in a prepared dependency environment with `python scripts/ip_compliance.py --generate`.
- Use `python scripts/ip_compliance.py --verify` in CI to detect stale evidence.
- Use `python scripts/ip_compliance.py --release-gate` before promotion; it fails on unresolved asset provenance, unknown/incompatible licences or missing notices.
- Add only documented licence/provenance evidence. Do not replace UNKNOWN with an assumption.

## Risk summary

- BLOCKER_UNKNOWN: 8
- HUMAN_LEGAL_REVIEW: 37
- PASS_PERMISSIVE: 1196

## Exact package evidence requiring review

| Risk | Component | Declared licence | Evidence | Required remediation |
| --- | --- | --- | --- | --- |
| BLOCKER_UNKNOWN | `native:Android Gradle Plugin@9.1.0` | UNKNOWN | metadata only | Record compatible licence/notice evidence or replace/remove before release. |
| BLOCKER_UNKNOWN | `native:CocoaPods dependency graph@UNLOCKED` | UNKNOWN | metadata only | Record compatible licence/notice evidence or replace/remove before release. |
| BLOCKER_UNKNOWN | `native:Gradle@9.3.1` | UNKNOWN | metadata only | Record compatible licence/notice evidence or replace/remove before release. |
| BLOCKER_UNKNOWN | `native:Kotlin Gradle Plugin@2.4.0` | UNKNOWN | metadata only | Record compatible licence/notice evidence or replace/remove before release. |
| BLOCKER_UNKNOWN | `npm:exit@0.1.2` | UNKNOWN | metadata only | Record compatible licence/notice evidence or replace/remove before release. |
| BLOCKER_UNKNOWN | `pub:sky_engine@0.0.0` | UNKNOWN | metadata only | Record compatible licence/notice evidence or replace/remove before release. |
| BLOCKER_UNKNOWN | `pub:uuid@4.6.0` | UNKNOWN | locally collected upstream distribution notice: LICENSE | Record compatible licence/notice evidence or replace/remove before release. |
| BLOCKER_UNKNOWN | `pub:yaml@3.1.3` | UNKNOWN | locally collected upstream distribution notice: LICENSE | Record compatible licence/notice evidence or replace/remove before release. |
| HUMAN_LEGAL_REVIEW | `npm:caniuse-lite@1.0.30001806` | CC-BY-4.0 | mobile/participant-app/node_modules/caniuse-lite/LICENSE | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:glob@13.0.6` | BlueOak-1.0.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:glob@7.2.3` | BlueOak-1.0.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:glob@7.2.3` | BlueOak-1.0.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:glob@7.2.3` | BlueOak-1.0.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:glob@7.2.3` | BlueOak-1.0.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:lightningcss@1.33.0` | MPL-2.0 | mobile/participant-app/node_modules/lightningcss/LICENSE | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:lightningcss-android-arm64@1.33.0` | MPL-2.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:lightningcss-darwin-arm64@1.33.0` | MPL-2.0 | mobile/participant-app/node_modules/lightningcss-darwin-arm64/LICENSE | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:lightningcss-darwin-x64@1.33.0` | MPL-2.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:lightningcss-freebsd-x64@1.33.0` | MPL-2.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:lightningcss-linux-arm-gnueabihf@1.33.0` | MPL-2.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:lightningcss-linux-arm64-gnu@1.33.0` | MPL-2.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:lightningcss-linux-arm64-musl@1.33.0` | MPL-2.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:lightningcss-linux-x64-gnu@1.33.0` | MPL-2.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:lightningcss-linux-x64-musl@1.33.0` | MPL-2.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:lightningcss-win32-arm64-msvc@1.33.0` | MPL-2.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:lightningcss-win32-x64-msvc@1.33.0` | MPL-2.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:minimatch@10.2.6` | BlueOak-1.0.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:minimatch@3.1.5` | BlueOak-1.0.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:minimatch@3.1.5` | BlueOak-1.0.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:minimatch@3.1.5` | BlueOak-1.0.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:minimatch@3.1.5` | BlueOak-1.0.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:minimatch@3.1.5` | BlueOak-1.0.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:minimatch@3.1.5` | BlueOak-1.0.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:minimatch@3.1.5` | BlueOak-1.0.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:minimatch@3.1.5` | BlueOak-1.0.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:minimatch@3.1.5` | BlueOak-1.0.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:minimatch@5.1.9` | BlueOak-1.0.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:minipass@7.1.3` | BlueOak-1.0.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:node-forge@1.4.0` | (BSD-3-Clause OR GPL-2.0) | mobile/participant-app/node_modules/node-forge/LICENSE | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:path-scurry@2.0.2` | BlueOak-1.0.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:sax@1.6.1` | BlueOak-1.0.0 | metadata only | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `pub:dbus@0.7.14` | UNKNOWN | locally collected upstream distribution notice: LICENSE | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `pypi:certifi@2026.7.22` | MPL-2.0 | locally collected upstream distribution notice: LICENSE | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `pypi:psycopg@3.2.3` | GNU Lesser General Public License v3 (LGPLv3) | locally collected upstream distribution notice: LICENSE.txt | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `pypi:psycopg-binary@3.2.3` | GNU Lesser General Public License v3 (LGPLv3) | locally collected upstream distribution notice: LICENSE.txt | Obtain legal approval and document the chosen/compatible licence terms. |

## Exact unresolved asset evidence

All 38 currently shipped media records are listed individually in `docs/IP_ASSET_PROVENANCE_TEMPLATE.csv` with repository path, byte-identical internal copies and an `UNRESOLVED` status. An authorised rights holder must complete creator/source, permission, commercial-use, modification/distribution and attribution evidence before release.
