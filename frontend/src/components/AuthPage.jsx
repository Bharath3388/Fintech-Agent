import { useState } from 'react';
import { LogIn, UserPlus, Mail, Lock, User, ArrowRight, Activity } from 'lucide-react';

const API = '/api';

export default function AuthPage({ onAuth }) {
  const [mode, setMode] = useState('login'); // login | signup
  const [form, setForm] = useState({ username: '', email: '', password: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    const endpoint = mode === 'login' ? '/login' : '/signup';
    const body = mode === 'login'
      ? { email: form.email, password: form.password }
      : { username: form.username, email: form.email, password: form.password };

    try {
      const resp = await fetch(`${API}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `${mode === 'login' ? 'Login' : 'Signup'} failed`);
      }

      const data = await resp.json();
      onAuth(data); // { token, username, email }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-card">
        <div className="auth-header">
          <Activity size={36} color="var(--accent-green)" />
          <h1 className="auth-title">Fintech Agent</h1>
          <p className="auth-subtitle">AI-Powered Loan Portfolio Analytics</p>
        </div>

        <div className="auth-tabs">
          <button
            className={`auth-tab ${mode === 'login' ? 'active' : ''}`}
            onClick={() => { setMode('login'); setError(''); }}
          >
            <LogIn size={14} /> Login
          </button>
          <button
            className={`auth-tab ${mode === 'signup' ? 'active' : ''}`}
            onClick={() => { setMode('signup'); setError(''); }}
          >
            <UserPlus size={14} /> Sign Up
          </button>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          {mode === 'signup' && (
            <div className="auth-field">
              <User size={16} className="auth-field-icon" />
              <input
                type="text"
                placeholder="Username"
                value={form.username}
                onChange={(e) => setForm(f => ({ ...f, username: e.target.value }))}
                required
                minLength={3}
              />
            </div>
          )}
          <div className="auth-field">
            <Mail size={16} className="auth-field-icon" />
            <input
              type="email"
              placeholder="Email"
              value={form.email}
              onChange={(e) => setForm(f => ({ ...f, email: e.target.value }))}
              required
            />
          </div>
          <div className="auth-field">
            <Lock size={16} className="auth-field-icon" />
            <input
              type="password"
              placeholder="Password"
              value={form.password}
              onChange={(e) => setForm(f => ({ ...f, password: e.target.value }))}
              required
              minLength={6}
            />
          </div>

          {error && <div className="auth-error">{error}</div>}

          <button type="submit" className="btn btn-primary auth-submit" disabled={loading}>
            {loading ? (
              <span className="spin" style={{ display: 'inline-flex' }}><Activity size={16} /></span>
            ) : (
              <>
                {mode === 'login' ? 'Login' : 'Create Account'}
                <ArrowRight size={16} />
              </>
            )}
          </button>
        </form>

        <p className="auth-footer">
          {mode === 'login' ? "Don't have an account? " : 'Already have an account? '}
          <button
            className="auth-switch"
            onClick={() => { setMode(mode === 'login' ? 'signup' : 'login'); setError(''); }}
          >
            {mode === 'login' ? 'Sign up' : 'Login'}
          </button>
        </p>
      </div>
    </div>
  );
}
