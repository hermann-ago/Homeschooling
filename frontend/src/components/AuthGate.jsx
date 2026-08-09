import { useEffect, useState } from 'react';
import { isSupabaseConfigured, supabase } from '../lib/supabase';

const emptySetup = { setup_code: '', email: '', password: '' };

export default function AuthGate({ children }) {
  const [session, setSession] = useState(undefined);
  const [mode, setMode] = useState('login');
  const [form, setForm] = useState(emptySetup);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!supabase) return;
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: subscription } = supabase.auth.onAuthStateChange((_event, next) => setSession(next));
    const expire = () => setSession(null);
    window.addEventListener('auth:expired', expire);
    return () => {
      subscription.subscription.unsubscribe();
      window.removeEventListener('auth:expired', expire);
    };
  }, []);

  if (!isSupabaseConfigured) {
    return <main className="min-h-screen grid place-items-center p-6"><p>Hosted authentication is not configured yet.</p></main>;
  }
  if (session === undefined) return <main className="min-h-screen grid place-items-center">Loading…</main>;
  if (session) return children;

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      if (mode === 'setup') {
        const response = await fetch('/api/setup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(form),
        });
        const body = await response.json();
        if (!response.ok) throw new Error(body.detail || 'Setup failed');
      }
      const { error: signInError } = await supabase.auth.signInWithPassword({
        email: form.email,
        password: form.password,
      });
      if (signInError) throw signInError;
    } catch (submitError) {
      setError(submitError.message || 'Unable to sign in');
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="min-h-screen bg-background grid place-items-center p-6">
      <form onSubmit={submit} className="w-full max-w-sm rounded-xl bg-surface border border-border p-6 shadow-soft space-y-4">
        <div><h1 className="text-2xl font-bold">Homeschooler</h1><p className="text-sm text-text-secondary mt-1">{mode === 'setup' ? 'Create the shared family account.' : 'Sign in to your family workspace.'}</p></div>
        {mode === 'setup' && <label className="block text-sm">One-time setup code<input required type="password" value={form.setup_code} onChange={(e) => setForm({ ...form, setup_code: e.target.value })} className="mt-1 w-full rounded border p-2" /></label>}
        <label className="block text-sm">Email<input required type="email" autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="mt-1 w-full rounded border p-2" /></label>
        <label className="block text-sm">Password<input required minLength="12" type="password" autoComplete={mode === 'setup' ? 'new-password' : 'current-password'} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className="mt-1 w-full rounded border p-2" /></label>
        {error && <p className="text-sm text-red-700">{error}</p>}
        <button disabled={busy} className="w-full rounded bg-accent text-white py-2 disabled:opacity-60">{busy ? 'Please wait…' : mode === 'setup' ? 'Create family account' : 'Sign in'}</button>
        <button type="button" onClick={() => { setMode(mode === 'login' ? 'setup' : 'login'); setError(''); }} className="w-full text-sm text-text-secondary underline">{mode === 'login' ? 'First-time setup' : 'Back to sign in'}</button>
      </form>
    </main>
  );
}
