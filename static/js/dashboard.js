/* =========================================================================
   SUNLIGHT Dashboard — Client Logic
   ========================================================================= */

const API = '';  // Same origin
let systemData = {};
let triageData = [];
let expandedRow = null;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt(n) {
    if (n == null) return '—';
    if (n >= 1e9) return '$' + (n / 1e9).toFixed(1) + 'B';
    if (n >= 1e6) return '$' + (n / 1e6).toFixed(1) + 'M';
    if (n >= 1e3) return '$' + (n / 1e3).toFixed(0) + 'K';
    return '$' + n.toLocaleString();
}

function fmtNum(n) {
    if (n == null) return '—';
    return n.toLocaleString();
}

function fmtPct(n) {
    if (n == null) return '—';
    return n.toFixed(1) + '%';
}

function tierClass(tier) {
    return { RED: 'red', YELLOW: 'yellow', GREEN: 'green', GRAY: 'gray' }[tier] || 'gray';
}

function confColor(score) {
    if (score >= 70) return 'red';
    if (score >= 40) return 'amber';
    return 'green';
}

async function apiFetch(path) {
    const resp = await fetch(API + path);
    if (!resp.ok) throw new Error(`API ${resp.status}: ${path}`);
    return resp.json();
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', async () => {
    try {
        await Promise.all([
            loadHealth(),
            loadKPIs(),
            loadRiskDistribution(),
            loadDetectionFeed(),
            loadVendorRisk(),
            loadAgencyExposure(),
            loadSystemHealth(),
        ]);
        setupUpload();
    } catch (err) {
        console.error('Dashboard init error:', err);
    }
});

// ---------------------------------------------------------------------------
// Top Bar — Health
// ---------------------------------------------------------------------------

async function loadHealth() {
    try {
        const data = await apiFetch('/dashboard/api/health');
        systemData = data;
        document.getElementById('status-dot').className = 'status-dot';
        document.getElementById('status-text').textContent = 'Operational';
        document.getElementById('topbar-contracts').textContent = fmtNum(data.contract_count);
        document.getElementById('topbar-scored').textContent = fmtNum(data.scored_count);

        const now = new Date();
        document.getElementById('topbar-time').textContent =
            now.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' ' +
            now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    } catch (e) {
        document.getElementById('status-dot').className = 'status-dot offline';
        document.getElementById('status-text').textContent = 'Offline';
    }
}

// ---------------------------------------------------------------------------
// KPIs
// ---------------------------------------------------------------------------

async function loadKPIs() {
    const [health, triage, scores] = await Promise.all([
        apiFetch('/dashboard/api/health'),
        apiFetch('/dashboard/api/triage?limit=500'),
        apiFetch('/dashboard/api/scores?limit=1'),
    ]);

    const flagged = triage.total || 0;
    const total = health.contract_count || 0;
    const detectionRate = total > 0 ? (flagged / total * 100) : 0;

    // Compute total procurement value and avg risk score from triage items
    let totalValue = 0;
    let totalConfidence = 0;
    let confCount = 0;
    for (const item of (triage.items || [])) {
        totalValue += item.award_amount || 0;
        totalConfidence += item.confidence_score || 0;
        confCount++;
    }
    const avgRisk = confCount > 0 ? Math.round(totalConfidence / confCount) : 0;

    // Get total procurement value from all contracts
    const allContracts = await apiFetch('/dashboard/api/contracts?limit=1');
    // We'll estimate total value from the triage endpoint or health data
    // For now use the flagged value as "flagged exposure"

    setKPI('kpi-total', fmtNum(total));
    setKPI('kpi-flagged', fmtNum(flagged), flagged > 0 ? 'red' : 'green');
    setKPI('kpi-rate', fmtPct(detectionRate), detectionRate > 15 ? 'amber' : 'green');
    setKPI('kpi-risk', avgRisk.toString(), avgRisk >= 70 ? 'red' : avgRisk >= 40 ? 'amber' : 'green');
    setKPI('kpi-exposure', fmt(totalValue), 'amber');
}

