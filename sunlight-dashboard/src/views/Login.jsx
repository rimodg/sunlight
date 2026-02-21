import { useState } from 'react';
import { useApp } from '../context/AppContext';

export default function Login() {
  const { login, isDemoMode } = useApp();
  const [apiKey, setApiKey] = useState('');
  const [tenantId, setTenantId] = useState('');
  const [role, setRole] = useState('analyst');
  const [error, setError] = useState('');

  // Demo mode auto-redirects via isAuthenticated
  if (isDemoMode) {
    return null;
  }

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!apiKey.trim() || !tenantId.trim()) {
      setError('API Key and Tenant ID are required');
      return;
    }
    login(apiKey.trim(), tenantId.trim(), role);
  };

  return (
    <div className="login-container">
      <div className="login-card">
        <div style={{ textAlign: 'center', marginBottom: 'var(--space-lg)' }}>
          <div className="topbar-wordmark" style={{ fontSize: '1.5rem', marginBottom: 'var(--space-xs)' }}>
            SUN<span>LIGHT</span>
          </div>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            Procurement Fraud Detection
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">API Key</label>
            <input
              className="form-input"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-..."
              autoFocus
            />
          </div>

          <div className="form-group">
            <label className="form-label">Tenant ID</label>
            <input
              className="form-input"
              type="text"
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
              placeholder="your-tenant-id"
            />
          </div>

          <div className="form-group">
            <label className="form-label">Role</label>
            <select
              className="form-input"
              value={role}
              onChange={(e) => setRole(e.target.value)}
              style={{ fontFamily: 'var(--font-sans)' }}
            >
              <option value="analyst">Analyst</option>
              <option value="admin">Admin</option>
            </select>
          </div>

          {error && <div className="error-msg">{error}</div>}

          <button type="submit" className="btn-primary" style={{ marginTop: 'var(--space-md)' }}>
            Sign In
          </button>
        </form>

        <div style={{ marginTop: 'var(--space-lg)', textAlign: 'center', fontSize: '0.72rem', color: 'var(--text-dim)' }}>
          Add <code style={{ color: 'var(--accent)' }}>?demo=true</code> to URL for demo mode
        </div>
      </div>
    </div>
  );
}
