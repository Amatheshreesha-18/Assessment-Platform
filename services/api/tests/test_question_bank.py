import pytest
from services.api.app.question_bank import build_version_payload, matches_filters, next_version, slugify, validate_question_input


def valid():
    return {'concept_key':'arrays.first_unique','title':'First unique character','prompt':'Return the first unique character.','language':'python','difficulty':'easy','question_type':'coding','roles':['Software Developer'],'skills':['Data Structures'],'scoring_rules':{'max_score':100},'seed_parameters':{'seed':7}}


def test_question_validation_normalizes_slug_and_rejects_unknown_language():
    result=validate_question_input(valid())
    assert result['slug']=='first-unique-character'
    with pytest.raises(ValueError, match='language'):
        validate_question_input({**valid(), 'language':'ruby'})


def test_role_skill_and_language_mappings_are_preserved_in_payload():
    result=validate_question_input({**valid(), 'roles':['Backend Developer'], 'skills':['Algorithms']})
    assert result['roles']==['Backend Developer']
    assert result['skills']==['Algorithms']
    assert result['language']=='python'


def test_next_version_and_new_version_are_immutable_draft_copies():
    source={'id':'old','concept_key':'x','version':2,'title':'Old','published':True,'active':True,'created_by':'tpo','question_roles':[{'role_name':'Backend Developer'}]}
    assert next_version([{'version':1},{'version':2}])==3
    created=build_version_payload(source, {'title':'New'}, 3, 'tpo')
    assert 'id' not in created
    assert created['title']=='New'
    assert created['version']==3
    assert created['published'] is False
    assert source['title']=='Old'


def test_filter_supports_role_skill_and_search():
    row={**valid(), 'question_roles':[{'role_name':'Backend Developer'}], 'question_skills':[{'skill_name':'Algorithms'}], 'active':True}
    assert matches_filters(row, role='Backend Developer', skill='Algorithms', search='unique')
    assert not matches_filters(row, role='Data Analyst')