function setKPI(id, value, colorClass) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = value;
    el.className = 'kpi-value fade-in' + (colorClass ? ' ' + colorClass : '');
}

// ---------------------------------------------------------------------------
// Risk Distribution Donut
// ---------------------------------------------------------------------------

async function loadRiskDistribution() {
    const data = await apiFetch('/dashboard/api/triage?limit=500');
    const allScores = await apiFetch('/dashboard/api/scores?limit=500');

    // Count tiers from scores
    const tiers = { RED: 0, YELLOW: 0, GREEN: 0, GRAY: 0 };
    const tierValues = { RED: 0, YELLOW: 0, GREEN: 0, GRAY: 0 };

    for (const item of (allScores.items || [])) {
        const t = item.fraud_tier || 'GREEN';
        tiers[t] = (tiers[t] || 0) + 1;
    }

    // Get dollar values from triage (which has award_amount)
    for (const item of (data.items || [])) {
        const t = item.fraud_tier || 'YELLOW';
        tierValues[t] = (tierValues[t] || 0) + (item.award_amount || 0);
    }

    const total = Object.values(tiers).reduce((a, b) => a + b, 0);

    // Update legend
    updateLegend('legend-red', tiers.RED, tierValues.RED);
    updateLegend('legend-yellow', tiers.YELLOW, tierValues.YELLOW);
    updateLegend('legend-green', tiers.GREEN, tierValues.GREEN);
    updateLegend('legend-gray', tiers.GRAY, tierValues.GRAY);

    document.getElementById('donut-total').textContent = fmtNum(total);

    // Render donut
    const ctx = document.getElementById('donut-chart').getContext('2d');
    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['RED', 'YELLOW', 'GREEN', 'GRAY'],
            datasets: [{
                data: [tiers.RED, tiers.YELLOW, tiers.GREEN, tiers.GRAY],
                backgroundColor: ['#ef4444', '#f59e0b', '#10b981', '#6b7280'],
                borderWidth: 0,
                hoverBorderWidth: 2,
                hoverBorderColor: '#e8edf5',
            }],
        },
        options: {
            cutout: '72%',
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#1a2236',
                    titleColor: '#e8edf5',
                    bodyColor: '#8899b4',
                    borderColor: '#2a3654',
                    borderWidth: 1,
                    padding: 12,
                    cornerRadius: 8,
                    callbacks: {
                        label: (ctx) => {
                            const pct = total > 0 ? (ctx.raw / total * 100).toFixed(1) : '0';
                            return ` ${ctx.label}: ${ctx.raw} contracts (${pct}%)`;
                        }
                    }
                }
            },
            animation: { animateRotate: true, duration: 800 },
        }
    });
}

function updateLegend(id, count, value) {
    const el = document.getElementById(id);
    if (!el) return;
    el.querySelector('.legend-count').textContent = fmtNum(count);
    el.querySelector('.legend-amount').textContent = value > 0 ? fmt(value) : '—';
}

// ---------------------------------------------------------------------------
// Detection Feed
// ---------------------------------------------------------------------------

