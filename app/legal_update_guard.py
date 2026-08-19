from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Iterable

from .repository import repository, now_iso
from .text import normalize_ar


@dataclass(frozen=True)
class UpdatePlan:
    action: str  # new | changed | unchanged | rejected
    fingerprint: str
    reason: str


_ALLOWED_DOMAINS = {
    'general', 'civil', 'criminal', 'personal_status', 'labor', 'commercial',
    'procedure', 'cyber', 'traffic', 'administrative', 'real_estate',
    'constitutional', 'tax_finance',
}

_GARBLED_MARKERS = ('�', '\x00', 'english search english', 'يرجى الانتظار')
_LEGAL_HINT_RE = re.compile(r'(قانون|نظام|تعليمات|المادة|مادة|تشريع|law|regulation|article)', re.I)


def _canonical_chunks(chunks: Iterable[tuple[str | None, str]]) -> str:
    parts = []
    for article, body in chunks:
        cleaned = ' '.join((body or '').replace('\x00', ' ').split())
        if not cleaned:
            continue
        parts.append(f'{article or ""}|{cleaned}')
    return '\n'.join(parts)


def document_fingerprint(*, title: str, authority: str, domain: str, source_url: str, chunks: list[tuple[str | None, str]]) -> str:
    payload = '\n'.join([
        normalize_ar(title),
        normalize_ar(authority),
        domain.strip().lower(),
        source_url.strip(),
        _canonical_chunks(chunks),
    ])
    return hashlib.sha256(payload.encode('utf-8', errors='ignore')).hexdigest()


def quality_gate(*, title: str, text: str, domain: str, chunks: list[tuple[str | None, str]], source_domains: list[str] | None = None) -> tuple[bool, str]:
    cleaned = ' '.join((text or '').replace('\x00', ' ').split())
    if domain not in _ALLOWED_DOMAINS:
        return False, 'unknown_domain'
    allowed = [d for d in (source_domains or []) if d in _ALLOWED_DOMAINS]
    if allowed and 'general' not in allowed and domain not in allowed:
        return False, 'domain_outside_source_scope'
    if len(cleaned) < 250:
        return False, 'text_too_short'
    if not chunks:
        return False, 'no_chunks'
    if any(marker in cleaned.lower() for marker in _GARBLED_MARKERS):
        return False, 'garbled_or_boilerplate_text'
    if not _LEGAL_HINT_RE.search(f'{title} {cleaned[:2500]}'):
        return False, 'no_legal_language_detected'

    # Statutory article splitting naturally produces many short chunks. Requiring a
    # single article to exceed an arbitrary length rejects valid laws with concise
    # provisions. Evaluate the extracted document as a whole while still requiring at
    # least one non-trivial chunk so menu/navigation fragments cannot pass on volume.
    chunk_lengths = [len(' '.join((body or '').replace('\x00', ' ').split())) for _, body in chunks]
    aggregate_chunk_text = sum(chunk_lengths)
    meaningful_chunks = sum(1 for length in chunk_lengths if length >= 45)
    if aggregate_chunk_text < 200 or meaningful_chunks == 0:
        return False, 'no_substantive_chunks'
    return True, 'accepted'


class LegalUpdateLedger:
    """SQLite audit ledger for official-source change detection.

    The updater never treats a fetched page as trusted merely because it came from an
    allowed host. A document must pass the quality gate, then its fingerprint is compared
    with the last promoted version. This makes weekly runs idempotent and auditable.
    """

    def ensure_tables(self) -> None:
        with repository.connect() as con:
            con.execute('''
                create table if not exists legal_sync_fingerprints (
                    source_url text primary key,
                    source_id text not null,
                    title text not null,
                    domain text not null,
                    fingerprint text not null,
                    promoted_at text not null
                )
            ''')
            con.execute('''
                create table if not exists legal_update_events (
                    id integer primary key autoincrement,
                    source_id text not null,
                    source_url text not null,
                    title text,
                    domain text,
                    action text not null,
                    fingerprint text,
                    reason text,
                    details_json text not null default '{}',
                    created_at text not null
                )
            ''')
            con.execute('create index if not exists legal_update_events_created_idx on legal_update_events(created_at desc)')
            con.execute('create index if not exists legal_update_events_source_idx on legal_update_events(source_id, created_at desc)')

    def plan(self, *, source_id: str, source_url: str, title: str, authority: str, domain: str, text: str, chunks: list[tuple[str | None, str]], source_domains: list[str] | None = None) -> UpdatePlan:
        self.ensure_tables()
        fingerprint = document_fingerprint(
            title=title,
            authority=authority,
            domain=domain,
            source_url=source_url,
            chunks=chunks,
        )
        accepted, reason = quality_gate(
            title=title,
            text=text,
            domain=domain,
            chunks=chunks,
            source_domains=source_domains,
        )
        if not accepted:
            return UpdatePlan('rejected', fingerprint, reason)
        with repository.connect() as con:
            row = con.execute(
                'select fingerprint from legal_sync_fingerprints where source_url=?',
                (source_url,),
            ).fetchone()
        if not row:
            return UpdatePlan('new', fingerprint, 'first_seen')
        if row['fingerprint'] == fingerprint:
            return UpdatePlan('unchanged', fingerprint, 'same_fingerprint')
        return UpdatePlan('changed', fingerprint, 'content_changed')

    def record(self, *, source_id: str, source_url: str, title: str, domain: str, plan: UpdatePlan, promoted: bool = False, details: dict | None = None) -> None:
        self.ensure_tables()
        now = now_iso()
        with repository.connect() as con:
            con.execute(
                '''insert into legal_update_events(source_id,source_url,title,domain,action,fingerprint,reason,details_json,created_at)
                   values(?,?,?,?,?,?,?,?,?)''',
                (source_id, source_url, title, domain, plan.action, plan.fingerprint, plan.reason, json.dumps(details or {}, ensure_ascii=False), now),
            )
            if promoted and plan.action in {'new', 'changed'}:
                con.execute(
                    '''insert into legal_sync_fingerprints(source_url,source_id,title,domain,fingerprint,promoted_at)
                       values(?,?,?,?,?,?)
                       on conflict(source_url) do update set
                         source_id=excluded.source_id,
                         title=excluded.title,
                         domain=excluded.domain,
                         fingerprint=excluded.fingerprint,
                         promoted_at=excluded.promoted_at''',
                    (source_url, source_id, title, domain, plan.fingerprint, now),
                )

    def recent_events(self, limit: int = 50) -> list[dict]:
        self.ensure_tables()
        with repository.connect() as con:
            rows = con.execute(
                '''select source_id,source_url,title,domain,action,fingerprint,reason,details_json,created_at
                   from legal_update_events order by id desc limit ?''',
                (min(max(int(limit), 1), 200),),
            ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            try:
                item['details'] = json.loads(item.pop('details_json') or '{}')
            except Exception:
                item['details'] = {}
                item.pop('details_json', None)
            out.append(item)
        return out


legal_update_ledger = LegalUpdateLedger()
