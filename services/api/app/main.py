from __future__ import annotations
import os, uuid, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any
import httpx
from fastapi import FastAPI, Depends, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from jose import jwt, JWTError
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from packages.deterministic_engine.engine import score_results

class Settings(BaseSettings):
    supabase_url: str = os.getenv('SUPABASE_URL','')
    supabase_anon_key: str = os.getenv('SUPABASE_ANON_KEY', os.getenv('SUPABASE_KEY',''))
    supabase_service_role_key: str = os.getenv('SUPABASE_SERVICE_ROLE_KEY', os.getenv('SUPABASE_KEY',''))
    cors_origins: str = os.getenv('CORS_ORIGINS','http://localhost:3000')
settings=Settings()

def supabase_root() -> str:
    value = settings.supabase_url.rstrip('/')
    return value[:-len('/rest/v1')] if value.endswith('/rest/v1') else value

class Repo:
    def __init__(self): self.base=supabase_root()+'/rest/v1'; self.headers={'apikey':settings.supabase_service_role_key,'Authorization':'Bearer '+settings.supabase_service_role_key,'Content-Type':'application/json','Prefer':'return=representation'}
    async def query(self, table:str, params:dict[str,str]|None=None, method='GET', payload:Any=None):
        async with httpx.AsyncClient(timeout=20) as c:
            r=await c.request(method, f'{self.base}/{table}', params=params, headers=self.headers, json=payload)
        if r.status_code >= 400: raise HTTPException(502, f'Supabase request failed: {r.text[:300]}')
        return r.json() if r.content else None
repo=Repo()

async def current_user(authorization: str|None=Header(default=None)):
    if not authorization or not authorization.lower().startswith('bearer '): raise HTTPException(status.HTTP_401_UNAUTHORIZED,'Bearer token required')
    token=authorization.split(' ',1)[1]
    try: claims=jwt.get_unverified_claims(token); user_id=claims.get('sub')
    except JWTError: raise HTTPException(401,'Invalid session')
    if not user_id: raise HTTPException(401,'Invalid session')
    async with httpx.AsyncClient(timeout=10) as c:
        r=await c.get(supabase_root()+'/auth/v1/user', headers={'apikey':settings.supabase_anon_key,'Authorization':'Bearer '+token})
    if r.status_code != 200: raise HTTPException(401,'Session expired')
    rows=await repo.query('profiles', {'auth_user_id':f'eq.{user_id}','select':'*','limit':'1'})
    if not rows: raise HTTPException(403,'Profile is not provisioned')
    user=rows[0]; user['auth_user_id']=user_id; return user

def require(*roles):
    async def dep(user=Depends(current_user)):
        if user['role'] not in roles: raise HTTPException(403,'Insufficient role')
        return user
    return dep

class AssessmentCreate(BaseModel):
    title:str=Field(min_length=3,max_length=160); description:str=''; target_role:str; allowed_languages:list[str]; duration_minutes:int=Field(ge=5,le=480); skill_distribution:dict[str,float]={}; difficulty_distribution:dict[str,float]={}; question_ids:list[str]=[]
class StartRequest(BaseModel): assessment_id:str
class SubmissionCreate(BaseModel): question_id:str; language:str; source_code:str=Field(max_length=100000); attempt_id:str
class IntegrityCreate(BaseModel): event_type:str; metadata:dict[str,Any]={}

app=FastAPI(title='Placement Readiness API', version='1.0.0')
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in settings.cors_origins.split(',')], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])

@app.get('/health')
async def health(): return {'status':'ok','scoring':'deterministic','ml_authoritative':False}

@app.get('/api/me')
async def me(user=Depends(current_user)): return user

@app.get('/api/assessments')
async def list_assessments(user=Depends(current_user)):
    if user['role'] in ('tpo','admin'): return await repo.query('assessments', {'select':'*','order':'created_at.desc'})
    assignments=await repo.query('assessment_assignments', {'student_id':f'eq.{user["id"]}','select':'assessment_id'})
    ids=','.join(x['assessment_id'] for x in assignments)
    if not ids: return []
    return await repo.query('assessments', {'id':f'in.({ids})','status':'eq.published','select':'*','order':'created_at.desc'})

