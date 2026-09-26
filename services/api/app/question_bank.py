from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

SUPPORTED_LANGUAGES = {'python', 'java', 'cpp', 'javascript', 'c'}
SUPPORTED_DIFFICULTIES = {'easy', 'medium', 'hard'}
SUPPORTED_TYPES = {'coding', 'debugging', 'knowledge', 'ast'}


def slugify(value: str) -> str:
    value = re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')
    if not value:
        raise ValueError('title must produce a non-empty slug')
    return value[:120]


def validate_question_input(body: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
    required = ('concept_key', 'title', 'prompt', 'language', 'difficulty', 'question_type')
    if not partial:
        missing = [key for key in required if not body.get(key)]
        if missing:
            raise ValueError(f'Missing fields: {", ".join(missing)}')
    normalized = deepcopy(body)
    if 'title' in normalized and normalized['title']:
        normalized['slug'] = normalized.get('slug') or slugify(normalized['title'])
    if normalized.get('language') and normalized['language'].lower() not in SUPPORTED_LANGUAGES:
        raise ValueError('language must be one of Python, Java, C++, JavaScript, or C')
    if normalized.get('difficulty') and normalized['difficulty'].lower() not in SUPPORTED_DIFFICULTIES:
        raise ValueError('difficulty must be easy, medium, or hard')
    if normalized.get('question_type') and normalized['question_type'].lower() not in SUPPORTED_TYPES:
        raise ValueError('question_type must be coding, debugging, knowledge, or ast')
    if 'roles' in normalized and (not isinstance(normalized['roles'], list) or not all(isinstance(x, str) and x.strip() for x in normalized['roles'])):
        raise ValueError('roles must be a list of non-empty strings')
    if 'skills' in normalized and (not isinstance(normalized['skills'], list) or not all(isinstance(x, str) and x.strip() for x in normalized['skills'])):
        raise ValueError('skills must be a list of non-empty strings')
    if 'language_variants' in normalized:
        variants = normalized['language_variants']
        if not isinstance(variants, list) or not all(isinstance(x, dict) and x.get('language','').lower() in SUPPORTED_LANGUAGES for x in variants):
            raise ValueError('language_variants must contain supported language objects')
    if 'scoring_rules' in normalized and not isinstance(normalized['scoring_rules'], dict):
        raise ValueError('scoring_rules must be an object')
    if 'seed_parameters' in normalized and not isinstance(normalized['seed_parameters'], dict):
        raise ValueError('seed_parameters must be an object')
    return normalized


def next_version(rows: list[dict[str, Any]]) -> int:
    return max((int(row.get('version', 0)) for row in rows), default=0) + 1


def build_version_payload(source: dict[str, Any], overrides: dict[str, Any], version: int, created_by: str) -> dict[str, Any]:
    payload = deepcopy(source)
    for key in ('id', 'created_at', 'updated_at', 'published', 'version'):
        payload.pop(key, None)
    payload.update(overrides)
    payload['version'] = version
    payload['published'] = False
    payload['active'] = True
    payload['created_by'] = created_by
    return payload


def matches_filters(row: dict[str, Any], *, search: str = '', role: str = '', language: str = '', skill: str = '', difficulty: str = '', question_type: str = '', active: str = '') -> bool:
    haystack = f"{row.get('title','')} {row.get('description','')} {row.get('concept_key','')}".lower()
    if search and search.lower() not in haystack: return False
    if language and row.get('language') != language: return False
    if difficulty and row.get('difficulty') != difficulty: return False
    if question_type and row.get('question_type') != question_type: return False
    if active in ('true', 'false') and str(row.get('active', True)).lower() != active: return False
    roles = {x.get('role_name') for x in row.get('question_roles', [])}
    skills = {x.get('skill_name') for x in row.get('question_skills', [])}
    if role and role not in roles: return False
    if skill and skill not in skills: return False
    return True
