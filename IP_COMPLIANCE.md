# Intellectual Property and Release Compliance

This document defines mandatory IP controls for Citizen Centric releases. It is an engineering/compliance control, not a legal opinion.

## 1. Ownership and provenance

Do not commit third-party proprietary source code, books, reports, images, fonts, audio, video, datasets, trademarks, or other protected materials unless Politis UK has documented permission or a licence that permits the intended use.

For every non-trivial externally sourced asset, record: source/creator, acquisition date, applicable licence or written permission, permitted uses, attribution requirements, modification restrictions, and evidence location.

AI-assisted or generated assets must also have their generation/source provenance retained where practical. Do not represent an asset as exclusively human-created where that is inaccurate.

## 2. Methodology sources

Methodology sources are evidence inputs, not distributable product content. Public and participant routes must not expose raw copyrighted books, reports, source PDFs, or substantial copied passages unless separately authorised.

Published structured methodology derivatives must preserve the controlled source register, versioning, provenance and validation controls. A later approved methodology bundle must create a new version rather than silently rewriting a previously published version.

## 3. Open-source dependencies

Before every production release:

1. Generate an SBOM/dependency inventory covering Python, npm/Expo, Flutter/Dart and native/transitive dependencies.
2. Identify the licence for every component.
3. Flag unknown licences and strong-copyleft/network-copyleft licences for review before release.
4. Preserve required copyright notices, licence texts, attribution and source/modification obligations.
5. Confirm no dependency licence is being presented as the licence for Politis UK's proprietary application code.
6. Store the reviewed inventory with the release evidence.

## 4. Branding and trademarks

`Citizen Centric`, `Citizen-Centric`, associated logos, icons, product names and slogans must be treated as branding requiring clearance before public commercial launch.

Do not add ™ or ® claims unless authorised. In particular, never use ® unless the relevant mark is registered for the relevant jurisdiction/use.

Before public launch or a material rebrand, record a trademark clearance review covering exact and confusingly similar marks in relevant jurisdictions and classes. Any unresolved collision must be escalated before launch.

## 5. Images, icons, fonts and media

Only ship assets where provenance and commercial-use rights are documented. Confirm separately the right to modify, distribute in an app/web product, use in marketing, and sublicense/embed where relevant.

Do not assume that an asset being publicly downloadable means it is free for commercial use.

## 6. Release gate

A release must be blocked if any of the following remain unresolved:

- unknown ownership/provenance for a shipped custom asset;
- unreviewed dependency with an unknown or incompatible licence;
- required attribution/licence notice is missing;
- raw or excessive third-party copyrighted content is publicly exposed without authority;
- a material trademark conflict remains unresolved;
- a third-party licence is incorrectly presented as licensing Politis UK proprietary code.

## 7. Evidence

Retain the SBOM, dependency licence report, asset provenance register, methodology version/hash evidence, trademark review, third-party notices and approvals with each production release.
