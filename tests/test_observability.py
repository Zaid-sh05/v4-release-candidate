from app import observability


class _Response:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self.rows = rows
        self.start = 0
        self.end = 999

    def select(self, *_args, **_kwargs):
        return self

    def range(self, start, end):
        self.start = start
        self.end = end
        return self

    def execute(self):
        return _Response(self.rows[self.start:self.end + 1])


class _Client:
    def __init__(self):
        self.tables = {
            'legal_chunks': [
                {'id': 'c1', 'domain': 'commercial'},
                {'id': 'c2', 'domain': 'commercial'},
                {'id': 'c3', 'domain': 'labor'},
            ],
            'legal_documents': [
                {'id': 'd1'},
                {'id': 'd2'},
            ],
        }

    def table(self, name):
        return _Query(self.tables[name])


def test_effective_corpus_reports_cloud_when_supabase_is_configured(monkeypatch):
    monkeypatch.setattr(observability.supabase_store, 'client', _Client())
    monkeypatch.setattr(
        observability.repository,
        'stats',
        lambda: {
            'chunks': 2,
            'documents': 1,
            'registered_official_sources': 19,
            'canonical_documents': 6,
            'domains': {'commercial': 2},
        },
    )
    observability.clear_observability_cache()

    stats = observability.effective_corpus_stats()

    assert stats['store'] == 'supabase'
    assert stats['chunks'] == 3
    assert stats['documents'] == 2
    assert stats['domains'] == {'commercial': 2, 'labor': 1}
    assert stats['local_fallback'] == {'chunks': 2, 'documents': 1}


def test_ai_status_reports_groq_cognition_without_openai(monkeypatch):
    monkeypatch.setattr(observability.settings, 'openai_api_key', '')
    monkeypatch.setattr(observability.settings, 'cognition_llm_enabled', True)
    monkeypatch.setattr(observability.settings, 'cognition_llm_provider', 'groq')
    monkeypatch.setattr(observability.settings, 'groq_api_key', 'test-groq-key')
    monkeypatch.setattr(observability.settings, 'groq_cognition_model', 'openai/gpt-oss-120b')

    status = observability.ai_runtime_status()

    assert status['answer_generation']['provider'] == 'extractive'
    assert status['answer_generation']['configured'] is False
    assert status['cognition']['provider'] == 'groq'
    assert status['cognition']['configured'] is True
    assert status['cognition']['model'] == 'openai/gpt-oss-120b'
