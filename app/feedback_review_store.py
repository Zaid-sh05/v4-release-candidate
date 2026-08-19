from __future__ import annotations

import hashlib
import json
import uuid

from .repository import now_iso, repository
from .text import normalize_ar


def question_fingerprint(question: str) -> str:
    normalized=' '.join(normalize_ar(question or '').split())
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


class FeedbackReviewStore:
    """SQLite fallback for grounded negative-feedback reviews.

    Reviews store official-source hints and proposed corrections, never model weights and
    never user-provided claims as legal truth.
    """

    def ensure_table(self) -> None:
        with repository.connect() as con:
            con.execute('''
                create table if not exists feedback_reviews (
                    id text primary key,
                    feedback_id text,
                    conversation_id text,
                    question_fingerprint text not null,
                    question text not null,
                    previous_answer text,
                    feedback_note text,
                    primary_domain text,
                    status text not null,
                    old_score real,
                    proposed_answer text,
                    new_score real,
                    source_refs_json text not null default '[]',
                    retrieval_hints_json text not null default '[]',
                    review_reason text,
                    created_at text not null
                )
            ''')
            con.execute('create index if not exists feedback_reviews_question_idx on feedback_reviews(question_fingerprint,primary_domain,created_at desc)')
            con.execute('create index if not exists feedback_reviews_status_idx on feedback_reviews(status,created_at desc)')

    def save_review(self, *, feedback_id: str | None, conversation_id: str | None, question: str, previous_answer: str, feedback_note: str | None, primary_domain: str, status: str, old_score: float | None, proposed_answer: str | None, new_score: float | None, source_refs: list[dict], retrieval_hints: list[str], review_reason: str) -> dict:
        self.ensure_table(); rid=str(uuid.uuid4()); created=now_iso(); fp=question_fingerprint(question)
        with repository.connect() as con:
            con.execute('''insert into feedback_reviews(
                id,feedback_id,conversation_id,question_fingerprint,question,previous_answer,feedback_note,
                primary_domain,status,old_score,proposed_answer,new_score,source_refs_json,retrieval_hints_json,
                review_reason,created_at
            ) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(
                rid,feedback_id,conversation_id,fp,question,previous_answer,(feedback_note or '')[:1200],
                primary_domain,status,old_score,proposed_answer,new_score,
                json.dumps(source_refs or [],ensure_ascii=False),json.dumps(retrieval_hints or [],ensure_ascii=False),
                review_reason,created,
            ))
        return {'id':rid,'status':status,'question_fingerprint':fp,'created_at':created}

    def hint(self, question: str, primary_domain: str) -> dict | None:
        self.ensure_table(); fp=question_fingerprint(question)
        with repository.connect() as con:
            row=con.execute('''select id,retrieval_hints_json,source_refs_json,new_score,created_at
                from feedback_reviews
                where question_fingerprint=? and primary_domain=? and status='auto_corrected'
                order by created_at desc limit 1''',(fp,primary_domain)).fetchone()
        if not row: return None
        return {
            'review_id':row['id'],
            'retrieval_hints':json.loads(row['retrieval_hints_json'] or '[]'),
            'source_refs':json.loads(row['source_refs_json'] or '[]'),
            'score':row['new_score'],
            'created_at':row['created_at'],
        }

    def list_reviews(self, limit: int=50) -> list[dict]:
        self.ensure_table()
        with repository.connect() as con:
            rows=con.execute('''select id,feedback_id,conversation_id,question,feedback_note,primary_domain,status,
                old_score,proposed_answer,new_score,source_refs_json,retrieval_hints_json,review_reason,created_at
                from feedback_reviews order by created_at desc limit ?''',(min(max(int(limit),1),200),)).fetchall()
        out=[]
        for row in rows:
            item=dict(row)
            item['source_refs']=json.loads(item.pop('source_refs_json') or '[]')
            item['retrieval_hints']=json.loads(item.pop('retrieval_hints_json') or '[]')
            out.append(item)
        return out

    def stats(self) -> dict:
        self.ensure_table()
        with repository.connect() as con:
            rows=con.execute('select status,count(*) c from feedback_reviews group by status').fetchall()
        return {row['status']:row['c'] for row in rows}


feedback_review_store=FeedbackReviewStore()
