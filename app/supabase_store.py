from __future__ import annotations

import uuid
from datetime import datetime, timezone
from .config import settings


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

    # Runtime telemetry / conversation persistence. All methods are best-effort;
    # RuntimeStore falls back to SQLite if any cloud call fails.
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
