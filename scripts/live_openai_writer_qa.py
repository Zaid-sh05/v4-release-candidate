from __future__ import annotations

import sys

import httpx

from scripts.live_production_qa import BASE_URL, TIMEOUT, cleanup, created_conversations, post_chat, supabase_client


def fail(message: str) -> None:
    raise AssertionError(message)


def main() -> int:
    sb=supabase_client()
    client=httpx.Client(timeout=TIMEOUT,follow_redirects=True)
    try:
        health=client.get(f"{BASE_URL}/api/health")
        if health.status_code!=200:
            fail(f"health {health.status_code}: {health.text[:500]}")
        data=health.json()
        answer_ai=((data.get('ai') or {}).get('answer_generation') or {})
        if answer_ai.get('provider')!='openai' or answer_ai.get('configured') is not True:
            fail(f"Railway OpenAI answer generation is not configured: {answer_ai}")
        model=str(answer_ai.get('model') or '')
        if not model.startswith('gpt-5.6'):
            fail(f"Unexpected OpenAI answer model: {model!r}")
        print(f"[PASS] OpenAI configured on Railway -> {model}")

        question='حالات الفصل التعسفي في القانون الأردني'
        response=post_chat(client,question,language='ar')
        route=response.get('route') or {}
        if route.get('primary_domain')!='labor':
            fail(f"arbitrary-dismissal overview routed incorrectly: {route}")
        mode=str(response.get('mode') or '')
        if not mode.startswith('official-openai-grounded-writer'):
            fail(f"OpenAI writer was not selected; mode={mode}; answer={(response.get('answer') or '')[:900]}")
        answer=response.get('answer') or ''
        if '[S' not in answer:
            fail(f"OpenAI writer answer lost official citations: {answer[:900]}")
        if len(answer)<450:
            fail(f"OpenAI writer answer is too thin for a legal overview: {answer[:900]}")
        structure_markers=(
            'المبدأ','الحالات','الحالة','متى','الحقوق','النتائج','الإجراءات','الإجراء',
            'الإثبات','الأدلة','ملاحظة','الأساس القانوني','التعويض','الفصل التعسفي',
        )
        hits=sum(1 for marker in structure_markers if marker in answer)
        if hits<3:
            fail(f"OpenAI writer answer is not sufficiently structured; hits={hits}: {answer[:1200]}")
        sources=response.get('sources') or []
        if not sources:
            fail('OpenAI writer returned no official sources')
        if any(s.get('domain')!='labor' for s in sources):
            fail(f"OpenAI writer leaked non-labor sources: {[s.get('domain') for s in sources]}")
        print(f"[PASS] grounded labor overview -> mode={mode}, sources={len(sources)}, structure_hits={hits}")

        print('\nLIVE OPENAI WRITER QA: PASS')
        return 0
    finally:
        try:
            cleanup(sb)
        finally:
            client.close()


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"\nLIVE OPENAI WRITER QA: FAIL\n{type(exc).__name__}: {exc}",file=sys.stderr)
        raise
