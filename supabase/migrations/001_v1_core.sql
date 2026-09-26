create extension if not exists pgcrypto;

create type public.app_role as enum ('student','tpo','admin');
create type public.assessment_status as enum ('draft','published','archived');
create type public.question_type as enum ('coding','debugging','knowledge','ast');
create type public.difficulty_level as enum ('easy','medium','hard');
create type public.submission_status as enum ('queued','running','completed','failed','late');

create table public.roles (id uuid primary key default gen_random_uuid(), name public.app_role unique not null, permissions jsonb not null default '{}'::jsonb);
insert into public.roles(name, permissions) values ('student','{"assessment_take":true,"ast_practice":true}'),('tpo','{"question_write":true,"assessment_write":true,"analytics":true}'),('admin','{"all":true}') on conflict do nothing;

create table public.profiles (
 id uuid primary key default gen_random_uuid(), auth_user_id uuid unique not null references auth.users(id) on delete cascade,
 full_name text not null default '', email text not null, role public.app_role not null default 'student', college_id uuid, department text,
 active boolean not null default true, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index profiles_auth_user_idx on public.profiles(auth_user_id);

create or replace function public.current_profile_id() returns uuid language sql stable security definer set search_path = public as $$ select id from public.profiles where auth_user_id = auth.uid() and active = true limit 1 $$;
create or replace function public.current_role() returns public.app_role language sql stable security definer set search_path = public as $$ select role from public.profiles where auth_user_id = auth.uid() and active = true limit 1 $$;

create table public.questions (
 id uuid primary key default gen_random_uuid(), concept_key text not null, version integer not null default 1, title text not null, prompt text not null,
 constraints_text text, examples jsonb not null default '[]', seed_parameters jsonb not null default '{}', hidden_tests jsonb not null default '[]',
 scoring_rules jsonb not null default '{"max_score":100}', runtime_image text not null default 'python:3.12-slim', language text not null,
 difficulty public.difficulty_level not null, question_type public.question_type not null, published boolean not null default false,
 created_by uuid not null references public.profiles(id), created_at timestamptz not null default now(), unique(concept_key,version)
);
create table public.question_roles(question_id uuid references public.questions(id) on delete cascade, role_name text not null, primary key(question_id,role_name));
create table public.question_skills(question_id uuid references public.questions(id) on delete cascade, skill_name text not null, weight numeric not null default 1, primary key(question_id,skill_name));
create table public.question_languages(question_id uuid references public.questions(id) on delete cascade, language text not null, starter_code text not null default '', primary key(question_id,language));

create table public.assessments (
 id uuid primary key default gen_random_uuid(), title text not null, description text not null default '', target_role text not null, allowed_languages text[] not null,
 duration_minutes integer not null check(duration_minutes between 5 and 480), attempt_policy jsonb not null default '{"max_attempts":1}', skill_distribution jsonb not null default '{}', difficulty_distribution jsonb not null default '{}',
 status public.assessment_status not null default 'draft', author_id uuid not null references public.profiles(id), published_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index assessments_author_status_idx on public.assessments(author_id,status);
create table public.assessment_questions(assessment_id uuid references public.assessments(id) on delete cascade, question_id uuid references public.questions(id), position integer not null, points numeric not null default 100, question_snapshot jsonb, primary key(assessment_id,question_id), unique(assessment_id,position));
create table public.assessment_assignments(id uuid primary key default gen_random_uuid(), assessment_id uuid not null references public.assessments(id) on delete cascade, student_id uuid not null references public.profiles(id) on delete cascade, assigned_by uuid not null references public.profiles(id), created_at timestamptz not null default now(), unique(assessment_id,student_id));

create table public.attempts(id uuid primary key default gen_random_uuid(), assessment_id uuid not null references public.assessments(id), student_id uuid not null references public.profiles(id), started_at timestamptz not null default now(), deadline_at timestamptz not null, submitted_at timestamptz, status text not null default 'active', unique(assessment_id,student_id));
create index attempts_student_idx on public.attempts(student_id,status);
create table public.submissions(id uuid primary key default gen_random_uuid(), attempt_id uuid not null references public.attempts(id) on delete cascade, question_id uuid not null references public.questions(id), student_id uuid not null references public.profiles(id), language text not null, source_code text not null, status public.submission_status not null default 'queued', score numeric, feedback jsonb, submitted_at timestamptz not null default now(), completed_at timestamptz);
create index submissions_attempt_idx on public.submissions(attempt_id,status);
create table public.execution_logs(id uuid primary key default gen_random_uuid(), submission_id uuid not null references public.submissions(id) on delete cascade, runtime_image text not null, seed jsonb not null, normalized_result jsonb, stdout text, stderr text, exit_code integer, timed_out boolean not null default false, network_disabled boolean not null default true, resource_limits jsonb not null default '{"cpus":1,"memory_mb":256}', started_at timestamptz not null default now(), finished_at timestamptz);
create table public.integrity_events(id uuid primary key default gen_random_uuid(), attempt_id uuid not null references public.attempts(id) on delete cascade, student_id uuid not null references public.profiles(id), event_type text not null, metadata jsonb not null default '{}', occurred_at timestamptz not null default now());
create table public.ast_challenges(id uuid primary key default gen_random_uuid(), title text not null, language text not null, buggy_source text not null, patch_rules jsonb not null, skill_name text not null, active boolean not null default true);
create table public.ast_attempts(id uuid primary key default gen_random_uuid(), challenge_id uuid not null references public.ast_challenges(id), student_id uuid not null references public.profiles(id), patch text not null, passed boolean not null, score numeric not null default 0, created_at timestamptz not null default now());
create table public.student_readiness(id uuid primary key default gen_random_uuid(), student_id uuid not null references public.profiles(id), readiness_score numeric check(readiness_score between 0 and 100), model_version text not null, feature_snapshot jsonb not null, inferred_at timestamptz not null default now());
create index readiness_student_idx on public.student_readiness(student_id,inferred_at desc);
create table public.audit_logs(id uuid primary key default gen_random_uuid(), actor_id uuid references public.profiles(id), action text not null, entity_type text not null, entity_id uuid, metadata jsonb not null default '{}', created_at timestamptz not null default now());

create or replace function public.prevent_published_question_mutation() returns trigger language plpgsql as $$ begin if old.published then raise exception 'Published question versions are immutable'; end if; return new; end $$;
create trigger immutable_published_questions before update or delete on public.questions for each row execute function public.prevent_published_question_mutation();
create or replace function public.prevent_published_assessment_mutation() returns trigger language plpgsql as $$ begin if old.status = 'published' and (new.status <> 'archived' or new.title <> old.title or new.duration_minutes <> old.duration_minutes or new.allowed_languages <> old.allowed_languages) then raise exception 'Published assessments are immutable'; end if; return new; end $$;
create trigger immutable_published_assessments before update on public.assessments for each row execute function public.prevent_published_assessment_mutation();

alter table public.profiles enable row level security;
alter table public.assessments enable row level security;
alter table public.assessment_questions enable row level security;
alter table public.assessment_assignments enable row level security;
alter table public.questions enable row level security;
alter table public.question_roles enable row level security;
alter table public.question_skills enable row level security;
alter table public.question_languages enable row level security;
alter table public.attempts enable row level security;
alter table public.submissions enable row level security;
alter table public.integrity_events enable row level security;
alter table public.ast_challenges enable row level security;
alter table public.ast_attempts enable row level security;
alter table public.student_readiness enable row level security;
alter table public.audit_logs enable row level security;

create policy profiles_self on public.profiles for select using(auth_user_id=auth.uid() or public.current_role() in ('tpo','admin'));
create policy profiles_admin_write on public.profiles for all using(public.current_role()='admin') with check(public.current_role()='admin');
create policy assessment_permitted on public.assessments for select using(author_id=public.current_profile_id() or status='published' and exists(select 1 from public.assessment_assignments a where a.assessment_id=id and a.student_id=public.current_profile_id()) or public.current_role()='admin');
create policy assessment_tpo_write on public.assessments for all using(public.current_role() in ('tpo','admin')) with check(author_id=public.current_profile_id() or public.current_role()='admin');
create policy assessment_question_permitted on public.assessment_questions for select using(exists(select 1 from public.assessments a where a.id=assessment_id and (a.author_id=public.current_profile_id() or exists(select 1 from public.assessment_assignments x where x.assessment_id=a.id and x.student_id=public.current_profile_id()) or public.current_role()='admin')));
create policy assignments_permitted on public.assessment_assignments for select using(student_id=public.current_profile_id() or assigned_by=public.current_profile_id() or public.current_role()='admin');
create policy questions_tpo_admin on public.questions for all using(public.current_role() in ('tpo','admin')) with check(public.current_role() in ('tpo','admin'));
create policy questions_student_published on public.questions for select using(published=true);
create policy attempts_self on public.attempts for all using(student_id=public.current_profile_id() or public.current_role() in ('tpo','admin')) with check(student_id=public.current_profile_id() or public.current_role() in ('tpo','admin'));
create policy submissions_self on public.submissions for all using(student_id=public.current_profile_id() or public.current_role() in ('tpo','admin')) with check(student_id=public.current_profile_id() or public.current_role() in ('tpo','admin'));
create policy integrity_self_insert on public.integrity_events for insert with check(student_id=public.current_profile_id());
create policy integrity_authorized_read on public.integrity_events for select using(student_id=public.current_profile_id() or public.current_role() in ('tpo','admin'));
create policy ast_challenges_read on public.ast_challenges for select using(active=true or public.current_role() in ('tpo','admin'));
create policy ast_attempts_self on public.ast_attempts for all using(student_id=public.current_profile_id() or public.current_role() in ('tpo','admin')) with check(student_id=public.current_profile_id() or public.current_role() in ('tpo','admin'));
create policy readiness_self on public.student_readiness for select using(student_id=public.current_profile_id() or public.current_role() in ('tpo','admin'));
create policy audit_admin_read on public.audit_logs for select using(public.current_role()='admin');
