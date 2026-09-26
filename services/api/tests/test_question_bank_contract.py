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


def test_student_safe_projection_contains_content_but_no_private_configuration():
    from services.api.app.question_bank import student_safe_question
    safe=student_safe_question({'id':'q1','title':'Two sum','description':'Find a pair','prompt':'Return indices','examples':[{'input':'[]'}],'constraints_text':'n <= 1000','version':1,'language':'python','difficulty':'easy','question_type':'coding','published':True,'active':True,'hidden_tests':[{'input':'secret'}],'seed_parameters':{'seed':9},'scoring_rules':{'max_score':100},'runtime_image':'private:image','created_by':'author','question_languages':[{'language':'python','starter_code':'def solve():\n    pass'}],'question_skills':[{'skill_name':'Algorithms','weight':2}]})
    assert safe['title']=='Two sum'
    assert safe['description']=='Find a pair'
    assert safe['examples']==[{'input':'[]'}]
    assert safe['constraints_text']=='n <= 1000'
    assert safe['question_languages']==[{'language':'python','starter_code':'def solve():\n    pass'}]
    for private in ('hidden_tests','seed_parameters','scoring_rules','runtime_image','created_by'):
        assert private not in safe


def test_student_assessment_path_uses_explicit_projection():
    assert 'questions(*)' in API  # TPO/Admin authoring path remains available.
    assert "question_select = 'assessment_id,question_id,position,points,question_snapshot,questions(id" in API
    assert "if user['role']=='student'" in API


def test_applied_security_migration_removes_direct_student_question_policy():
    migration=(ROOT / 'supabase/migrations/002_restrict_student_question_rows.sql').read_text()
    assert 'drop policy if exists questions_student_published' in migration
