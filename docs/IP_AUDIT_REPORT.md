# Intellectual-property audit report

**Scope.** Repository evidence reviewed on the current `chore/ip-compliance-hardening` source. This is an engineering compliance record, not legal advice or a trademark-law conclusion.

## PASS

- Generated SBOM/inventory covers 1240 locked or configured components: Python 79, npm 1051, Dart/pub 107, native build graph 3.
- Repository source scan found no third-party copyright/licence headers in application-source extensions; generated Flutter platform scaffolding is identified as generated configuration rather than copied third-party application source.
- Methodology bundle has controlled provenance, source IDs and a pinned synthesis hash; it is not publicly exposed as raw source material according to `SOURCE_MANIFEST.md`.
- No declared AGPL, SSPL or non-commercial dependency was identified after evidence classification. This does not clear UNKNOWN or dual-licence entries.

## WARNING

- Licence classifications are based only on lockfile metadata and locally collected distribution licence files. The inventory does not infer absent terms.
- The npm installation reports deprecated transitive packages and vulnerabilities; they are security maintenance findings outside this IP determination but should be handled through the security process.
- No bundled source notice was collected for some components; preserve the upstream package notice before distributing binaries.

## BLOCKER

- 1 dependency/native records have UNKNOWN licence evidence or an unresolved native graph. Release gate fails until each is reviewed, replaced or backed by recorded evidence.
- 38 shipped custom/media assets have no repository evidence of creator, owner, commercial-use permission or modification/distribution rights. 27 have a repository/platform-evidenced variant relationship, but the original source remains unresolved. `docs/IP_ASSET_PROVENANCE_TEMPLATE.csv` keeps all of them release-blocking until completed by an authorised reviewer.
- The iOS Flutter project uses generated Swift Package Manager plugin integration rather than CocoaPods; no Podfile or Podfile.lock is expected. The pinned pub lock and iOS project configuration are the authoritative graph evidence.

## HUMAN/LEGAL REVIEW

- Review every component flagged `HUMAN_LEGAL_REVIEW`, `BLOCKER_STRONG_COPYLEFT`, `BLOCKER_NETWORK_COPYLEFT`, `BLOCKER_NON_COMMERCIAL` or `BLOCKER_UNKNOWN` in the generated inventory before release. Do not treat an absent flag as legal advice.
- `npm:node-forge@1.4.0` declares a BSD-3-Clause/GPL-2.0 choice; record the selected compatible licence and preserve its notice before distribution.
- Owner-supplied trademark evidence is recorded in `docs/IP_TRADEMARK_EVIDENCE.md`: UK00003775365; owner supplied as Politis Ltd; associated mark supplied as the Politis figurative/logo mark. It is not independent confirmation of registration/status, nor evidence of copyright/licence for a particular repository asset.
- Trademark clearance for Citizen Centric, Citizen-Centric, logos, icons, product names and slogans remains a human/legal release gate. This audit makes no ownership, registration or clearance conclusion.
- Repository-only methodology triage reviewed 82 controlled derivative records and identified 54 long narrative fields for source-side comparison. See `docs/IP_METHODOLOGY_COPYRIGHT_REVIEW.md`. It makes no infringement conclusion and does not rewrite claims or provenance.

## Evidence and remediation

- Regenerate records in a prepared dependency environment with `python scripts/ip_compliance.py --generate`.
- Use `python scripts/ip_compliance.py --verify` in CI to detect stale evidence.
- Use `python scripts/ip_compliance.py --release-gate` before promotion; it fails on unresolved asset provenance, unknown/incompatible licences or missing notices.
- Add only documented licence/provenance evidence. Do not replace UNKNOWN with an assumption.

## Risk summary

- BLOCKER_UNKNOWN: 1
- HUMAN_LEGAL_REVIEW: 25
- PASS_PERMISSIVE: 1214

## Exact package evidence requiring review

