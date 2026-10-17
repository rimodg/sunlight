import { useEffect, useState } from 'react';
import './EvidenceWorkspace.css';
import EvidenceGlobe from './EvidenceGlobe';
import { investigationRecords } from './evidenceGeography';

const specimens = {
  open: { label: 'Documented open procedure', method: 'open', amount: 1000000 },
  direct: { label: 'Direct award above threshold', method: 'direct', amount: 1000000 },
  thin: { label: 'Sparse record', thin: true },
};

function specimen(key, currency) {
  if (specimens[key].thin) return { ocid: 'synthetic-sparse-001' };
  const { method, amount } = specimens[key];
  return {
    ocid: `synthetic-${key}-001`,
    buyer: { name: 'Illustrative public authority', id: 'EXAMPLE-BUYER' },
    tender: { id: 'EXAMPLE-TENDER', title: 'Illustrative medical supply contract',
      deliveryLocations: [{ description: 'Fictional example delivery site / Washington, DC', geometry: { type: 'Point', coordinates: [-77.04, 38.9] } }],
      procurementMethod: method, numberOfTenderers: method === 'open' ? 5 : 1,
      value: { amount, currency },
      tenderPeriod: { startDate: '2025-01-01T00:00:00Z', endDate: '2025-02-01T00:00:00Z' } },
    awards: [{ id: 'EXAMPLE-AWARD', date: '2025-02-15T00:00:00Z',
      value: { amount, currency }, suppliers: [{ name: 'Illustrative supplier', id: 'EXAMPLE-SUPPLIER' }] }],
  };
}

async function getJSON(path, options, preserveText = false) {
  const response = await fetch(path, options);
  const text = await response.text();
  const body = JSON.parse(text);
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail || body));
  return preserveText ? { body, text } : body;
}

