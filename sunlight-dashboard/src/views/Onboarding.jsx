import { useOnboardingStatus } from '../hooks/useApi';

const STEP_DEFINITIONS = [
  { key: 'tenant_created', title: 'Create Tenant', desc: 'Register your organization and get API credentials' },
  { key: 'webhook_configured', title: 'Configure Webhook', desc: 'Set up real-time notifications for new detections' },
  { key: 'data_ingested', title: 'Upload Data', desc: 'Ingest your first batch of procurement contracts' },
  { key: 'first_scan_complete', title: 'Run First Scan', desc: 'Execute the fraud detection pipeline on your data' },
  { key: 'risk_inbox_available', title: 'Review Risk Inbox', desc: 'Examine flagged contracts and evidence packages' },
  { key: 'dispositions_set', title: 'Set Dispositions', desc: 'Triage findings as confirmed, false positive, or needs review' },
  { key: 'go_live', title: 'Go Live', desc: 'Enable continuous monitoring and automated scanning' },
];

export default function Onboarding() {
  const { data, loading, error } = useOnboardingStatus();

  if (loading) return <div className="loading-container">Loading onboarding status...</div>;
  if (error) return <div className="loading-container error-msg">Error: {error}</div>;

  const steps = data?.steps || {};
  const isComplete = data?.complete || false;
  const nextStep = data?.next_step;

  // Find the first incomplete step
  let firstIncompleteIdx = STEP_DEFINITIONS.findIndex((s) => !steps[s.key]);
  if (firstIncompleteIdx === -1) firstIncompleteIdx = STEP_DEFINITIONS.length;

  return (
    <div className="fade-in">
      <div className="section-header">
        <span className="section-title">Onboarding</span>
        <span className="section-badge">
          {isComplete ? 'Complete' : `Step ${firstIncompleteIdx + 1} of ${STEP_DEFINITIONS.length}`}
        </span>
      </div>

      {/* Progress bar */}
      <div className="card" style={{ marginBottom: 'var(--space-xl)' }}>
        <div className="progress-bar" style={{ height: '6px', marginBottom: 'var(--space-md)' }}>
          <div
            className="progress-bar-fill"
            style={{
              width: `${(firstIncompleteIdx / STEP_DEFINITIONS.length) * 100}%`,
              background: isComplete ? 'var(--green)' : 'var(--accent)',
            }}
          />
        </div>
        <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
          {isComplete
            ? 'All onboarding steps complete. SUNLIGHT is fully operational.'
            : `${firstIncompleteIdx} of ${STEP_DEFINITIONS.length} steps completed`}
        </div>
      </div>

      <div className="onboarding-steps">
        {STEP_DEFINITIONS.map((step, i) => {
          const done = steps[step.key];
          const isCurrent = i === firstIncompleteIdx;
          const className = `onboarding-step ${done ? 'complete' : isCurrent ? 'current' : ''}`;

          return (
            <div className={className} key={step.key}>
              <div className="step-number">
                {done ? '\u2713' : i + 1}
              </div>
              <div className="step-info">
                <div className="step-title">{step.title}</div>
                <div className="step-desc">{step.desc}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
