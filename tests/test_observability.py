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
                {'id': 'c1', 'domain': 'labor', 'document_id': 'd1', 'article': '1'},
                {'id': 'c2', 'domain': 'labor', 'document_id': 'd1', 'article': '2'},
                {'id': 'c3', 'domain': 'civil', 'document_id': 'd2', 'article': None},
            ],
            'legal_documents': [
                {
                    'id': 'd1',
                    'title_ar': 'قانون العمل رقم 8 لسنة 1996 وتعديلاته',
                    'domain': 'labor',
                    'source_url': 'https://example.test/labor.pdf',
                    'source_kind': 'official_sync',
                },
                {
                    'id': 'd2',
                    'title_ar': 'القانون المدني رقم 43 لسنة 1976 وتعديلاته',
                    'domain': 'civil',
                    'source_url': 'https://example.test/civil',
                    'source_kind': 'reference',
                },
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
    assert stats['domains'] == {'labor': 2, 'civil': 1}
    assert stats['local_fallback'] == {'chunks': 2, 'documents': 1}


def test_effective_coverage_uses_cloud_documents_not_local_snapshot(monkeypatch):
    monkeypatch.setattr(observability.supabase_store, 'client', _Client())
    monkeypatch.setattr(observability.repository, 'coverage', lambda: [{'title': 'LOCAL_ONLY'}])
    observability.clear_observability_cache()

    coverage = observability.effective_coverage()
    labor = next(row for row in coverage if row['domain'] == 'labor')
    civil = next(row for row in coverage if row['domain'] == 'civil')

    assert labor['store'] == 'supabase'
    assert labor['chunks'] == 2
    assert labor['distinct_articles'] == 2
    assert labor['status'] == 'partial'
    assert labor['source_urls'] == ['https://example.test/labor.pdf']
    assert civil['chunks'] == 1
    assert civil['status'] == 'reference_only'
    assert all(row['title'] != 'LOCAL_ONLY' for row in coverage)


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
