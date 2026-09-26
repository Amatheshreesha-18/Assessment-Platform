import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3]))
from services.api.app.main import settings, supabase_root


def test_supabase_root_normalizes_rest_url(monkeypatch):
    original = settings.supabase_url
    monkeypatch.setattr(settings, 'supabase_url', 'https://project.supabase.co/rest/v1/')
    assert supabase_root() == 'https://project.supabase.co'
    monkeypatch.setattr(settings, 'supabase_url', 'https://project.supabase.co')
    assert supabase_root() == 'https://project.supabase.co'
    monkeypatch.setattr(settings, 'supabase_url', original)


def test_browser_env_contract_does_not_use_server_key():
    frontend = Path(__file__).parents[3] / 'apps/web/app/page.tsx'
    source = frontend.read_text()
    assert 'SUPABASE_SERVICE_ROLE_KEY' not in source
    assert 'NEXT_PUBLIC_SUPABASE_ANON_KEY' in source


def test_service_role_key_has_no_public_key_fallback():
    assert "os.getenv('SUPABASE_SERVICE_ROLE_KEY','')" in Path(__file__).parents[1].joinpath('app/main.py').read_text()
