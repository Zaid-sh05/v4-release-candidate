# Core-law readiness

Qanoni distinguishes “the official law exists” from “the current article-level text is locally ready for exact answers.”

## Strong/usable pilot coverage

- Personal Status Law: substantial article-level corpus.
- Companies Law: substantial article-level corpus.
- Traffic Law: canonical article-level corpus.
- Traffic Points System 2024: article-level corpus.
- Sharia Procedure: substantial article-level corpus, including appeal-period material.
- Insolvency: useful article-level material including Article 114 penalty evidence.

## Partial / tracked gap

- Labor: many official documents plus curated Ministry guidance/services; some source PDFs have poor Arabic extraction.
- Cybercrime: official anchor/source coverage exists, but article extraction is not treated as complete where the PDF text layer is unreliable.
- Penal Code: official base-law reference and later amendments exist, but the complete current consolidated offence-by-offence base text is not locally ready.
- Civil Code: full local article-level base text is not ready.
- Criminal Procedure: official references/services exist, but the full current consolidated article-level code is not locally ready.
- Civil Procedure: official references/amendments/services exist, but the full current consolidated article-level code is not locally ready.

Run:

```text
python scripts/audit_pilot_readiness.py
```

for the exact shipped database counts and threshold report.
