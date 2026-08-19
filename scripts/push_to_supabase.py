import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings
from app.repository import repository

if not settings.supabase_url or not settings.supabase_service_role_key:
    raise SystemExit(
        "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env first."
    )

from supabase import create_client


def clean_value(value):
    """Remove NUL characters that PostgreSQL text fields reject."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    return value


def clean_row(row):
    return {key: clean_value(value) for key, value in row.items()}


sb = create_client(
    settings.supabase_url,
    settings.supabase_service_role_key
)

con = repository.connect()

docs = con.execute(
    "select * from documents"
).fetchall()

chunks = con.execute(
    """
    select
        c.*,
        d.title_ar title,
        d.authority,
        d.domain,
        d.source_url,
        d.law_number,
        d.year,
        d.verified_at,
        d.source_kind
    from chunks c
    join documents d on d.id = c.document_id
    """
).fetchall()

print("Uploading documents:", len(docs))

for i in range(0, len(docs), 200):
    batch = []

    for r in docs[i:i + 200]:
        x = clean_row(dict(r))
        x.pop("content_hash", None)
        batch.append(x)

    sb.table("legal_documents").upsert(batch).execute()

print("Uploading chunks:", len(chunks))

for i in range(0, len(chunks), 150):
    batch = []

    for r in chunks[i:i + 150]:
        x = clean_row(dict(r))

        x.pop("body_normalized", None)
        x.pop("content_hash", None)
        x.pop("chunk_index", None)

        batch.append(x)

    sb.table("legal_chunks").upsert(batch).execute()

    print(
        min(i + 150, len(chunks)),
        "/",
        len(chunks)
    )

print("Supabase upload complete.")
print("OpenAI embeddings skipped for now.")