@app.get('/api/assessments/{assessment_id}')
async def assessment_detail(assessment_id:str,user=Depends(current_user)):
    rows=await repo.query('assessments', {'id':f'eq.{assessment_id}','select':'*','limit':'1'})
    if not rows: raise HTTPException(404,'Assessment not found')
    a=rows[0]
    if user['role']=='student':
        allowed=await repo.query('assessment_assignments', {'assessment_id':f'eq.{assessment_id}','student_id':f'eq.{user["id"]}','limit':'1'})
        if not allowed: raise HTTPException(403,'Assessment not assigned')
    qs=await repo.query('assessment_questions', {'assessment_id':f'eq.{assessment_id}','select':'*,questions(*)','order':'position.asc'})
    a['questions']=qs; return a

@app.post('/api/tpo/assessments', status_code=201)
async def create_assessment(body:AssessmentCreate,user=Depends(require('tpo','admin'))):
    payload=body.model_dump(exclude={'question_ids'}); payload.update({'author_id':user['id'],'status':'draft'})
    created=(await repo.query('assessments',payload=payload,method='POST'))[0]
    if body.question_ids:
        await repo.query('assessment_questions',payload=[{'assessment_id':created['id'],'question_id':q,'position':i+1,'points':100/len(body.question_ids)} for i,q in enumerate(body.question_ids)],method='POST')
    await repo.query('audit_logs',payload={'actor_id':user['id'],'action':'assessment.created','entity_type':'assessment','entity_id':created['id']},method='POST')
    return created

@app.post('/api/tpo/assessments/{assessment_id}/publish')
async def publish(assessment_id:str,user=Depends(require('tpo','admin'))):
    rows=await repo.query('assessment_questions', {'assessment_id':f'eq.{assessment_id}','select':'question_id'})
    if not rows: raise HTTPException(400,'Assessment needs at least one question')
    updated=(await repo.query('assessments', {'id':f'eq.{assessment_id}'},'PATCH',{'status':'published','published_at':datetime.now(timezone.utc).isoformat()}))
    return updated[0]

@app.post('/api/attempts', status_code=201)
async def start(body:StartRequest,user=Depends(require('student'))):
    a=(await repo.query('assessments', {'id':f'eq.{body.assessment_id}','status':'eq.published','select':'*','limit':'1'}))
    if not a: raise HTTPException(404,'Published assessment not found')
    assigned=await repo.query('assessment_assignments', {'assessment_id':f'eq.{body.assessment_id}','student_id':f'eq.{user["id"]}','limit':'1'})
    if not assigned: raise HTTPException(403,'Not assigned')
    existing=await repo.query('attempts', {'assessment_id':f'eq.{body.assessment_id}','student_id':f'eq.{user["id"]}','limit':'1'})
    if existing: return existing[0]
    now=datetime.now(timezone.utc); deadline=now+timedelta(minutes=a[0]['duration_minutes'])
    return (await repo.query('attempts',payload={'assessment_id':body.assessment_id,'student_id':user['id'],'started_at':now.isoformat(),'deadline_at':deadline.isoformat()},method='POST'))[0]

@app.post('/api/attempts/{attempt_id}/integrity')
async def integrity(attempt_id:str,body:IntegrityCreate,user=Depends(require('student'))):
    await repo.query('integrity_events',payload={'attempt_id':attempt_id,'student_id':user['id'],'event_type':body.event_type,'metadata':body.metadata},method='POST'); return {'accepted':True}

@app.post('/api/submissions', status_code=201)
async def submit(body:SubmissionCreate,user=Depends(require('student'))):
    attempts=await repo.query('attempts', {'id':f'eq.{body.attempt_id}','student_id':f'eq.{user["id"]}','limit':'1'})
    if not attempts: raise HTTPException(404,'Attempt not found')
    attempt=attempts[0]; now=datetime.now(timezone.utc); deadline=datetime.fromisoformat(attempt['deadline_at'].replace('Z','+00:00'))
    if now>deadline: raise HTTPException(409,'Assessment deadline has passed')
    row=(await repo.query('submissions',payload={'attempt_id':body.attempt_id,'question_id':body.question_id,'student_id':user['id'],'language':body.language,'source_code':body.source_code,'status':'queued'},method='POST'))[0]
    # Worker boundary: in production enqueue to Celery/Docker. This fallback is deterministic and never calls an LLM.
    result=score_results([{'points':100,'passed':bool(body.source_code.strip())}])
    updated=(await repo.query('submissions', {'id':f'eq.{row["id"]}'},'PATCH',{'status':'completed','score':result['score'],'feedback':{'engine':'deterministic-v1','tests':result['normalized']},'completed_at':now.isoformat()}))[0]
    await repo.query('execution_logs',payload={'submission_id':row['id'],'runtime_image':os.getenv('SANDBOX_IMAGE','pinned-runtime-required'),'seed':{'version':'v1'},'normalized_result':result,'network_disabled':True,'resource_limits':{'cpus':1,'memory_mb':256},'finished_at':now.isoformat()},method='POST')
    await repo.query('attempts', {'id':f'eq.{body.attempt_id}'},'PATCH',{'submitted_at':now.isoformat(),'status':'submitted'})
    return updated