| Risk | Component | Declared licence | Evidence | Required remediation |
| --- | --- | --- | --- | --- |
| BLOCKER_UNKNOWN | `native:Android Gradle Plugin@9.1.0` | UNKNOWN | metadata only | Record compatible licence/notice evidence or replace/remove before release. |
| HUMAN_LEGAL_REVIEW | `npm:caniuse-lite@1.0.30001806` | CC-BY-4.0 | mobile/participant-app/node_modules/caniuse-lite/LICENSE | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:glob@13.0.6` | BlueOak-1.0.0 | mobile/participant-app/node_modules/glob/LICENSE.md | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:lightningcss@1.33.0` | MPL-2.0 | mobile/participant-app/node_modules/lightningcss/LICENSE | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:lightningcss-android-arm64@1.33.0` | MPL-2.0 | integrity-checked npm package tarball: lightningcss-android-arm64-1.33.0.tgz/package/LICENSE | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:lightningcss-darwin-arm64@1.33.0` | MPL-2.0 | mobile/participant-app/node_modules/lightningcss-darwin-arm64/LICENSE | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:lightningcss-darwin-x64@1.33.0` | MPL-2.0 | integrity-checked npm package tarball: lightningcss-darwin-x64-1.33.0.tgz/package/LICENSE | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:lightningcss-freebsd-x64@1.33.0` | MPL-2.0 | integrity-checked npm package tarball: lightningcss-freebsd-x64-1.33.0.tgz/package/LICENSE | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:lightningcss-linux-arm-gnueabihf@1.33.0` | MPL-2.0 | integrity-checked npm package tarball: lightningcss-linux-arm-gnueabihf-1.33.0.tgz/package/LICENSE | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:lightningcss-linux-arm64-gnu@1.33.0` | MPL-2.0 | integrity-checked npm package tarball: lightningcss-linux-arm64-gnu-1.33.0.tgz/package/LICENSE | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:lightningcss-linux-arm64-musl@1.33.0` | MPL-2.0 | integrity-checked npm package tarball: lightningcss-linux-arm64-musl-1.33.0.tgz/package/LICENSE | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:lightningcss-linux-x64-gnu@1.33.0` | MPL-2.0 | integrity-checked npm package tarball: lightningcss-linux-x64-gnu-1.33.0.tgz/package/LICENSE | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:lightningcss-linux-x64-musl@1.33.0` | MPL-2.0 | integrity-checked npm package tarball: lightningcss-linux-x64-musl-1.33.0.tgz/package/LICENSE | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:lightningcss-win32-arm64-msvc@1.33.0` | MPL-2.0 | integrity-checked npm package tarball: lightningcss-win32-arm64-msvc-1.33.0.tgz/package/LICENSE | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:lightningcss-win32-x64-msvc@1.33.0` | MPL-2.0 | integrity-checked npm package tarball: lightningcss-win32-x64-msvc-1.33.0.tgz/package/LICENSE | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:lru-cache@11.5.2` | BlueOak-1.0.0 | mobile/participant-app/node_modules/path-scurry/node_modules/lru-cache/LICENSE.md | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:minimatch@10.2.6` | BlueOak-1.0.0 | mobile/participant-app/node_modules/minimatch/LICENSE.md | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:minipass@7.1.3` | BlueOak-1.0.0 | mobile/participant-app/node_modules/minipass/LICENSE.md | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:node-forge@1.4.0` | (BSD-3-Clause OR GPL-2.0) | mobile/participant-app/node_modules/node-forge/LICENSE | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:path-scurry@2.0.2` | BlueOak-1.0.0 | mobile/participant-app/node_modules/path-scurry/LICENSE.md | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `npm:sax@1.6.1` | BlueOak-1.0.0 | mobile/participant-app/node_modules/sax/LICENSE.md | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `pub:dbus@0.7.14` | UNKNOWN | locally collected upstream distribution notice: LICENSE | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `pub:sky_engine@0.0.0` | Multiple bundled third-party notices | locally collected upstream distribution notice: LICENSE | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `pypi:certifi@2026.7.22` | MPL-2.0 | locally collected upstream distribution notice: LICENSE | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `pypi:psycopg@3.2.3` | GNU Lesser General Public License v3 (LGPLv3) | locally collected upstream distribution notice: LICENSE.txt | Obtain legal approval and document the chosen/compatible licence terms. |
| HUMAN_LEGAL_REVIEW | `pypi:psycopg-binary@3.2.3` | GNU Lesser General Public License v3 (LGPLv3) | locally collected upstream distribution notice: LICENSE.txt | Obtain legal approval and document the chosen/compatible licence terms. |

## Exact unresolved asset evidence

All 38 currently shipped media records are listed individually in `docs/IP_ASSET_PROVENANCE_TEMPLATE.csv`. Platform/byte-identical derivative relationships are recorded separately from original ownership; every asset remains release-blocking until an authorised rights holder completes creator/source, permission, commercial-use, modification/distribution and attribution evidence.
