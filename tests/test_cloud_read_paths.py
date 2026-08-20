from app import main as main_module


def test_public_search_prefers_supabase_keyword_search(monkeypatch):
    cloud_row = {
        'id': 'cloud-1',
        'title': 'قانون العمل رقم 8 لسنة 1996 وتعديلاته',
        'authority': 'وزارة العمل الأردنية',
        'domain': 'labor',
        'source_url': 'https://example.test/labor.pdf',
        'law_number': '8',
        'year': 1996,
        'article': '23',
        'excerpt': 'نص رسمي مسترجع من السحابة',
        'verified_at': '2026-08-20T00:00:00Z',
        'source_kind': 'official_sync',
        'score': 1.0,
    }
    monkeypatch.setattr(main_module.supabase_store, 'client', object())
    monkeypatch.setattr(main_module.supabase_store, 'keyword_search', lambda q, domains, limit: [cloud_row])
    monkeypatch.setattr(main_module.repository, 'search', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('local fallback should not run')))

    result = main_module.search('إنذار العامل', 'labor', 8)

    assert result['store'] == 'supabase'
    assert result['results'] == [cloud_row]


def test_public_search_falls_back_to_local_when_cloud_has_no_match(monkeypatch):
    local_row = {'id': 'local-1'}
    monkeypatch.setattr(main_module.supabase_store, 'client', object())
    monkeypatch.setattr(main_module.supabase_store, 'keyword_search', lambda q, domains, limit: [])
    monkeypatch.setattr(main_module.repository, 'search', lambda q, domains, limit: [local_row])

    result = main_module.search('اختبار', 'labor', 8)

    assert result['store'] == 'sqlite'
    assert result['results'] == [local_row]


def test_public_search_rejects_unknown_domain():
    try:
        main_module.search('اختبار', 'not-a-domain', 8)
    except Exception as exc:
        assert getattr(exc, 'status_code', None) == 400
    else:
        raise AssertionError('unknown domain must be rejected')
