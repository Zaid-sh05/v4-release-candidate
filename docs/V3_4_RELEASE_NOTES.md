# Qanoni Pilot V3.4 release notes

Release: `3.4.0-pilot`

## Shipped changes

- Self-evaluation before legal answers are returned.
- Intent-specific adaptive retrieval when the first answer is incomplete.
- Runtime QA log for evaluator pass/fail/reasons.
- Helpful / Not helpful feedback capture in the chat UI.
- Labor dismissal depth using official Ministry of Labour guidance and a published Judicial Council principle.
- Article 31 is no longer shown as a generic dismissal rule; it is reserved for facts suggesting its special termination/suspension path.
- Existing V3.3 homicide, cyber-reporting, traffic, Sharia appeal, fees, complaint, zina, theft and no-emoji fixes preserved.

## Shipped corpus snapshot

- 3,472 searchable chunks
- 187 documents
- 19 registered official-source entries
- 13 legal domains

## Verification performed before packaging

- `doctor.py` — PASS
- router tests — PASS
- repository tests — PASS
- API smoke tests — PASS
- UI invariant tests — PASS
- no-emoji tests — PASS
- pilot acceptance tests — PASS
- V3.4 adaptive/self-evaluation tests — PASS
- Python compileall — PASS
- JavaScript syntax check — PASS
- SQLite integrity check — PASS

Runtime test conversations, feedback, and evaluator telemetry were cleared before creating the release ZIP.