function download(value, name) {
  const url = URL.createObjectURL(new Blob([typeof value === 'string' ? value : JSON.stringify(value, null, 2)], { type: 'application/json' }));
  const link = document.createElement('a');
  link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// Preserve API number serialization: JSON.stringify would turn 1.0 into 1
// and can round large integers, invalidating canonical receipt hashes.
function packetText(run) {
  return `{"request":${JSON.stringify(run.request)},"input_origin":${JSON.stringify(run.input_origin)},"filename":${JSON.stringify(run.filename)},"response":${run.responseText}}`;
}

const title = value => String(value || 'Not assessed').replaceAll('_', ' ');

export default function EvidenceWorkspace() {
  const [tab, setTab] = useState('review');
  const [importOpen, setImportOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [profiles, setProfiles] = useState([]);
  const [profile, setProfile] = useState('us_federal');
  const [assurance, setAssurance] = useState(null);
  const [connection, setConnection] = useState('Connecting');
  const [input, setInput] = useState(JSON.stringify(specimen('direct', 'USD'), null, 2));
  const [origin, setOrigin] = useState('Synthetic example');
  const [budget, setBudget] = useState('');
  const [run, setRun] = useState(null);
  const [selected, setSelected] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [uploadName, setUploadName] = useState('');

  useEffect(() => {
    if (!importOpen) return;
    const previous = document.activeElement;
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    document.querySelector('.ev-close-import')?.focus();
    function trap(event) {
      if (event.key !== 'Tab') return;
      const controls = [...document.querySelectorAll('.ev-input button:not(:disabled), .ev-input select:not(:disabled), .ev-input textarea:not(:disabled), .ev-input input:not(:disabled)')].filter(el => el.getClientRects().length);
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
    document.addEventListener('keydown', trap);
    return () => { document.body.style.overflow = oldOverflow; document.removeEventListener('keydown', trap); previous?.focus(); };
  }, [importOpen]);

  useEffect(() => {
    let active = true;
    Promise.all([getJSON('/profiles'), getJSON('/assurance')]).then(([p, a]) => {
      if (!active) return;
      setProfiles(p.profiles); setAssurance(a); setConnection('API connected');
    }).catch(() => { if (active) setConnection('API unavailable'); });
    return () => { active = false; };
  }, []);

  function loadExample(key) {
    const currency = profiles.find(p => p.name === profile)?.currency || 'USD';
    setInput(JSON.stringify(specimen(key, currency), null, 2));
    setOrigin('Synthetic example'); setUploadName(''); setError(''); setRun(null);
  }

  async function upload(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) { setError('Choose a JSON file smaller than 2 MB.'); return; }
    try {
      const text = await file.text(); JSON.parse(text);
      setInput(text); setUploadName(file.name); setOrigin('User-supplied record'); setError(''); setRun(null);
    } catch { setError('The file is not valid JSON.'); }
    event.target.value = '';
  }

  async function analyze() {
    setError(''); setBusy(true); setRun(null);
    try {
      const payload = JSON.parse(input);
      const contracts = Array.isArray(payload) ? payload : payload.contracts;
      const isBatch = Array.isArray(contracts);
      const request = isBatch ? { contracts, profile, capacity_budget: budget === '' ? null : Number(budget) }
        : { contract: payload.contract || payload, profile };
      if (isBatch && contracts.length > 1000) throw new Error('A batch can contain at most 1,000 records.');
      const { body: response, text: responseText } = await getJSON(isBatch ? '/batch' : '/analyze', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request),
      }, true);
      setRun({ request, response, responseText, input_origin: origin, filename: uploadName || null }); setSelected(0); setImportOpen(false);
    } catch (e) { setError(e.message || 'Analysis could not complete.'); }
    finally { setBusy(false); }
  }

  const records = investigationRecords(run);
  const visibleRecords = records.filter(r => `${r.label} ${r.result.ocid}`.toLowerCase().includes(search.toLowerCase()) && (filter === 'all' || (filter === 'findings' ? r.findings > 0 : !r.location)));
  const results = run ? (run.response.results || [run.response]) : [];
  const result = results[selected];
  const findings = result?.structure?.contradictions || [];
  const scoring = result?.structural_scoring;
  const quality = result?.ingestion_quality;
  const metadata = run?.response.threshold_metadata;

  return <div className="evidence-app">
    <header className="ev-header">
      <a className="ev-brand" href={import.meta.env.BASE_URL} aria-label="SUNLIGHT home"><span className="ev-sun" />SUNLIGHT<span className="ev-edition">THE GLOBAL HUMANITARIAN WATCH</span></a>
      <span className={`ev-connection ${connection === 'API connected' ? 'connected' : ''}`}><i />{connection}</span>
    </header>
    <main className="ev-main">
      <nav className="ev-tabs" aria-label="Workspace sections">
        {[['review', 'Investigation'], ['method', 'Method & interpretation'], ['assurance', 'Capabilities & readiness']].map(([id, label]) => <button key={id} aria-pressed={tab === id} onClick={() => setTab(id)}>{label}</button>)}
        <button className="ev-import-button" onClick={() => { setTab('review'); setImportOpen(true); }}>+ Import evidence</button>
      </nav>

      {tab === 'review' && <>
        <div className="ev-workspace">
          <aside className="ev-queue" aria-label="Record queue">
            <div className="ev-queue-title"><span>RECORD REGISTER</span><strong>{records.length.toString().padStart(2, '0')}</strong></div>
            <div className="ev-session-stats"><div><strong>{records.reduce((n, r) => n + r.findings, 0)}</strong><span>Findings</span></div><div><strong>{records.filter(r => !r.location).length}</strong><span>Unlocated</span></div></div>
            <label htmlFor="record-search">Find a record</label><input id="record-search" type="search" placeholder="Title or identifier" value={search} onChange={e => setSearch(e.target.value)}/>
            <label htmlFor="queue-filter">Show</label><select id="queue-filter" value={filter} onChange={e => setFilter(e.target.value)}><option value="all">All records</option><option value="findings">With findings</option><option value="unlocated">Without coordinates</option></select>
            <div className="ev-queue-list">{visibleRecords.map(r => <button key={r.index} className={`ev-queue-record ${selected === r.index ? 'active' : ''}`} aria-pressed={selected === r.index} onClick={() => setSelected(r.index)}><span>{r.result.ocid}</span><strong>{r.label}</strong><small>{r.findings} findings · {r.location ? 'Located' : 'Unlocated'}{r.result.errors?.length ? ' · Analysis error' : ''}</small></button>)}</div>
            {!records.length && <div className="ev-queue-empty"><h2>Start with evidence.</h2><p>Import a record or examine a fictional example through the live engine.</p><button onClick={() => setImportOpen(true)}>Supply a record ↗</button></div>}
            {records.length > 0 && visibleRecords.length === 0 && <p className="ev-caption">No records match this filter.</p>}
            <div className="ev-register-note"><span>SESSION SCOPE</span><p>{run ? run.input_origin : 'No records analyzed'}. This register contains only this session’s analysis. Download packets to retain the evidence.</p></div>
          </aside>
          <EvidenceGlobe records={records} selected={selected} onSelect={setSelected}/>
          {importOpen && <div className="ev-import-overlay" onClick={e => { if (e.target === e.currentTarget) setImportOpen(false); }} onKeyDown={e => { if (e.key === 'Escape') setImportOpen(false); }}>
          <section className="ev-panel ev-input" role="dialog" aria-modal="true" aria-labelledby="ev-import-title">
            <button className="ev-close-import" onClick={() => setImportOpen(false)} aria-label="Close import">Close ×</button>
            <div className="ev-section-title"><span className="ev-step">01</span><h2 id="ev-import-title">Supply a record</h2></div>
            <p>OCDS-shaped JSON, one record or an array of up to 1,000. Examples are fictional inputs; every result comes from the live API.</p>
            <label htmlFor="jurisdiction">Jurisdiction calibration</label>
            <select id="jurisdiction" value={profile} disabled={busy} onChange={e => { setProfile(e.target.value); setRun(null); }}>
              {(profiles.length ? profiles : [{ name: 'us_federal' }]).map(p => <option key={p.name} value={p.name}>{title(p.name)}{p.currency ? ` / ${p.currency}` : ''}</option>)}
            </select>
            <p className="ev-caption">Amounts must match the selected profile currency. SUNLIGHT does not convert currencies.</p>
            <div className="ev-examples">{Object.entries(specimens).map(([key, s]) => <button key={key} disabled={busy} onClick={() => loadExample(key)}>{s.label}</button>)}</div>
            <div className="ev-editor-heading"><label htmlFor="record">Record JSON</label><label className="ev-upload">Open JSON<input type="file" accept="application/json,.json" disabled={busy} onChange={upload} /></label></div>
            <textarea id="record" spellCheck="false" value={input} disabled={busy} onChange={e => { setInput(e.target.value); setOrigin('Edited input; source not authenticated'); setRun(null); }} />
            <div className="ev-input-footer"><span>{origin}{uploadName ? ` / ${uploadName}` : ''}</span><label>Batch capacity<input aria-label="Batch investigation capacity" type="number" min="0" step="1" placeholder="No ceiling" value={budget} disabled={busy} onChange={e => { setBudget(e.target.value); setRun(null); }} /></label></div>
            <button className="ev-primary" disabled={busy || connection !== 'API connected'} onClick={analyze}>{busy ? 'Running analysis...' : 'Analyze supplied evidence'}<span aria-hidden="true">↗</span></button>
            <p className="ev-caption">Submitted records are sent to this deployment's API. Use public or synthetic data until institutional access and data-handling controls are established.</p>
            {error && <div className="ev-error" role="alert">{error}</div>}
          </section>

          </div>}
          <section className="ev-panel ev-results" aria-live="polite" aria-busy={busy}>
            <div className="ev-section-title"><span className="ev-step">EVIDENCE</span><h2>{run ? 'Record inspection' : 'Investigation desk'}</h2></div>
            {!run ? <div className="ev-empty"><span className="ev-empty-mark">◎</span><h3>{busy ? 'Analyzing evidence' : 'From record to review'}</h3><p>Select a record to follow its procedural facts, findings, and assessment limits.</p><ol className="ev-start-steps"><li><strong>Supply</strong> a procurement record.</li><li><strong>Examine</strong> the rules and their basis.</li><li><strong>Retain</strong> a reproducible evidence packet.</li></ol><button className="ev-primary" onClick={() => setImportOpen(true)}>Begin investigation ↗</button><span className="ev-caption">Geography provides context. Findings come from the record.</span></div> : <>
              <div className="ev-result-toolbar"><span className="ev-origin">{run.input_origin}</span><button onClick={() => download(packetText(run), 'sunlight-evidence-packet.json')}>Download evidence packet ↓</button></div>
              {metadata && <div className="ev-batch-summary"><strong>{run.response.total_processed} processed</strong><span>{metadata.recommended_count} recommended / {metadata.deferred_count} deferred / {run.response.total_errors} errors</span>{metadata.boundary_tie?.length > 0 && <p>Equal scores at the capacity boundary. OCID ordering selects work administratively; it adds no evidence of risk.</p>}</div>}
              {results.length > 1 && <><label htmlFor="result-record">Inspect record</label><select id="result-record" value={selected} onChange={e => setSelected(Number(e.target.value))}>{results.map((r, i) => <option key={i} value={i}>{r.ocid}{r.errors.length ? ' / errors' : ''}</option>)}</select></>}
              {result ? <>
                <p className="ev-record-id">{result.ocid}</p>
                <div className="ev-contract-context"><h3>{records[selected]?.label}</h3><p>{records[selected]?.record?.buyer?.name || 'Buyer not supplied'}</p><span>{records[selected]?.location?.label || 'No supported delivery coordinates supplied'}</span></div>
                <div className="ev-verdicts"><div><label>Structural reading</label><strong>{title(result.structure?.verdict)}</strong></div><div><label>Evidence gate</label><strong>{title(result.gate_verdict)}</strong></div><div><label>Normalized fields</label><strong>{quality ? `${quality.fields_present} / ${quality.fields_total}` : 'Not assessed'}</strong></div></div>
                <p className="ev-reading-note">Risk indicators for review. A green gate does not certify integrity; missing inputs may leave rules unassessable.</p>
                {result.errors.length > 0 && <div className="ev-error">{result.errors.join('; ')}</div>}
                <h3 className="ev-subheading">Observed structural findings <span>{findings.length}</span></h3>
                {findings.length === 0 && <p>No structural contradictions reported for these inputs. This does not verify facts outside the supplied record.</p>}
                {findings.map((f, i) => <article className="ev-finding" key={`${f.rule_id}-${i}`}><div><code>{f.rule_id}</code><span>{title(f.layer)}</span></div><h4>{f.description}</h4><p>{f.evidence}</p><details><summary>Rule basis</summary><p>{f.legal_citation || 'Citation not supplied'}</p></details></article>)}
                <details className="ev-detail" open><summary>Input completeness and assessment limits</summary><p>Presence is measured on the normalized dossier; defaults may count as present. It does not verify truth. The v1 heuristic treats numeric zero as missing.</p>{quality?.missing_fields.length > 0 ? <div className="ev-chips">{quality.missing_fields.map(f => <span key={f}>{title(f)}</span>)}</div> : <p>No fields marked missing by the presence heuristic.</p>}{quality?.mapping_gaps?.length > 0 && <div className="ev-error"><strong>Input mapping requires review</strong><p>Supplied fields were not reflected in normalized inputs. Affected conclusions need review.</p>{quality.mapping_gaps.map(g => <div key={g.source_path}><code>{g.source_path}</code> → {title(g.normalized_field)}</div>)}</div>}<p>{scoring?.band_qualification}</p><p>{scoring?.assessment_context?.note || ''}</p></details>
                <details className="ev-detail"><summary>Calculation and evidence-gate trace</summary><p>Composite: {scoring?.composite_structural_score ?? 'Not assessable'}. This is not a probability of corruption.</p><p>{scoring?.composite_formula}</p>{Object.entries(scoring?.sub_scores || {}).map(([name, s]) => <div className="ev-trace" key={name}><span>{title(name)}</span><strong>{s.score ?? 'Indeterminate'}</strong></div>)}{result.gate_outcome?.dimension_results.map(d => <div className="ev-dimension" key={d.dimension}><strong>{title(d.dimension)} / {d.fired ? 'fired' : 'not fired'}</strong><p>{d.detail}</p></div>)}</details>
                <details className="ev-detail"><summary>Reproduction receipt</summary><p>Hashes bind content and calibration. They do not authenticate a document's issuer or certify a finding.</p><dl className="ev-hashes">{['input_sha256', 'result_sha256', 'profile_sha256', 'source_manifest_sha256'].map(k => <div key={k}><dt>{title(k)}</dt><dd>{result.analysis_receipt?.[k] || 'Not available'}</dd></div>)}</dl></details>
              </> : <p>The batch contained no records. No analysis was performed.</p>}
            </>}
          </section>
        </div>
      </>}

      {tab === 'method' && <section className="ev-method">
        <div className="ev-method-lead"><p className="ev-eyebrow">HOW TO READ A RESULT</p><h2>Three readings.<br />Different questions.</h2><p>Keeping these distinctions visible prevents a score from becoming a claim the evidence cannot support.</p></div>
        <div className="ev-method-grid">{[
          ['01', 'Structural analysis', 'Do the supplied relationships and procedural facts contain contradictions under the selected rules?', 'Findings expose their rule, observed basis, and citation. Jurisdiction calibration supplies monetary thresholds and fiscal context.'],
          ['02', 'Evidence gate', 'Do independent analytical dimensions meet the configured escalation conditions?', 'Read the observed value, threshold, and detail for each dimension. A gate verdict is distinct from the structural reading.'],
          ['03', 'Input completeness', 'Which engine-consumed fields were populated?', 'A full record can still be false. A sparse record can leave findings unassessable. Completeness does not alter analytical verdicts.'],
        ].map(([n, h, q, a]) => <article key={n}><span className="ev-step">{n}</span><h3>{h}</h3><p className="ev-question">{q}</p><p>{a}</p></article>)}</div>
        <div className="ev-panel ev-method-note"><h3>What the calculation establishes</h3><p>The structural composite summarizes determinate sub-scores. Indeterminate axes are excluded, and a result based on one axis carries a low-context qualification. The composite is not a calibrated probability of corruption.</p><p>Portfolio capacity changes the review queue, never the underlying findings. Equal scores use identifier ordering solely to meet the administrative ceiling; the tied group is disclosed in the batch response.</p><h3>What reproducibility requires</h3><p>Keep the exact request, source files, jurisdiction and global calibration, dependency versions, and substantive response. The receipt excludes elapsed processing time. A matching hash establishes content equality, not source authenticity or independent validation.</p></div>
      </section>}

      {tab === 'assurance' && <section className="ev-assurance">
        <div className="ev-method-lead"><p className="ev-eyebrow">AN INSPECTABLE INSTRUMENT</p><h2>Capability stated.<br />Readiness demonstrated.</h2><p>Procurement is the operational entry point. The wider watch is a staged program whose capabilities must earn their own evidence.</p></div>
        {!assurance ? <p>Connect the API to load its capability and assurance statement.</p> : <>
          <div className="ev-capabilities">{assurance.capabilities.map(c => <article key={c.name}><span className={`ev-state ${c.state === 'API available' ? 'available' : ''}`}>{c.state}</span><h3>{c.name}</h3><p>{c.scope}</p></article>)}</div>
          <div className="ev-assurance-columns"><section className="ev-panel"><h3>Before an institutional deployment</h3><ol>{assurance.deployment_requirements.map(s => <li key={s}>{s}</li>)}</ol><p>Institutional adoption, legal approval, and security certification are not implied by this workspace.</p></section><section className="ev-panel"><h3>Reference evaluation</h3><p>Historical metrics belong to their exact evaluation corpus and sampling protocol. This interface does not present them as a fresh validation.</p><p>The reference database and root prosecution-case corpus are required to reproduce the published floor.</p><button onClick={() => download(assurance, 'sunlight-assurance.json')}>Download capability statement ↓</button><a href="/docs" target="_blank" rel="noreferrer">Open API specification ↗</a></section></div>
          <details className="ev-detail"><summary>Interpretation boundaries</summary>{assurance.interpretation.map(s => <p key={s}>{s}</p>)}</details>
        </>}
      </section>}
    </main>
    <footer className="ev-footer"><span>SUNLIGHT / Evidence that can be examined.</span><span>Decision support. Human authority. Documented limits.</span></footer>
  </div>;
}
