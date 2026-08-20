from __future__ import annotations

from pathlib import Path
import sys
import time

import httpx

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from scripts.live_production_qa import BASE_URL, cleanup, post_chat, supabase_client


def fail(message: str) -> None:
    raise AssertionError(message)


def main() -> int:
    sb=supabase_client()
    client=httpx.Client(timeout=45.0,follow_redirects=True)
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
        started=time.monotonic()
        response=post_chat(client,question,language='ar')
        elapsed=time.monotonic()-started
        route=response.get('route') or {}
        if route.get('primary_domain')!='labor':
            fail(f"arbitrary-dismissal overview routed incorrectly: {route}")
        mode=str(response.get('mode') or '')
        if not mode.startswith('official-openai-grounded-writer'):
            fail(f"OpenAI writer was not selected; mode={mode}; answer={(response.get('answer') or '')[:1200]}")
        answer=response.get('answer') or ''
        if '[S' not in answer:
            fail(f"OpenAI writer answer lost official citations: {answer[:1200]}")
        if len(answer)<650:
            fail(f"OpenAI writer answer is too thin for a legal overview: {answer[:1200]}")
        structure_markers=(
            'المبدأ','الحالات','الحالة','متى','الحقوق','النتائج','الإجراءات','الإجراء',
            'الإثبات','الأدلة','ملاحظة','الأساس القانوني','التعويض','الفصل التعسفي',
            'العقد','السبب','الإشعار','المصدر','التحقق',
        )
        hits=sum(1 for marker in structure_markers if marker in answer)
        if hits<5:
            fail(f"OpenAI writer answer is not sufficiently structured; hits={hits}: {answer[:1500]}")
        sources=response.get('sources') or []
        if not sources:
            fail('OpenAI writer returned no official sources')
        if any(s.get('domain')!='labor' for s in sources):
            fail(f"OpenAI writer leaked non-labor sources: {[s.get('domain') for s in sources]}")
        if elapsed>30.0:
            fail(f"OpenAI overview latency exceeded interactive budget: {elapsed:.1f}s")
        print(f"[PASS] grounded labor overview -> mode={mode}, sources={len(sources)}, structure_hits={hits}, latency={elapsed:.1f}s")
        print('--- ANSWER SAMPLE ---')
        print(answer[:1800])

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
