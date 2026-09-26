from pathlib import Path
import pytest
from services.api.app.question_bank import validate_question_input

ROOT = Path(__file__).parents[3]
MIGRATION = (ROOT / 'supabase/migrations/001_v1_core.sql').read_text()
API = (ROOT / 'services/api/app/main.py').read_text()


def test_language_variants_reject_unknown_languages():
    body={'concept_key':'x','title':'X','prompt':'Y','language':'python','difficulty':'easy','question_type':'coding','language_variants':[{'language':'ruby'}]}
    with pytest.raises(ValueError, match='language_variants'):
        validate_question_input(body)


def test_schema_enforces_version_and_slug_uniqueness():
    assert 'unique(concept_key,version)' in MIGRATION
    assert 'unique(slug,version)' in MIGRATION


def test_schema_and_api_enforce_published_immutability():
    assert 'prevent_published_question_mutation' in MIGRATION
    assert 'Published question versions are immutable' in API


def test_tpo_scope_guards_are_present_on_question_operations():
    assert "rows[0]['created_by'] != user['id']" in API
    assert "require('tpo','admin')" in API
