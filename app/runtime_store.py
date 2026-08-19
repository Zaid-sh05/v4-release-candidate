from __future__ import annotations

from .config import settings
from .feedback_review_store import feedback_review_store
from .repository import repository
from .supabase_store import supabase_store


class RuntimeStore:
    """Persist conversations, evaluations, feedback and grounded review memory."""

    def _prefer_cloud(self) -> bool:
        mode=(settings.runtime_store or 'auto').lower().strip()
        return mode=='supabase' or (mode=='auto' and supabase_store.configured)

    @property
    def active_name(self) -> str:
        return 'supabase' if self._prefer_cloud() else 'sqlite'

    def _call(self,name:str,*args,**kwargs):
        if self._prefer_cloud():
            try:
                return getattr(supabase_store,name)(*args,**kwargs)
            except Exception:
                pass
        return getattr(repository,name)(*args,**kwargs)

    def ensure_conversation(self,*a,**k): return self._call('ensure_conversation',*a,**k)
    def save_message(self,*a,**k): return self._call('save_message',*a,**k)
    def history(self,*a,**k): return self._call('history',*a,**k)
    def log_evaluation(self,*a,**k): return self._call('log_evaluation',*a,**k)
    def save_feedback(self,*a,**k): return self._call('save_feedback',*a,**k)
    def feedback_stats(self,*a,**k): return self._call('feedback_stats',*a,**k)

    def save_feedback_review(self,**kwargs):
        if self._prefer_cloud():
            try: return supabase_store.save_feedback_review(**kwargs)
            except Exception: pass
        return feedback_review_store.save_review(**kwargs)

    def feedback_review_hint(self,question:str,primary_domain:str):
        if self._prefer_cloud():
            try: return supabase_store.feedback_review_hint(question,primary_domain)
            except Exception: pass
        return feedback_review_store.hint(question,primary_domain)

    def list_feedback_reviews(self,limit:int=50):
        if self._prefer_cloud():
            try: return supabase_store.list_feedback_reviews(limit)
            except Exception: pass
        return feedback_review_store.list_reviews(limit)

    def feedback_review_stats(self):
        if self._prefer_cloud():
            try: return supabase_store.feedback_review_stats()
            except Exception: pass
        return feedback_review_store.stats()


runtime_store=RuntimeStore()