async function loadDetectionFeed() {
    const data = await apiFetch('/dashboard/api/triage?limit=100');
    triageData = data.items || [];

    const tbody = document.getElementById('detection-tbody');
    tbody.innerHTML = '';

    if (triageData.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="empty-state"><div class="icon">&#9711;</div><div class="message">No flagged contracts detected</div></td></tr>`;
        return;
    }

    for (const item of triageData) {
        const tr = document.createElement('tr');
        tr.dataset.contractId = item.contract_id;
        tr.onclick = () => toggleExpand(item.contract_id);

        const tc = tierClass(item.fraud_tier);
        const cc = confColor(item.confidence_score);

        tr.innerHTML = `
            <td class="contract-id">${esc(item.contract_id)}</td>
            <td>${esc(truncate(item.vendor_name, 30))}</td>
            <td>${esc(truncate(item.agency_name, 28))}</td>
            <td><span class="tier-badge ${tc}">${item.fraud_tier}</span></td>
            <td>
                <div class="conf-bar-wrap">
                    <div class="conf-bar"><div class="conf-bar-fill ${cc}" style="width:${item.confidence_score}%"></div></div>
                    <span class="conf-value">${item.confidence_score}</span>
                </div>
            </td>
            <td>${fmtPct(item.markup_pct)}</td>
            <td style="text-align:right">${fmt(item.award_amount)}</td>
        `;
        tbody.appendChild(tr);
    }

    document.getElementById('detection-count').textContent = data.total;
}

async function toggleExpand(contractId) {
    const tbody = document.getElementById('detection-tbody');

    // Close existing
    const existing = tbody.querySelector('.expanded-row');
    if (existing) {
        const prevId = existing.dataset.contractId;
        existing.remove();
        if (prevId === contractId) { expandedRow = null; return; }
    }

    expandedRow = contractId;

    // Fetch detection report
    try {
        const report = await apiFetch(`/dashboard/api/report/${contractId}`);

        const targetRow = tbody.querySelector(`tr[data-contract-id="${contractId}"]`);
        if (!targetRow) return;

        const expandTr = document.createElement('tr');
        expandTr.className = 'expanded-row';
        expandTr.dataset.contractId = contractId;

        const assessment = report.assessment || {};
        const evidence = report.evidence || {};
        const price = evidence.price_analysis || {};
        const bayesian = evidence.bayesian_analysis || {};
        const recs = report.recommendations || {};
        const reasoning = report.reasoning || [];
        const legal = report.legal_framework || [];

        expandTr.innerHTML = `
            <td colspan="7">
                <div class="expanded-content">
                    <h4>${esc(assessment.risk_label || contractId)}</h4>
                    <div class="evidence-grid">
                        <div class="evidence-item">
                            <div class="label">Markup</div>
                            <div class="value ${tierClass(report.assessment?.risk_level)}">${fmtPct(price.markup_pct)}</div>
                        </div>
                        <div class="evidence-item">
                            <div class="label">95% CI Lower</div>
                            <div class="value">${fmtPct(price.confidence_interval?.lower)}</div>
                        </div>
                        <div class="evidence-item">
                            <div class="label">Bayesian Posterior</div>
                            <div class="value">${bayesian.posterior_probability != null ? (bayesian.posterior_probability * 100).toFixed(1) + '%' : '—'}</div>
                        </div>
                        <div class="evidence-item">
                            <div class="label">Comparables</div>
                            <div class="value">${price.sample_size || '—'}</div>
                        </div>
                    </div>
                    ${reasoning.length > 0 ? `
                    <h4>Reasoning</h4>
                    <ul class="reasoning-list">
                        ${reasoning.map(r => `<li>${esc(r)}</li>`).join('')}
                    </ul>` : ''}
                    ${(recs.next_steps || []).length > 0 ? `
                    <h4 style="margin-top:var(--space-md)">Recommended Actions</h4>
                    <ul class="reasoning-list">
                        ${(recs.next_steps || []).map(s => `<li>${esc(s)}</li>`).join('')}
                    </ul>` : ''}
                    ${legal.length > 0 ? `
                    <div style="margin-top:var(--space-md);font-size:0.72rem;color:var(--text-muted)">
                        Legal: ${legal.map(l => esc(typeof l === 'string' ? l : l.statute || '')).join(' | ')}
                    </div>` : ''}
                </div>
            </td>
        `;

        targetRow.after(expandTr);
    } catch (e) {
        console.error('Failed to load report:', e);
    }
}

// ---------------------------------------------------------------------------
// Vendor Risk
// ---------------------------------------------------------------------------

