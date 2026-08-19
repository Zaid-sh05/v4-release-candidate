# Qanoni V4 — Cognition First

Qanoni V4 is a cognition-first Jordanian legal assistant.

The core rule is simple: **understand the case before searching the law**.

## V4 reasoning pipeline

1. Case Cognition — extract the user's goal, actors, facts, events, evidence, dates, amounts, intent indicators, and procedural posture.
2. Issue Spotting — generate competing legal hypotheses without prematurely declaring guilt, liability, or a final legal characterization.
3. Clarification — ask only questions whose answers can materially change the legal path.
4. Retrieval Planning — turn the case model into focused legal searches.
5. Verified Retrieval — use official Jordanian legal sources and current versions.
6. Cross-check — verify authority, effective date, amendments, and conflicting texts.
7. Grounded Answer — answer the user's actual goal and cite the supporting authority.
8. Self-review — verify that each legal conclusion is supported and that important alternatives were not ignored.
9. Feedback Learning — convert poor answers into reviewed failure cases and regression tests; user feedback never rewrites legal truth directly.

## Why V4 exists

V3.6 had strong retrieval and anti-hallucination protections, but complex fact patterns could still be reduced too early to keywords. V4 introduces a structured case representation before routing and retrieval.

## Development status

This repository is isolated from the live V3.6 pilot. The first milestone is the Case Cognition Engine and scenario test suite. No paid API is required for this milestone.