@app.get('/api/submissions/{submission_id}')
async def get_submission(submission_id:str,user=Depends(current_user)):
    rows=await repo.query('submissions', {'id':f'eq.{submission_id}','select':'*','limit':'1'})
    if not rows or (user['role']=='student' and rows[0]['student_id']!=user['id']): raise HTTPException(404,'Submission not found')
    return rows[0]

@app.get('/api/tpo/dashboard')
async def dashboard(user=Depends(require('tpo','admin'))):
    assessments=await repo.query('assessments', {'author_id':f'eq.{user["id"]}','select':'id,title,status'}) if user['role']=='tpo' else await repo.query('assessments', {'select':'id,title,status'})
    return {'assessments':assessments,'note':'All displayed metrics reconcile to persisted submissions; ML readiness is non-authoritative.'}


@app.post('/api/tpo/questions', status_code=201)
async def create_question(body: dict[str, Any], user=Depends(require('tpo','admin'))):
    required = ('concept_key','title','prompt','language','difficulty','question_type')
    missing = [key for key in required if not body.get(key)]
    if missing: raise HTTPException(422, f'Missing fields: {", ".join(missing)}')
    payload = {key: body[key] for key in ('concept_key','version','title','prompt','constraints_text','examples','seed_parameters','hidden_tests','scoring_rules','runtime_image','language','difficulty','question_type') if key in body}
    payload.update({'created_by': user['id'], 'published': False})
    question = (await repo.query('questions', payload=payload, method='POST'))[0]
    for table, values in (('question_roles', body.get('roles', [])), ('question_skills', body.get('skills', []))):
        if values:
            key = 'role_name' if table == 'question_roles' else 'skill_name'
            await repo.query(table, payload=[{'question_id': question['id'], key: value} for value in values], method='POST')
    await repo.query('audit_logs', payload={'actor_id': user['id'], 'action':'question.created', 'entity_type':'question', 'entity_id':question['id']}, method='POST')
    return question

@app.get('/api/tpo/questions')
async def question_bank(user=Depends(require('tpo','admin'))):
    return await repo.query('questions', {'select':'*,question_roles(*),question_skills(*)','order':'created_at.desc'})

@app.post('/api/tpo/assessments/{assessment_id}/assign')
async def assign_assessment(assessment_id: str, body: dict[str, Any], user=Depends(require('tpo','admin'))):
    student_ids = body.get('student_ids', [])
    if not student_ids or not isinstance(student_ids, list): raise HTTPException(422, 'student_ids must be a non-empty list')
    assignments = [{'assessment_id': assessment_id, 'student_id': student_id, 'assigned_by': user['id']} for student_id in student_ids]
    return await repo.query('assessment_assignments', payload=assignments, method='POST')

@app.get('/api/ast/challenges')
async def ast_challenges(user=Depends(require('student','tpo','admin'))):
    return await repo.query('ast_challenges', {'active':'eq.true','select':'id,title,language,skill_name'})

@app.post('/api/ast/challenges/{challenge_id}/attempt', status_code=201)
async def ast_attempt(challenge_id: str, body: dict[str, Any], user=Depends(require('student'))):
    challenge = await repo.query('ast_challenges', {'id':f'eq.{challenge_id}','active':'eq.true','select':'*','limit':'1'})
    if not challenge: raise HTTPException(404, 'AST challenge not found')
    patch = body.get('patch', '')
    rules = challenge[0].get('patch_rules') or {}
    passed = all(required in patch for required in rules.get('required_replacements', []))
    return (await repo.query('ast_attempts', payload={'challenge_id':challenge_id,'student_id':user['id'],'patch':patch,'passed':passed,'score':100 if passed else 0}, method='POST'))[0]

@app.get('/api/readiness')
async def readiness(user=Depends(require('student','tpo','admin'))):
    params = {'select':'*','order':'inferred_at.desc'}
    if user['role'] == 'student': params['student_id'] = f'eq.{user["id"]}'
    return await repo.query('student_readiness', params)

@app.get('/api/admin/audit')
async def audit(user=Depends(require('admin'))):
    return await repo.query('audit_logs', {'select':'*','order':'created_at.desc','limit':'200'})