async function loadVendorRisk() {
    const data = await apiFetch('/dashboard/api/triage?limit=500');
    const items = data.items || [];

    // Aggregate by vendor
    const vendors = {};
    for (const item of items) {
        const v = item.vendor_name;
        if (!vendors[v]) vendors[v] = { count: 0, totalConf: 0, totalAmount: 0, maxConf: 0 };
        vendors[v].count++;
        vendors[v].totalConf += item.confidence_score || 0;
        vendors[v].totalAmount += item.award_amount || 0;
        vendors[v].maxConf = Math.max(vendors[v].maxConf, item.confidence_score || 0);
    }

    // Sort by count * avg confidence
    const sorted = Object.entries(vendors)
        .map(([name, d]) => ({ name, ...d, avgConf: d.count > 0 ? d.totalConf / d.count : 0 }))
        .sort((a, b) => (b.count * b.avgConf) - (a.count * a.avgConf))
        .slice(0, 20);

    const container = document.getElementById('vendor-risk-list');
    container.innerHTML = '';

    if (sorted.length === 0) {
        container.innerHTML = '<div class="empty-state"><div class="message">No vendor risk data</div></div>';
        return;
    }

    const maxScore = Math.max(...sorted.map(v => v.count * v.avgConf));

    sorted.forEach((v, i) => {
        const barPct = maxScore > 0 ? (v.count * v.avgConf / maxScore * 100) : 0;
        const barClass = v.maxConf >= 70 ? '' : 'amber';

        const div = document.createElement('div');
        div.className = 'rank-item fade-in';
        div.style.animationDelay = (i * 30) + 'ms';
        div.innerHTML = `
            <span class="rank-num">${i + 1}</span>
            <span class="rank-name" title="${esc(v.name)}">${esc(truncate(v.name, 32))}</span>
            <div class="rank-bar-wrap">
                <div class="rank-bar"><div class="rank-bar-fill ${barClass}" style="width:${barPct}%"></div></div>
            </div>
            <span class="rank-value">${v.count} flag${v.count !== 1 ? 's' : ''}</span>
        `;
        container.appendChild(div);
    });
}

// ---------------------------------------------------------------------------
// Agency Exposure
// ---------------------------------------------------------------------------

async function loadAgencyExposure() {
    const data = await apiFetch('/dashboard/api/triage?limit=500');
    const items = data.items || [];

    // Aggregate by agency
    const agencies = {};
    for (const item of items) {
        const a = item.agency_name;
        if (!agencies[a]) agencies[a] = { count: 0, totalAmount: 0 };
        agencies[a].count++;
        agencies[a].totalAmount += item.award_amount || 0;
    }

    const sorted = Object.entries(agencies)
        .map(([name, d]) => ({ name, ...d }))
        .sort((a, b) => b.totalAmount - a.totalAmount);

    const container = document.getElementById('agency-exposure-list');
    container.innerHTML = '';

    if (sorted.length === 0) {
        container.innerHTML = '<div class="empty-state"><div class="message">No agency exposure data</div></div>';
        return;
    }

    const maxAmount = Math.max(...sorted.map(a => a.totalAmount));

    sorted.forEach((a, i) => {
        const barPct = maxAmount > 0 ? (a.totalAmount / maxAmount * 100) : 0;
        const div = document.createElement('div');
        div.className = 'rank-item fade-in';
        div.style.animationDelay = (i * 40) + 'ms';
        div.innerHTML = `
            <span class="rank-num">${i + 1}</span>
            <span class="rank-name" title="${esc(a.name)}">${esc(truncate(a.name, 32))}</span>
            <div class="rank-bar-wrap">
                <div class="rank-bar"><div class="rank-bar-fill amber" style="width:${barPct}%"></div></div>
            </div>
            <span class="rank-value">${fmt(a.totalAmount)}</span>
        `;
        container.appendChild(div);
    });
}

