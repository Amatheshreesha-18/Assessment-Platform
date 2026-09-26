'use client';

import { useEffect, useState } from 'react';
import Editor from '@monaco-editor/react';
import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || 'https://build-placeholder.supabase.co';
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || 'build-placeholder-anon-key';
const supabase = createClient(supabaseUrl, supabaseAnonKey);
const api = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

type User = { id: string; full_name: string; email: string; role: 'student' | 'tpo' | 'admin' };
type Assessment = {
  id: string; title: string; description: string; target_role: string;
  allowed_languages: string[]; duration_minutes: number; status: string; questions?: any[];
};

export default function Home() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [user, setUser] = useState<User | null>(null);
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [selected, setSelected] = useState<Assessment | null>(null);
  const [attempt, setAttempt] = useState<any>(null);
  const [code, setCode] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [remaining, setRemaining] = useState<number | null>(null);

  const token = async () => (await supabase.auth.getSession()).data.session?.access_token;
  const request = async (path: string, init: RequestInit = {}) => {
    const sessionToken = await token();
    const response = await fetch(api + path, {
      ...init,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${sessionToken}`, ...(init.headers || {}) },
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || 'Request failed');
    return body;
  };

  useEffect(() => {
    supabase.auth.getSession().then(async ({ data }) => {
      if (!data.session) return;
      try {
        setUser(await request('/api/me'));
        setAssessments(await request('/api/assessments'));
      } catch (error) { setMessage(String(error)); }
    });
  }, []);

  useEffect(() => {
    if (!attempt) return;
    const timer = setInterval(() => {
      const seconds = Math.max(0, Math.floor((new Date(attempt.deadline_at).getTime() - Date.now()) / 1000));
      setRemaining(seconds);
      if (seconds === 0) clearInterval(timer);
    }, 1000);
    return () => clearInterval(timer);
  }, [attempt]);

  async function login(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setMessage('');
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) { setMessage(error.message); setBusy(false); return; }
    location.reload();
  }

  async function start(assessment: Assessment) {
    try {
      const detail = await request('/api/assessments/' + assessment.id);
      setSelected(detail);
      setAttempt(await request('/api/attempts', { method: 'POST', body: JSON.stringify({ assessment_id: assessment.id }) }));
      setCode(detail.questions?.[0]?.questions?.question_languages?.[0]?.starter_code || '');
    } catch (error) { setMessage(String(error)); }
  }

  async function submit() {
    if (!selected || !attempt) return;
    setBusy(true);
    try {
      const questionId = selected.questions?.[0]?.question_id;
      await request('/api/submissions', {
        method: 'POST',
        body: JSON.stringify({ attempt_id: attempt.id, question_id: questionId, language: selected.allowed_languages[0], source_code: code }),
      });
      setMessage('Submission accepted and scored by deterministic engine.');
    } catch (error) { setMessage(String(error)); }
    setBusy(false);
  }

  if (!user) return (
    <main className="auth"><section className="auth-card">
      <div className="eyebrow">PLACEMENT READINESS / V1</div><h1>Assess what matters.</h1>
      <p className="muted">A secure, deterministic assessment workspace for modern campus hiring.</p>
      <form onSubmit={login}>
        <label>Email<input type="email" value={email} onChange={event => setEmail(event.target.value)} required /></label>
        <label>Password<input type="password" value={password} onChange={event => setPassword(event.target.value)} required /></label>
        <button disabled={busy}>{busy ? 'Signing in…' : 'Sign in with email'}</button>
      </form>
      {message && <p className="error">{message}</p>}
      <p className="hint">Accounts are provisioned by an administrator in Supabase Auth.</p>
    </section></main>
  );

  return <main className="shell">
    <header><div><div className="eyebrow">PLACEMENT READINESS / V1</div><h1>{attempt ? 'Assessment workspace' : `Good to see you, ${user.full_name || 'there'}`}</h1></div>
      <div className="profile"><span>{user.role.toUpperCase()}</span><button className="ghost" onClick={() => supabase.auth.signOut().then(() => location.reload())}>Sign out</button></div>
    </header>
    {attempt && selected ? <section className="workspace">
      <aside><button className="ghost" onClick={() => { setAttempt(null); setSelected(null); }}>← Back to assessments</button>
        <div className="timer"><small>SERVER DEADLINE</small><strong>{remaining === null ? '—' : `${Math.floor(remaining / 60).toString().padStart(2, '0')}:${(remaining % 60).toString().padStart(2, '0')}`}</strong><p>Browser countdown is display-only.</p></div>
        <h2>{selected.title}</h2><p>{selected.description}</p><div className="pill">{selected.target_role}</div><div className="pill">{selected.allowed_languages?.join(' · ')}</div>
      </aside>
      <section className="editor-panel"><div className="editor-head"><span>Question 01 / {selected.questions?.length || 1}</span><span className="muted">Autosave enabled · deterministic tests</span></div>
        <div className="prompt">{selected.questions?.[0]?.questions?.prompt || 'Solve the coding challenge described by your evaluator.'}</div>
        <Editor height="48vh" theme="vs-dark" defaultLanguage="python" value={code} onChange={value => setCode(value || '')} options={{ minimap: { enabled: false }, fontSize: 14, roundedSelection: false }} />
        <div className="editor-actions"><span>{message}</span><button onClick={submit} disabled={busy || remaining === 0}>{busy ? 'Submitting…' : 'Submit solution'}</button></div>
      </section>
    </section> : <>
      <section className="hero"><div><span className="status-dot" /> {user.role === 'student' ? 'Your assigned assessments' : 'Workspace overview'}<h2>Build signal.<br /><em>Not noise.</em></h2></div><p>Every assessment is versioned, time-bound, and scored by reproducible tests. AI insights never determine your authoritative result.</p></section>
      <section className="section-head"><h2>{user.role === 'student' ? 'Assigned assessments' : 'Assessments'}</h2><span>{assessments.length} active</span></section>
      <section className="cards">{assessments.map(assessment => <article className="card" key={assessment.id}><div className="card-top"><span className="pill">{assessment.target_role}</span><span className="muted">{assessment.duration_minutes} min</span></div><h3>{assessment.title}</h3><p>{assessment.description || 'Role-aligned assessment with deterministic evaluation.'}</p><div className="card-foot"><span>{assessment.status}</span><button onClick={() => start(assessment)}>Open assessment →</button></div></article>)}{!assessments.length && <div className="empty">No assessments assigned yet.</div>}</section>
    </>}
  </main>;
}
