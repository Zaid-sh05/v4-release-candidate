# Qanoni Pilot V3.2 QA Hotfix

## Fixed from live user QA

- Red-light penalty stays in Traffic and returns the verified traffic-points result.
- Sharia default-judgment appeal now prefers Article 112: 30 days, counted from service for a default judgment.
- A generic criminal/civil appeal question no longer mistakes a law year (e.g. 1961) for a filing deadline; it requests the court/judgment details needed to choose the correct rule.
- Short law-name queries such as `قانون العمل؟` return a clean law overview instead of scraped navigation text.
- Adultery, ordinary theft, and electronic extortion have targeted article-level pilot facts with explicit source-confidence metadata.
- Direct-answer priority remains: penalty / deadline / fee / procedure / judgment status first; sources support the answer rather than replace it.

## Source confidence

`canonical_verified`: cleaned rule derived from the official law text already stored in the corpus.

`official_guidance` / `official_service`: official Jordanian government guidance or service pages.

`verified_crosscheck`: the law itself is linked to an official Jordanian publication/list, while the article wording used by the pilot was cross-checked against a current legal reproduction because the official site did not expose a machine-readable consolidated article to the importer. The UI keeps this distinction in the authority label.

This is a pilot legal-information system, not a substitute for a lawyer or the competent court/authority.
