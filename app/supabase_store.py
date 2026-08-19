from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from .config import settings
from .text import normalize_ar


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SupabaseStore:
    """Server-side Supabase access.

    The service-role key is never exposed to the browser. When Supabase is not
    configured, callers can safely fall back to the bundled SQLite database.
    """

    def __init__(self):
        self.client = None
        self.last_error = ''
        if settings.supabase_url and settings.supabase_service_role_key:
            try:
                from supabase import create_client
                self.client = create_client(settings.supabase_url, settings.supabase_service_role_key)
            except Exception as exc:
                self.last_error = f'{type(exc).__name__}: {exc}'[:240]
                self.client = None

    @property
    def configured(self) -> bool:
        return self.client is not None

    def health(self):
        if not self.client:
            return {'status': 'not_configured', 'reachable': False, 'error': self.last_error or None}
        try:
            rows = self.client.table('legal_chunks').select('id').limit(1).execute().data or []
            return {'status': 'configured', 'reachable': True, 'sample_rows': len(rows)}
        except Exception as exc:
            return {'status': 'configured', 'reachable': False, 'error': f'{type(exc).__name__}: {exc}'[:240]}

    def hybrid_search(self, query: str, query_embedding: list[float], domains: list[str], limit: int = 8):
        if not self.client:
            return []
        try:
            result = self.client.rpc('hybrid_search_legal_chunks', {
                'query_text': query,
                'query_embedding': query_embedding,
                'filter_domains': domains,
                'match_count': limit,
            }).execute()
            return result.data or []
        except Exception as exc:
            self.last_error = f'{type(exc).__name__}: {exc}'[:240]
            return []

    def keyword_search(self, query: str, domains: list[str], limit: int = 8):
        """Search the cloud corpus without paid embeddings."""
        if not self.client:
            return []
        try:
            result = self.client.rpc('keyword_search_legal_chunks', {
                'query_text': query,
                'filter_domains': domains,
                'match_count': min(max(int(limit), 1), 30),
            }).execute()
            return result.data or []
        except Exception as exc:
            self.last_error = f'{type(exc).__name__}: {exc}'[:240]
            return []

    def replace_legal_document_chunks(
        self,
        *,
        title: str,
        authority: str,
        domain: str,
        source_url: str,
        chunks: list[tuple[str | None, str]],
        source_kind: str = 'official_sync',
        verified_at: str | None = None,
    ) -> int:
        """Promote one accepted official document into the persistent cloud corpus.

        New content is written first. Only after the current version is searchable do we
        remove stale chunks and older document IDs tied to the exact same official URL.
        This avoids serving two versions of an amended law while protecting against a
        transient write failure erasing the previous version first.
        """
        if not self.client:
            raise RuntimeError('Supabase is not configured')
        stamp = verified_at or now_iso()
        doc_id = hashlib.sha1(f'{source_url}|{title}|{domain}'.encode()).hexdigest()

        prior_documents = (
            self.client.table('legal_documents')
            .select('id')
            .eq('source_url', source_url)
            .execute().data or []
        )
        document = {
            'id': doc_id,
            'title_ar': title,
            'authority': authority,
            'domain': domain,
            'source_url': source_url,
            'source_kind': source_kind,
            'verified_at': stamp,
        }
        self.client.table('legal_documents').upsert(document).execute()

        rows = []
        current_ids = set()
        for article, body in chunks:
            body = (body or '').strip()
            if len(body) < 40:
                continue
            content_hash = hashlib.sha256(normalize_ar(body).encode()).hexdigest()
            chunk_id = hashlib.sha1(f'{doc_id}|{article or ""}|{content_hash}'.encode()).hexdigest()
            current_ids.add(chunk_id)
            rows.append({
                'id': chunk_id,
                'document_id': doc_id,
                'title': title,
                'authority': authority,
                'domain': domain,
                'source_url': source_url,
                'article': article,
                'body': body,
                'verified_at': stamp,
                'source_kind': source_kind,
            })
        if not rows:
            raise ValueError('Accepted legal document produced no promotable chunks')

        for start in range(0, len(rows), 150):
            self.client.table('legal_chunks').upsert(rows[start:start + 150]).execute()

        existing = self.client.table('legal_chunks').select('id').eq('document_id', doc_id).execute().data or []
        stale_chunks = [row.get('id') for row in existing if row.get('id') and row.get('id') not in current_ids]
        for start in range(0, len(stale_chunks), 150):
            batch = stale_chunks[start:start + 150]
            if batch:
                self.client.table('legal_chunks').delete().in_('id', batch).execute()

        stale_documents = [row.get('id') for row in prior_documents if row.get('id') and row.get('id') != doc_id]
        for start in range(0, len(stale_documents), 100):
            batch = stale_documents[start:start + 100]
            if batch:
                # legal_chunks cascades on document deletion.
                self.client.table('legal_documents').delete().in_('id', batch).execute()
        return len(rows)

    def get_legal_sync_fingerprint(self, source_url: str) -> str | None:
        if not self.client:
            return None
        rows = (
            self.client.table('qanoni_legal_sync_fingerprints')
            .select('fingerprint')
            .eq('source_url', source_url)
            .limit(1)
            .execute().data or []
        )
        return rows[0].get('fingerprint') if rows else None

    def upsert_legal_sync_fingerprint(self, *, source_url: str, source_id: str, title: str, domain: str, fingerprint: str, promoted_at: str) -> None:
        if not self.client:
            return
        self.client.table('qanoni_legal_sync_fingerprints').upsert({
            'source_url': source_url,
            'source_id': source_id,
            'title': title,
            'domain': domain,
            'fingerprint': fingerprint,
            'promoted_at': promoted_at,
        }).execute()

    def log_legal_update_event(self, *, source_id: str, source_url: str, title: str, domain: str, action: str, fingerprint: str, reason: str, details: dict, created_at: str) -> None:
        if not self.client:
            return
        self.client.table('qanoni_legal_update_events').insert({
            'id': str(uuid.uuid4()),
            'source_id': source_id,
            'source_url': source_url,
            'title': title,
            'domain': domain,
            'action': action,
            'fingerprint': fingerprint,
            'reason': reason,
            'details': details or {},
            'created_at': created_at,
        }).execute()

    def ensure_conversation(self, conversation_id: str | None, language: str) -> str:
        if not self.client:
            raise RuntimeError('Supabase is not configured')
        cid = conversation_id or str(uuid.uuid4())
        now = now_iso()
        existing = self.client.table('qanoni_conversations').select('id').eq('id', cid).limit(1).execute().data or []
        if existing:
            self.client.table('qanoni_conversations').update({'language': language, 'updated_at': now}).eq('id', cid).execute()
        else:
            self.client.table('qanoni_conversations').insert({'id': cid, 'language': language, 'created_at': now, 'updated_at': now}).execute()
        return cid

    def save_message(self, cid: str, role: str, content: str, domain: str | None = None, intent: str | None = None):
        if not self.client:
            raise RuntimeError('Supabase is not configured')
        now = now_iso()
        self.client.table('qanoni_messages').insert({
            'id': str(uuid.uuid4()), 'conversation_id': cid, 'role': role, 'content': content,
            'primary_domain': domain, 'intent': intent, 'created_at': now,
        }).execute()
        self.client.table('qanoni_conversations').update({'updated_at': now}).eq('id', cid).execute()

    def history(self, cid: str, limit: int = 8) -> list[dict]:
        if not self.client:
            raise RuntimeError('Supabase is not configured')
        rows = self.client.table('qanoni_messages').select('role,content,created_at').eq('conversation_id', cid).order('created_at', desc=True).limit(limit).execute().data or []
        return [{'role': r['role'], 'content': r['content']} for r in reversed(rows)]

    def log_evaluation(self, cid: str, message: str, intent: str, primary_domain: str, passed: bool, score: float, reasons: list[str], mode: str):
        if not self.client:
            raise RuntimeError('Supabase is not configured')
        self.client.table('qanoni_answer_evaluations').insert({
            'id': str(uuid.uuid4()), 'conversation_id': cid, 'message': message,
            'intent': intent, 'primary_domain': primary_domain, 'passed': bool(passed),
            'score': float(score), 'reasons': reasons, 'mode': mode, 'created_at': now_iso(),
        }).execute()

    def save_feedback(self, cid: str | None, rating: str, note: str | None = None) -> dict:
        if not self.client:
            raise RuntimeError('Supabase is not configured')
        if rating not in {'helpful', 'not_helpful'}:
            raise ValueError('rating must be helpful or not_helpful')
        fid = str(uuid.uuid4())
        self.client.table('qanoni_feedback').insert({
            'id': fid, 'conversation_id': cid, 'rating': rating,
            'note': (note or '')[:1200], 'created_at': now_iso(),
        }).execute()
        return {'id': fid, 'saved': True, 'rating': rating, 'store': 'supabase'}

    def feedback_stats(self) -> dict:
        if not self.client:
            raise RuntimeError('Supabase is not configured')
        rows = self.client.table('qanoni_feedback').select('rating').execute().data or []
        out = {'helpful': 0, 'not_helpful': 0}
        for r in rows:
            rating = r.get('rating')
            if rating in out:
                out[rating] += 1
        return out


supabase_store = SupabaseStore()
