import { useAdminConfig } from '../hooks/useApi';
import { useApp } from '../context/AppContext';
import { fmtNum } from '../utils/formatters';

export default function Admin() {
  const { isAdmin } = useApp();
  const { data, loading, error } = useAdminConfig();

  if (!isAdmin) {
    return (
      <div className="loading-container">
        <div className="empty-state">
          <div className="icon">&#128274;</div>
          <div className="message">Admin access required</div>
        </div>
      </div>
    );
  }

  if (loading) return <div className="loading-container">Loading admin config...</div>;
  if (error) return <div className="loading-container error-msg">Error: {error}</div>;

  const tenants = data?.tenants || [];

  return (
    <div className="fade-in">
      <div className="section-header">
        <span className="section-title">Tenant Administration</span>
        <span className="section-badge">{tenants.length} tenant{tenants.length !== 1 ? 's' : ''}</span>
      </div>

      <div className="card">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Tenant ID</th>
              <th>Name</th>
              <th>Plan</th>
              <th>Contracts</th>
              <th>Webhook</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {tenants.map((t) => (
              <tr key={t.tenant_id}>
                <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>{t.tenant_id}</td>
                <td style={{ color: 'var(--text-primary)' }}>{t.name}</td>
                <td>
                  <span className="tier-badge green" style={{ textTransform: 'capitalize' }}>{t.plan}</span>
                </td>
                <td>{fmtNum(t.contract_count)}</td>
                <td>
                  {t.webhook_active ? (
                    <span style={{ color: 'var(--green)' }}>Active</span>
                  ) : (
                    <span style={{ color: 'var(--text-muted)' }}>Inactive</span>
                  )}
                  {t.webhook_url && (
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                      {t.webhook_url}
                    </div>
                  )}
                </td>
                <td>{new Date(t.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
