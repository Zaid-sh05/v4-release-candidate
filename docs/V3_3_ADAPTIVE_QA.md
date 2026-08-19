# Qanoni Pilot V3.3 — Adaptive QA Patch

## Why this patch exists
User QA exposed three important failure modes: generic homicide returned only a law reference, a WhatsApp blackmail “what should I do?” question returned a penalty instead of action steps, and dismissal-without-notice returned unrelated general labour rights.

## Fixes
- Intentional homicide: official PSD guidance tied to Penal Code Article 326 is now in the curated corpus; the answer states the supported 20-year penalty for intentional killing and warns that other homicide classifications may differ.
- Cyber blackmail action: official PSD cybercrime-unit contact details and anti-payment/reporting guidance were added.
- Labour dismissal triage: generic leave/overtime facts are suppressed for dismissal questions; the answer asks for contract type, service duration, stated reason and written notice and provides official labour-dispute contact channels.
- Retrieval expansion: homicide, cyber-reporting and labour-dispute vocabulary were added to query expansion.

## Safety rule
Qanoni still fails closed when a penalty, deadline, fee or entitlement is not supported by the retrieved official material.