// ---------------------------------------------------------------------------
// Contract Upload
// ---------------------------------------------------------------------------

function setupUpload() {
    const zone = document.getElementById('upload-zone');
    const fileInput = document.getElementById('upload-input');
    if (!zone || !fileInput) return;

    zone.addEventListener('click', () => fileInput.click());

    zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('dragover');
    });

    zone.addEventListener('dragleave', () => {
        zone.classList.remove('dragover');
    });

    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            uploadFile(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            uploadFile(fileInput.files[0]);
        }
    });
}

async function uploadFile(file) {
    const zone = document.getElementById('upload-zone');
    const progress = document.getElementById('upload-progress');
    const progressFill = document.getElementById('progress-fill');
    const statusText = document.getElementById('upload-status-text');
    const resultDiv = document.getElementById('upload-result');

    zone.className = 'upload-zone processing';
    progress.className = 'upload-progress visible';
    progressFill.className = 'progress-bar-fill processing';
    progressFill.style.width = '30%';
    statusText.textContent = `Uploading ${file.name}...`;
    resultDiv.className = 'upload-result';

    try {
        const formData = new FormData();
        formData.append('file', file);

        const resp = await fetch(API + '/dashboard/api/ingest', { method: 'POST', body: formData });
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || 'Upload failed');
        }

        const data = await resp.json();
        progressFill.style.width = '60%';
        statusText.textContent = `Processing ${file.name}...`;

        // Poll for completion
        const jobId = data.job_id;
        let attempts = 0;
        while (attempts < 60) {
            await new Promise(r => setTimeout(r, 1000));
            attempts++;

            const status = await apiFetch(`/dashboard/api/ingest/${jobId}`);
            if (status.status === 'COMPLETED') {
                progressFill.style.width = '100%';
                progressFill.className = 'progress-bar-fill';
                progressFill.style.background = 'var(--green)';
                statusText.textContent = 'Processing complete';
                zone.className = 'upload-zone success';

                resultDiv.className = 'upload-result visible';
                resultDiv.innerHTML = `
                    <strong style="color:var(--green)">Ingestion Complete</strong><br>
                    Records: ${status.total_records} | Inserted: ${status.inserted} | Duplicates: ${status.duplicates} | Scored: ${status.scored}
                `;

                // Reload dashboard data
                setTimeout(() => {
                    loadHealth();
                    loadKPIs();
                    loadRiskDistribution();
                    loadDetectionFeed();
                    loadVendorRisk();
                    loadAgencyExposure();
                }, 500);
                return;
            } else if (status.status === 'FAILED') {
                throw new Error(status.error_details || 'Ingestion failed');
            }

            progressFill.style.width = (60 + attempts * 0.5) + '%';
        }

        throw new Error('Timeout waiting for processing');
    } catch (err) {
        zone.className = 'upload-zone error';
        progressFill.style.width = '100%';
        progressFill.style.background = 'var(--red)';
        statusText.textContent = 'Error: ' + err.message;
        resultDiv.className = 'upload-result visible';
        resultDiv.innerHTML = `<strong style="color:var(--red)">Failed</strong>: ${esc(err.message)}`;
    }
}

// ---------------------------------------------------------------------------
// System Health
// ---------------------------------------------------------------------------

async function loadSystemHealth() {
    try {
        const data = await apiFetch('/dashboard/api/health');

        setHealth('health-status', data.audit_chain_valid ? 'Verified' : 'BROKEN');
        setHealth('health-version', 'v' + (data.version || '—'));
        setHealth('health-db', data.database || '—');
        setHealth('health-contracts', fmtNum(data.contract_count));
    } catch (e) {
        setHealth('health-status', 'Unavailable');
    }
}

function setHealth(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function truncate(str, max) {
    if (!str) return '';
    return str.length > max ? str.substring(0, max - 1) + '\u2026' : str;
}
