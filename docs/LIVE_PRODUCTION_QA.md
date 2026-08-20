# Qanoni V4 Live Production QA

`python scripts/live_production_qa.py` validates the deployed Railway service rather than only the in-process FastAPI app.

The gate checks:

- V4 health, Supabase persistence, Groq cognition, and the effective cloud corpus.
- Arabic/English conversation routing and representative legal-domain routes.
- Cross-domain source isolation and the divorce/labor regression.
- Retrieval of a document promoted by the weekly official-source updater.
- Negative-feedback persistence and creation of a grounded correction review.
- Cleanup of QA conversations/feedback from Supabase after the run.

The GitHub Actions workflow `Qanoni Live Production QA` runs this harness against the production Railway URL and uses repository Supabase secrets only for verification and cleanup. No secret is sent to the public application.
