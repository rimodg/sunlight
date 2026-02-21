import { usePortfolioStats } from '../hooks/useApi';
import { fmt, fmtNum, tierClass } from '../utils/formatters';

export default function Portfolio() {
  const { data, loading, error } = usePortfolioStats();

  if (loading) return <div className="loading-container">Loading portfolio...</div>;
  if (error) return <div className="loading-container error-msg">Error: {error}</div>;

  const tiers = data?.tiers || {};
  const totalContracts = data?.total_contracts || 0;
  const vendors = data?.top_flagged_vendors || [];
  const agencies = data?.top_flagged_agencies || [];

  // Calculate donut segments
  const red = tiers.RED?.count || 0;
  const yellow = tiers.YELLOW?.count || 0;
  const green = tiers.GREEN?.count || 0;
  const total = red + yellow + green || 1;

  const redPct = (red / total) * 100;
  const yellowPct = (yellow / total) * 100;
  const greenPct = (green / total) * 100;

  // CSS conic-gradient donut
  const donutStyle = {
    background: `conic-gradient(
      var(--red) 0% ${redPct}%,
      var(--amber) ${redPct}% ${redPct + yellowPct}%,
      var(--green) ${redPct + yellowPct}% ${redPct + yellowPct + greenPct}%,
      var(--gray-tier) ${redPct + yellowPct + greenPct}% 100%
    )`,
  };

  return (
    <div className="fade-in">
      <div className="section-header">
        <span className="section-title">Portfolio Overview</span>
        <span className="section-badge">{fmtNum(totalContracts)} contracts</span>
      </div>

      {/* Risk Distribution */}
      <div className="card" style={{ marginBottom: 'var(--space-xl)' }}>
        <div className="section-header">
          <span className="section-title">Risk Distribution</span>
        </div>
        <div className="donut-container">
          <div className="donut-chart-wrap">
            <div className="css-donut" style={donutStyle} />
            <div className="donut-center-label">
              <span className="value">{fmtNum(totalContracts)}</span>
              <span className="label">contracts</span>
            </div>
          </div>
          <div className="donut-legend">
            <LegendItem
              color="red"
              name="RED"
              detail="Prosecution-grade"
              count={red}
              amount={tiers.RED?.total_value}
            />
            <LegendItem
              color="amber"
              name="YELLOW"
              detail="Investigation-worthy"
              count={yellow}
              amount={tiers.YELLOW?.total_value}
            />
            <LegendItem
              color="green"
              name="GREEN"
              detail="Normal pricing"
              count={green}
              amount={tiers.GREEN?.total_value}
            />
          </div>
        </div>
      </div>

      {/* Vendor + Agency rankings */}
      <div className="grid-2col">
        <div className="card">
          <div className="section-header">
            <span className="section-title">Top Flagged Vendors</span>
          </div>
          <div className="rank-list">
            {vendors.length === 0 ? (
              <div className="empty-state"><div className="message">No vendor data</div></div>
            ) : (
              vendors.map((v, i) => {
                const maxFlags = vendors[0]?.flag_count || 1;
                const barPct = (v.flag_count / maxFlags) * 100;
                const barClass = v.tier === 'RED' ? '' : 'amber';
                return (
                  <div className="rank-item fade-in" key={v.vendor_name} style={{ animationDelay: `${i * 30}ms` }}>
                    <span className="rank-num">{i + 1}</span>
                    <span className="rank-name" title={v.vendor_name}>{v.vendor_name}</span>
                    <div className="rank-bar-wrap">
                      <div className="rank-bar">
                        <div className={`rank-bar-fill ${barClass}`} style={{ width: `${barPct}%` }} />
                      </div>
                    </div>
                    <span className="rank-value">{v.flag_count} flag{v.flag_count !== 1 ? 's' : ''}</span>
                  </div>
                );
              })
            )}
          </div>
        </div>

        <div className="card">
          <div className="section-header">
            <span className="section-title">Agency Exposure</span>
          </div>
          <div className="rank-list">
            {agencies.length === 0 ? (
              <div className="empty-state"><div className="message">No agency data</div></div>
            ) : (
              agencies.map((a, i) => {
                const maxVal = agencies[0]?.total_value || 1;
                const barPct = (a.total_value / maxVal) * 100;
                return (
                  <div className="rank-item fade-in" key={a.agency_name} style={{ animationDelay: `${i * 40}ms` }}>
                    <span className="rank-num">{i + 1}</span>
                    <span className="rank-name" title={a.agency_name}>{a.agency_name}</span>
                    <div className="rank-bar-wrap">
                      <div className="rank-bar">
                        <div className="rank-bar-fill amber" style={{ width: `${barPct}%` }} />
                      </div>
                    </div>
                    <span className="rank-value">{fmt(a.total_value)}</span>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function LegendItem({ color, name, detail, count, amount }) {
  return (
    <div className="legend-item">
      <div className={`legend-dot ${color}`} />
      <div className="legend-text">
        <div className="tier-name">{name}</div>
        <div className="tier-detail">{detail}</div>
      </div>
      <span className="legend-count">{fmtNum(count)}</span>
      <span className="legend-amount">{amount ? fmt(amount) : '\u2014'}</span>
    </div>
  );
}
