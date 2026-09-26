# Placement Readiness & Smart Assessment Platform

V1 MVP implementation baseline from `Manus_AI_Final_PRD_V1_MVP.pdf`.

## Architecture

- `apps/web`: Next.js 14 App Router, Supabase email/password session, role-aware dashboards, assessment workspace.
- `services/api`: FastAPI REST API using Supabase Auth JWT verification and PostgREST/service-role access server-side.
- `packages/deterministic-engine`: seeded, reproducible rule-based scoring primitives.
- `services/worker`: worker boundary for Redis/Celery/Docker execution; local deterministic fallback is used when infrastructure is unavailable.
- `supabase/migrations`: PostgreSQL schema, RLS policies, triggers, immutable published question versions.

## Run locally

```bash
cp .env.example services/api/.env
cp .env.example apps/web/.env.local
python3 -m venv .venv && . .venv/bin/activate
pip install -r services/api/requirements.txt
uvicorn app.main:app --reload --app-dir services/api --port 8000

cd apps/web && npm install && npm run dev
```

Apply `supabase/migrations/001_v1_core.sql` to the connected Supabase project. The API never exposes the service-role key to the browser.

## V1 security decisions

- Supabase Auth is the only credential authority; no passwords are stored by the app.
- All user-facing tables have RLS. The API verifies bearer JWTs and uses a service-role client only server-side.
- The browser timer is display-only. `POST /api/attempts/{id}/submit` compares server UTC time with `deadline_at`.
- Authoritative scores come only from deterministic seeded evaluation. Readiness/ML is asynchronous insight and cannot affect scoring.
- Published assessment snapshots and question versions are immutable.

## Test commands

```bash
pytest -q services/api/tests
python3 -m unittest discover -s packages/deterministic-engine/tests
npm --prefix apps/web run build
```
