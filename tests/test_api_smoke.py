import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from app.main import app

EMOJI = re.compile('[\\U0001F1E6-\\U0001FAFF\\u2600-\\u27BF]+')


def test_api_smoke():
    """End-to-end smoke coverage for the public API without external paid services."""
    with TestClient(app) as c:
        for path in ['/', '/api/health', '/api/domains', '/api/sources', '/api/coverage']:
            r = c.get(path)
            assert r.status_code == 200, (path, r.status_code)

        cases = [
            ('مرحبا', 'ar', ['conversation']),
            ('فصلني صاحب العمل بدون إنذار', 'ar', ['labor']),
            ('قطعت إشارة حمراء شو العقوبة؟', 'ar', ['traffic']),
            ('عقوبة الزنا', 'ar', ['criminal']),
            ('واحد ببتزني على واتساب', 'ar', ['cyber', 'criminal']),
            ('بدي أستأنف حكم بقضية سرقة', 'ar', ['procedure', 'criminal']),
            ('Hello', 'en', ['conversation']),
        ]

        for msg, lang, expected in cases:
            r = c.post('/api/chat', json={'message': msg, 'language': lang})
            assert r.status_code == 200, msg
            data = r.json()
            assert data['route']['domains'][:len(expected)] == expected, (msg, data['route']['domains'])
            assert not EMOJI.search(data['answer']), data['answer']

            for src in data['sources']:
                assert '%D8' not in src['title'] and '%D9' not in src['title'], src['title']
                assert not re.fullmatch(r'[0-9a-f-]{30,}(?:\\.pdf)?', src['title'], re.I), src['title']


def main():
    test_api_smoke()
    print('api smoke tests: OK')


if __name__ == '__main__':
    main()
