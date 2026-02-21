import { NavLink, Outlet } from 'react-router-dom';
import { useApp } from '../context/AppContext';

export default function Layout() {
  const { isAdmin, isDemoMode, logout, tenantId } = useApp();

  return (
    <>
      <header className="topbar">
        <div className="topbar-brand">
          <div className="topbar-wordmark">SUN<span>LIGHT</span></div>
          <div className="topbar-divider" />
          <div className="topbar-subtitle">Procurement Fraud Detection</div>
        </div>
        <div className="topbar-stats">
          {isDemoMode && (
            <div className="topbar-stat">
              <span className="tier-badge yellow" style={{ fontSize: '0.65rem' }}>DEMO</span>
            </div>
          )}
          <div className="topbar-stat">
            <div className="status-dot" />
            <span>Operational</span>
          </div>
          {tenantId && (
            <div className="topbar-stat">
              Tenant: <strong>{tenantId}</strong>
            </div>
          )}
          <button
            onClick={logout}
            style={{
              background: 'none',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--text-secondary)',
              padding: '2px 10px',
              fontSize: '0.72rem',
              cursor: 'pointer',
            }}
          >
            Logout
          </button>
        </div>
      </header>

      <div className="app-layout">
        <nav className="sidebar">
          <div className="sidebar-section-label">Analysis</div>
          <div className="sidebar-nav">
            <NavLink to="/" end className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
              <span className="icon">&#9888;</span> Risk Inbox
            </NavLink>
            <NavLink to="/portfolio" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
              <span className="icon">&#9679;</span> Portfolio
            </NavLink>
          </div>

          <div className="sidebar-section-label" style={{ marginTop: 'var(--space-md)' }}>Setup</div>
          <div className="sidebar-nav">
            <NavLink to="/onboarding" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
              <span className="icon">&#9745;</span> Onboarding
            </NavLink>
            {isAdmin && (
              <NavLink to="/admin" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
                <span className="icon">&#9881;</span> Admin
              </NavLink>
            )}
          </div>
        </nav>

        <main className="main-content">
          <Outlet />
        </main>
      </div>

      <footer className="footer" style={{ marginLeft: 220 }}>
        <div className="footer-text">
          SUNLIGHT v2.0.0 &mdash; <span>Statistical anomaly detection for government procurement</span>
          &middot; All findings are risk indicators, not allegations of fraud
        </div>
      </footer>
    </>
  );
}
