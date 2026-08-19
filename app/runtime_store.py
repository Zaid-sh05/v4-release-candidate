from __future__ import annotations

from .config import settings
from .repository import repository
from .supabase_store import supabase_store


class RuntimeStore:
    """Persist conversations, evaluations and feedback.

    In `auto` mode Supabase is preferred when configured; SQLite remains a
    resilient local fallback so the pilot still works offline.
    """

    def _prefer_cloud(self) -> bool:
        mode = (settings.runtime_store or 'auto').lower().strip()
        return mode == 'supabase' or (mode == 'auto' and supabase_store.configured)

    @property
    def active_name(self) -> str:
        return 'supabase' if self._prefer_cloud() else 'sqlite'

    def _call(self, name: str, *args, **kwargs):
        if self._prefer_cloud():
            try:
                return getattr(supabase_store, name)(*args, **kwargs)
            except Exception:
                # Fail safely to local persistence. This also keeps local dev usable
                # before the Supabase runtime tables are created.
                pass
        return getattr(repository, name)(*args, **kwargs)

    def ensure_conversation(self, *a, **k): return self._call('ensure_conversation', *a, **k)
    def save_message(self, *a, **k): return self._call('save_message', *a, **k)
    def history(self, *a, **k): return self._call('history', *a, **k)
    def log_evaluation(self, *a, **k): return self._call('log_evaluation', *a, **k)
    def save_feedback(self, *a, **k): return self._call('save_feedback', *a, **k)
    def feedback_stats(self, *a, **k): return self._call('feedback_stats', *a, **k)


runtime_store = RuntimeStore()
