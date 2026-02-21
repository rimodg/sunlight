import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLeads, useUpdateDisposition } from '../hooks/useApi';
import { fmt, fmtPct, tierClass, confColor } from '../utils/formatters';
import EvidenceItem from '../components/EvidenceItem';

export default function RiskInbox() {
  const { data, loading, error, refetch } = useLeads();
  const { updateDisposition, loading: dispositionLoading } = useUpdateDisposition();
  const [expandedId, setExpandedId] = useState(null);
  const [notes, setNotes] = useState('');
  const navigate = useNavigate();

  if (loading) return <div className="loading-container">Loading risk inbox...</div>;
  if (error) return <div className="loading-container error-msg">Error: {error}</div>;

  const items = data?.items || [];
  const workload = data?.workload || {};

  const handleDisposition = async (contractId, disposition) => {
    try {
      await updateDisposition({ contract_id: contractId, disposition, notes });
      setNotes('');
      setExpandedId(null);
      refetch();
    } catch {
      // error is captured in hook
    }
  };

  return (
    <div className="fade-in">
      <div className="section-header">
        <span className="section-title">Risk Inbox</span>
        <span className="section-badge">{data?.count || 0} flagged</span>
      </div>

      {workload.flags_per_1k != null && (
        <div className="kpi-grid" style={{ marginBottom: 'var(--space-xl)' }}>
          <div className="kpi-card red">
            <div className="kpi-label">Flags / 1K Contracts</div>
            <div className="kpi-value red">{workload.flags_per_1k}</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">Total Flagged</div>
            <div className="kpi-value">{workload.total_flagged}</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">Total Scored</div>
            <div className="kpi-value">{workload.total_scored}</div>
          </div>
          <div className="kpi-card amber">
            <div className="kpi-label">Est. Analyst Minutes</div>
            <div className="kpi-value amber">{workload.estimated_analyst_minutes}</div>
          </div>
        </div>
      )}

      <div className="card">
        <div className="detection-table-wrap">
          <table className="detection-table">
            <thead>
              <tr>
                <th>Contract ID</th>
                <th>Vendor</th>
                <th>Agency</th>
                <th>Tier</th>
                <th>Confidence</th>
                <th>Markup</th>
                <th style={{ textAlign: 'right' }}>Award</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan="7" className="empty-state">
                    <div className="icon">&#9711;</div>
                    <div className="message">No flagged contracts detected</div>
                  </td>
                </tr>
              ) : (
                items.map((item) => {
                  const tc = tierClass(item.fraud_tier || item.tier);
                  const cc = confColor(item.confidence_score);
                  const isExpanded = expandedId === item.contract_id;

                  return (
                    <RowGroup key={item.contract_id}>
                      <tr
                        onClick={() => setExpandedId(isExpanded ? null : item.contract_id)}
                        style={{ cursor: 'pointer' }}
                      >
                        <td className="contract-id">{item.contract_id}</td>
                        <td>{item.vendor_name}</td>
                        <td>{item.agency_name}</td>
                        <td><span className={`tier-badge ${tc}`}>{item.fraud_tier || item.tier}</span></td>
                        <td>
                          <div className="conf-bar-wrap">
                            <div className="conf-bar">
                              <div className={`conf-bar-fill ${cc}`} style={{ width: `${item.confidence_score}%` }} />
                            </div>
                            <span className="conf-value">{item.confidence_score}</span>
                          </div>
                        </td>
                        <td>{fmtPct(item.markup_pct)}</td>
                        <td style={{ textAlign: 'right' }}>{fmt(item.award_amount)}</td>
                      </tr>
                      {isExpanded && (
                        <tr className="expanded-row">
                          <td colSpan="7">
                            <div className="expanded-content">
                              <h4>{item.contract_id} — {item.vendor_name}</h4>
                              <div className="evidence-grid">
                                <EvidenceItem label="Markup" value={fmtPct(item.markup_pct)} colorClass={tc} />
                                <EvidenceItem label="Confidence" value={item.confidence_score} colorClass={cc} />
                                <EvidenceItem label="Award Value" value={fmt(item.award_amount)} />
                                <EvidenceItem label="NAICS" value={item.naics_code || '\u2014'} />
                              </div>

                              {item.reasoning?.length > 0 && (
                                <>
                                  <h4>Reasoning</h4>
                                  <ul className="reasoning-list">
                                    {item.reasoning.map((r, i) => <li key={i}>{r}</li>)}
                                  </ul>
                                </>
                              )}

                              {item.legal_framework?.length > 0 && (
                                <div style={{ marginTop: 'var(--space-md)', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                                  Legal: {item.legal_framework.join(' | ')}
                                </div>
                              )}

                              <textarea
                                className="notes-input"
                                placeholder="Analyst notes (optional)..."
                                value={notes}
                                onChange={(e) => setNotes(e.target.value)}
                              />

                              <div className="disposition-bar">
                                <button
                                  className="disposition-btn confirmed"
                                  disabled={dispositionLoading}
                                  onClick={(e) => { e.stopPropagation(); handleDisposition(item.contract_id, 'confirmed_fraud'); }}
                                >
                                  Confirmed Fraud
                                </button>
                                <button
                                  className="disposition-btn false-positive"
                                  disabled={dispositionLoading}
                                  onClick={(e) => { e.stopPropagation(); handleDisposition(item.contract_id, 'false_positive'); }}
                                >
                                  False Positive
                                </button>
                                <button
                                  className="disposition-btn needs-review"
                                  disabled={dispositionLoading}
                                  onClick={(e) => { e.stopPropagation(); handleDisposition(item.contract_id, 'needs_review'); }}
                                >
                                  Needs Review
                                </button>
                                <button
                                  className="disposition-btn"
                                  disabled={dispositionLoading}
                                  onClick={(e) => { e.stopPropagation(); handleDisposition(item.contract_id, 'dismissed'); }}
                                >
                                  Dismiss
                                </button>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </RowGroup>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function RowGroup({ children }) {
  return <>{children}</>;
}
