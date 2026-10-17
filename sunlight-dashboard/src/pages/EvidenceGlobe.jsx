import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { geoContains, geoDistance, geoGraticule10, geoInterpolate, geoOrthographic, geoPath } from 'd3-geo';
import { feature, mesh } from 'topojson-client';
import atlas from 'world-atlas/countries-110m.json';
import ProcurementTotals from './ProcurementTotals';
import PublicProcurement from './PublicProcurement';
import CountryDirectory from './CountryDirectory';
import MaterialContributions from './MaterialContributions';
import FlowCanvas from './FlowCanvas';
import ArmsContext from './ArmsContext';
import {armsComparisons, armsLinks} from './arms';
import ConflictContext from './ConflictContext';
import ConflictCanvas from './ConflictCanvas';
import {conflictPoints, countryConflictPoints, pickConflictPoint, violenceTypes} from './conflicts';
import {materialLinks, materialScope, originBalanced} from './materials';
import { publicCountries, publicScope, compactCount } from './publicProcurement';
import { countryCatalog, matchCountries, resolveCountry, recordCountry, overview, tradeLinks, money } from './watchOverview';

const land = feature(atlas, atlas.objects.land);
const borders = mesh(atlas, atlas.objects.countries, (a, b) => a !== b);
const graticule = geoGraticule10();
const countryShapes = feature(atlas, atlas.objects.countries).features;
const countryDatasetURL = new URL('../data/countries.json', import.meta.url).href;
const countryLicenseURL = new URL('../data/COUNTRIES-LICENSE.txt', import.meta.url).href;
const defaultRotation = [-12, -15];
export default function EvidenceGlobe({ records, selected, onSelect, country, onCountry, origin }) {
  const [rotation, setRotation] = useState(defaultRotation);
  const [zoom, setZoom] = useState(1);
  const [motionAllowed, setMotionAllowed] = useState(() => !window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const [query, setQuery] = useState('');
  const [searchMessage, setSearchMessage] = useState('');
  const [trade, setTrade] = useState(null);
  const [tradeOpen, setTradeOpen] = useState(false);
  const [context, setContext] = useState(null);
  const [published, setPublished] = useState(null);
  const [sourceYear, setSourceYear] = useState(null);
  const [materials, setMaterials] = useState(null);
  const [materialCode, setMaterialCode] = useState('');
  const [arms, setArms] = useState(null);
  const [armsOpen, setArmsOpen] = useState(false);
  const [armsYear, setArmsYear] = useState(2022);
  const [armsFamily, setArmsFamily] = useState('');
  const [armsCategory, setArmsCategory] = useState('');
  const [conflicts, setConflicts] = useState(null);
  const [conflictType, setConflictType] = useState('');
  const [conflictsOpen, setConflictsOpen] = useState(false);
  const [conflictSelection, setConflictSelection] = useState(null);
  const publicData = useMemo(() => publicScope(published, country, sourceYear), [published, country, sourceYear]);
  const publishedCountries = useMemo(() => publicCountries(published, sourceYear), [published, sourceYear]);
  const drag = useRef(null);
  const panel = useRef(null), controls = useRef(null), caption = useRef(null);
  const projection = useMemo(() => geoOrthographic().translate([360, 340]).scale(300 * zoom).rotate(rotation).clipAngle(90), [rotation, zoom]);
  const mapped = records.filter(r => r.location);
  const suppliedLinks = useMemo(() => records.flatMap(r => (r.links || []).map(link => ({ ...link, recordIndex: r.index }))), [records]);
  const observedTrade = useMemo(() => tradeLinks(trade), [trade]);
  const scopedTrade = useMemo(() => country ? observedTrade.filter(l => l.reporter.code === country.code || l.partner.code === country.code) : observedTrade, [observedTrade, country]);
  const materialFlows = useMemo(() => materialLinks(materials, country, materialCode), [materials, country, materialCode]);
  const drawnMaterials = useMemo(() => originBalanced(materialFlows, country ? 80 : 240), [materialFlows, country]);
  const drawnTrade = useMemo(() => originBalanced(scopedTrade, 80), [scopedTrade]);
  const materialCountries = useMemo(() => new Map((materialScope(materials, null, materialCode)?.countries || []).map(c=>[c.iso,c])), [materials, materialCode]);
  const countryMaterials = useMemo(() => materialScope(materials, country, materialCode), [materials, country, materialCode]);
  const countryData = useMemo(() => country ? overview(records, country) : null, [records, country]);
  const countryShape = country ? countryShapes.find(s => String(s.id).padStart(3, '0') === country.numeric) : null;
  const allConflictPoints = useMemo(() => conflictPoints(conflicts, conflictType), [conflicts, conflictType]);
  const scopedConflictPoints = useMemo(() => countryConflictPoints(allConflictPoints, country, countryShape), [allConflictPoints, country, countryShape]);
  const closeConflicts = useCallback(() => setConflictsOpen(false), []);
  const changeConflictType = useCallback(value => { setConflictType(value); setConflictSelection(null); }, []);
  const armsRows = useMemo(() => armsComparisons(arms, armsYear, country, armsFamily, armsCategory), [arms, armsYear, country, armsFamily, armsCategory]);
  const declaredArmsLinks = useMemo(() => armsLinks(armsRows), [armsRows]);
  const drawnArms = useMemo(() => originBalanced(declaredArmsLinks, country ? 80 : 160), [declaredArmsLinks, country]);
  const closeArms = useCallback(() => setArmsOpen(false), []);
  const basemap = useMemo(() => {
    const draw = geoPath(projection);
    return { sphere: draw({ type: 'Sphere' }), grid: draw(graticule), land: draw(land), borders: draw(borders), country: countryShape ? draw(countryShape) : null };
  }, [projection, countryShape]);
  const countryCounts = useMemo(() => {
    const counts = new Map();
    for (const record of records) { const c = recordCountry(record.record); if (c) { const previous = counts.get(c.code) || { country: c, count: 0 }; previous.count++; counts.set(c.code, previous); } }
    return countryCatalog.map(country => ({ country, count: counts.get(country.code)?.count || 0 }));
  }, [records]);
  const links = useMemo(() => {
    const selectedLinks = suppliedLinks.filter(l => l.recordIndex === selected);
    const otherLinks = suppliedLinks.filter(l => l.recordIndex !== selected);
    const routes = [...drawnTrade, ...drawnMaterials, ...drawnArms, ...otherLinks.slice(0, 20), ...selectedLinks.slice(0, 20)];
    return routes.map(link => { const interpolate = geoInterpolate(link.from, link.to); return { ...link, geometry: { type: 'LineString', coordinates: Array.from({ length: 129 }, (_, i) => interpolate(i / 128)) } }; });
  }, [suppliedLinks, drawnTrade, drawnMaterials, drawnArms, selected]);

  useEffect(() => {
    const update = () => {
      panel.current?.style.setProperty('--ev-caption-height', `${Math.ceil(caption.current?.getBoundingClientRect().height || 0)}px`);
      panel.current?.style.setProperty('--ev-controls-height', `${Math.ceil(controls.current?.getBoundingClientRect().height || 0)}px`);
    };
    const observer = new ResizeObserver(update);
    observer.observe(caption.current); observer.observe(controls.current); update();
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    try { localStorage.removeItem('sunlight.globe.background.v1'); } catch { /* Storage may be disabled. */ }
    const controller = new AbortController();
    async function load(path, setter) { try { const response = await fetch(path, { signal: controller.signal }); if (!response.ok) throw new Error('Source unavailable'); setter(await response.json()); } catch (error) { if (error.name !== 'AbortError') setter({ status: 'unavailable', routes: [], errors: [{ reason: 'Source connection unavailable' }] }); } }
    load('/watch-data/context', setContext); load('/watch-data/procurement', setPublished); load('/watch-data/materials', setMaterials); load('/watch-data/conflicts', setConflicts); load('/watch-data/arms', setArms);
    return () => controller.abort();
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setTrade(null);
    if (country && !country.numeric) { setTrade({ status: 'unavailable', routes: [], errors: [{ reason: 'No source reporter mapping' }] }); return () => controller.abort(); }
    const suffix = country ? `?reporter=${Number(country.numeric)}` : '';
    fetch(`/watch-data/trade${suffix}`, { signal: controller.signal }).then(response => { if (!response.ok) throw new Error('Source unavailable'); return response.json(); }).then(setTrade).catch(error => { if (error.name !== 'AbortError') setTrade({ status: 'unavailable', routes: [], errors: [{ reason: 'Source unavailable' }] }); });
    return () => controller.abort();
  }, [country]);
  useEffect(() => {
    setQuery(country?.name || '');
    setSearchMessage('');
    setConflictSelection(null);
    if (!country) { setRotation(defaultRotation); setZoom(1); return; }
    const rotation = [-country.center[0], -country.center[1]];
    setRotation(rotation);
    const shape = countryShapes.find(s => String(s.id).padStart(3, '0') === country.numeric);
    if (!shape) { setZoom(5); return; }
    const bounds = geoPath(geoOrthographic().translate([360,340]).scale(300).rotate(rotation).clipAngle(90)).bounds(shape);
    const width = bounds[1][0] - bounds[0][0], height = bounds[1][1] - bounds[0][1];
    setZoom(Math.min(30, Math.max(1.05, Math.min(510 / Math.max(width,1), 410 / Math.max(height,1)))));
  }, [country]);

  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const change = () => setMotionAllowed(!preference.matches);
    preference.addEventListener('change', change);
    return () => preference.removeEventListener('change', change);
  }, []);
  useEffect(() => {
    if (!motionAllowed || country) return;
    let frame, previous = null;
    function tick(now) {
      frame = requestAnimationFrame(tick);
      if (document.hidden) { previous = null; return; }
      if (previous === null) { previous = now; return; }
      const elapsed = now - previous;
      if (elapsed < 1000 / 20) return;
      const seconds = Math.min(elapsed / 1000, .1);
      previous = now;
      // Positive longitude rotation moves the surface eastward; one turn / 180 s.
      if (!country) setRotation(([longitude, latitude]) => [(longitude + seconds * 2) % 360, latitude]);
    }
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [motionAllowed, country]);

  function focus() {
    const location = records[selected]?.location;
    if (location) { setRotation([-location.coordinates[0], -location.coordinates[1]]); }
  }
  function rotate(dx, dy) { setRotation(([x, y]) => [x + dx, Math.max(-85, Math.min(85, y + dy))]); }
  const front = coordinates => geoDistance(coordinates, [-rotation[0], -rotation[1]]) <= Math.PI / 2;
  const chooseCountry = useCallback(value => { onCountry(value); setQuery(value.name); setSearchMessage(''); }, [onCountry]);
  function selectConflictObservation(event) {
    if (drag.current?.moved) return;
    const matrix = event.currentTarget.getScreenCTM(); if (!matrix) return;
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
    const observation = pickConflictPoint(scopedConflictPoints, rotation, zoom, [point.x, point.y]);
    if (observation) { event.stopPropagation(); setConflictSelection(observation); setConflictsOpen(true); }
  }
  function selectMapCountry(event) {
    if (event.target.closest('[data-marker], [data-country]') || drag.current?.moved) return;
    const matrix = event.currentTarget.getScreenCTM(); if (!matrix) return;
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
    if (Math.hypot(point.x - 360, point.y - 340) > projection.scale()) return;
    const coordinates = projection.invert([point.x, point.y]);
    const shape = countryShapes.find(s => geoContains(s, coordinates));
    const match = shape && countryCatalog.find(c => c.numeric && c.numeric === String(shape.id).padStart(3, '0'));
    if (match) chooseCountry(match);
  }
  const matches = query && query !== country?.name ? matchCountries(query) : [];
  return <section ref={panel} className="ev-globe-panel" aria-label="Geographic evidence view">
    <div className="ev-map-heading"><div><span className="ev-eyebrow">GLOBAL WATCH / GEOGRAPHIC CONTEXT</span><h1>Procurement watch</h1></div><div className="ev-watch-counters"><PublicProcurement snapshot={published} country={country} year={sourceYear} onYear={setSourceYear} onCountry={chooseCountry}/><MaterialContributions snapshot={materials} country={country} onCountry={onCountry} productCode={materialCode} onProduct={setMaterialCode} links={materialFlows} drawn={drawnMaterials.length}/><ProcurementTotals records={records} country={country} context={context} origin={origin} onSelect={onSelect}/></div></div>
    <div className="ev-country-search"><form onSubmit={e => { e.preventDefault(); const exact = resolveCountry(query); if (exact) chooseCountry(exact); else setSearchMessage('Choose a matching country below.'); }}><label htmlFor="country-research">Research a country or territory</label><div><input id="country-research" type="search" autoComplete="off" placeholder="Country name or ISO code" value={query} onChange={e => { setQuery(e.target.value); setSearchMessage(''); }}/><button type="submit">Find ↗</button></div></form>{matches.length > 0 && <ul>{matches.map(c => <li key={c.code}><button onClick={() => chooseCountry(c)}>{c.name}<span>{c.code}</span></button></li>)}</ul>}{searchMessage && <p role="status">{searchMessage}</p>}<CountryDirectory snapshot={published} year={sourceYear} onCountry={chooseCountry}/>
      {country && <div className="ev-country-research"><span className="ev-eyebrow">COUNTRY RESEARCH</span><h2>{country.name}</h2><p>{country.official}</p>{!countryShape && <p>Boundary unavailable at this basemap resolution. The map marks a country reference point.</p>}<div className="ev-published-country"><span>PUBLISHED PROCUREMENT / {publicData?.year || 'SOURCE COVERAGE'}</span><strong>{publicData ? money(publicData.usd, 'USD') : 'No published figure'}</strong><p>{publicData ? `${publicData.contracts.toLocaleString('en')} contracts in publisher coverage. Open the published total above for markets and provenance.` : 'This country is included. No spending value is invented where the source has no observation.'}</p></div><div className="ev-country-materials"><span>RAW MATERIALS & PRIMARY INPUTS / {materials?.year || 'SOURCE'}</span><strong>{countryMaterials?.hasObservation ? money(countryMaterials.exports, 'USD') : 'No source observation'}</strong><p>Selected material exports · {countryMaterials?.products.filter(p=>p.exports>0).length || 0} HS4 headings. Open the white total for materials, partners and source coverage.</p></div><div className="ev-country-conflicts"><span>RECORDED VIOLENCE / UCDP 2026 EXTRACT</span><p>{conflicts?.events ? `${scopedConflictPoints.reduce((n,p)=>n+p.events.length,0)} plotted source records at ${scopedConflictPoints.length} reference locations within the map boundary. Coverage is partial; a missing point does not establish peace.` : 'Conflict data unavailable. No location is invented.'}</p><button onClick={()=>{setConflictSelection(null);setConflictsOpen(true)}}>Conflict context & sources ↗</button></div><div className="ev-country-arms"><span>ARMS DECLARATIONS / {armsYear}</span><p>{armsRows.length} declared pair/categories in partial UNROCA mirror coverage. Missing data is unknown.</p><button onClick={()=>setArmsOpen(true)}>Arms reporting & accountability ↗</button></div><div className="ev-country-numbers"><div><strong>{countryData.records}</strong><span>Supplied records</span></div><div><strong>{countryData.documents}</strong><span>Listed documents</span></div><div><strong>{countryData.missingCompletion}</strong><span>Completion-link gaps</span></div><div><strong>{scopedTrade.length}</strong><span>Available trade links</span></div></div>{countryData.amounts.map(a => <p className="ev-country-amount" key={`${a.currency}-${a.basis}`}>{money(a.amount,a.currency)} <small>{a.basis}</small></p>)}<p>{countryData.milestonesMet} / {countryData.milestones} implementation milestones marked met in supplied records.</p><p>Analysis figures cover your supplied records. Published figures come from the cited source dataset; open either total above for its own evidence and coverage.</p>{!countryData.records && <p>No contract-level records have been analyzed for this buyer country in this session. Published aggregates are shown separately above.</p>}<button onClick={() => onCountry(null)}>Return to global watch ↗</button></div>}
    </div>
    <svg viewBox="0 0 720 680" className="ev-globe" role="group" aria-label="Interactive globe. Drag or use arrow keys to rotate." tabIndex="0" onClick={selectMapCountry} onClickCapture={selectConflictObservation}
      onKeyDown={e => { const moves = { ArrowLeft: [-10, 0], ArrowRight: [10, 0], ArrowUp: [0, -10], ArrowDown: [0, 10] }; if (moves[e.key]) { e.preventDefault(); rotate(...moves[e.key]); } }}
      onPointerDown={e => { if (e.target.closest('[data-marker], [data-country]')) return; drag.current = { x: e.clientX, y: e.clientY, moved: false }; e.currentTarget.setPointerCapture(e.pointerId); }}
      onPointerMove={e => { if (!drag.current || drag.current.x == null) return; rotate((e.clientX - drag.current.x) * .3, -(e.clientY - drag.current.y) * .3); drag.current = { x: e.clientX, y: e.clientY, moved: drag.current.moved || Math.abs(e.movementX) + Math.abs(e.movementY) > 2 }; }}
      onPointerUp={() => { const moved = drag.current?.moved; drag.current = null; if (moved) { drag.current = { moved: true }; setTimeout(() => { drag.current = null; }, 0); } }} onPointerCancel={() => { drag.current = null; }}>
      <defs><radialGradient id="ev-ocean" cx="38%" cy="30%"><stop stopColor="#162b34"/><stop offset="1" stopColor="#0c1922"/></radialGradient><clipPath id="ev-sphere-clip"><path d={basemap.sphere}/></clipPath></defs>
      <path d={basemap.sphere} fill="url(#ev-ocean)" stroke="#46606a" strokeWidth="1"/>
      <g clipPath="url(#ev-sphere-clip)">
        <path d={basemap.grid} fill="none" stroke="#28404a" strokeWidth=".55"/>
        <path d={basemap.land} fill="#29434a" stroke="#567079" strokeWidth=".6"/>
        <path d={basemap.borders} fill="none" stroke="#5c737a" strokeWidth=".5"/>
        {countryShape && <path d={basemap.country} className="ev-country-highlight"/>}
        {country && !countryShape && <g transform={`translate(${projection(country.center).join(',')})`}><circle r="8" fill="#e2c36d"/><text y="-18" textAnchor="middle" fill="#f4d998" fontSize="14">{country.name}</text></g>}
        <foreignObject x="0" y="0" width="720" height="680" pointerEvents="none" aria-hidden="true">
          <FlowCanvas links={links} rotation={rotation} zoom={zoom} motionAllowed={motionAllowed}/>
        </foreignObject>
        {countryCounts.map(({country:c,count}) => {
          if (!front(c.center)) return null;
          const [x,y] = projection(c.center), source = publishedCountries.get(c.code), material = materialCountries.get(c.alpha3);
          const description = `${c.name}: ${source ? `${source.contracts.toLocaleString('en')} source contracts, ${money(source.usd,'USD')}, ${source.year}` : 'published procurement data not available'}; ${material ? `${money(material.exports,'USD')} selected material exports in ${materials.year}` : 'material export observation unavailable'}; ${count} supplied records`;
          return <g className={`ev-country-count ${source ? 'has-public-data' : 'coverage-pending'}`} data-country="true" data-country-code={c.code} key={c.code} transform={`translate(${x},${y})`} role="button" tabIndex="0" aria-label={`Research ${description}`} onClick={() => chooseCountry(c)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); chooseCountry(c); } }}><circle r={source ? 9 : 3}/>{!source && material?.exports > 0 && <circle r="4.5" className="ev-material-origin"/>}{source && <text textAnchor="middle" dy="3">{compactCount(source.contracts)}</text>}<title>{description}</title></g>;
        })}
        {mapped.map(r => {
          if (!front(r.location.coordinates)) return null;
          const [x, y] = projection(r.location.coordinates);
          return <g key={r.index} data-marker="true" role="button" tabIndex="0" aria-label={`Inspect ${r.label}`} className={`ev-map-marker ${selected === r.index ? 'selected' : ''}`} transform={`translate(${x},${y})`}
            onClick={() => { onSelect(r.index); }} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); onSelect(r.index); } }}>
            <title>{r.label} — {r.location.label}</title><circle r="14" fill="transparent"/><circle r="9" className="ev-marker-ring"/><circle r="3.5" fill="#e3c582"/>
          </g>;
        })}
        <foreignObject x="0" y="0" width="720" height="680" pointerEvents="none" aria-hidden="true">
          <ConflictCanvas points={scopedConflictPoints} rotation={rotation} zoom={zoom}/>
        </foreignObject>
      </g>
    </svg>
    <div className="ev-flow-legend" aria-label="Flow legend"><span><i className="gold"/>Yellow · total goods exports (2023)</span><span><i className="white"/>White · material exports ({materials?.year || 'source'})</span><button className="ev-conflict-legend" onClick={()=>{setConflictSelection(null);setConflictsOpen(true)}} aria-label="Open conflict observations"><i className="red"/>Red · {conflicts?.latest_start ? 'recorded violence (Aug 2026)' : conflicts ? 'conflict source unavailable' : 'loading conflict context'} ↗</button><button className="ev-arms-legend" onClick={()=>setArmsOpen(true)} aria-label="Open arms reporting and accountability"><i className="blue"/>Blue · declared arms ({armsYear}) ↗</button>{(armsFamily || armsCategory) && <button onClick={()=>{setArmsFamily('');setArmsCategory('')}}>Arms category filter · clear ×</button>}{conflictType && <button onClick={()=>changeConflictType('')}>{violenceTypes[conflictType]} · clear filter ×</button>}{materialCode && <button onClick={()=>setMaterialCode('')}>HS {materialCode} · clear filter ×</button>}</div><div ref={controls} className="ev-map-controls"><button onClick={() => setZoom(z => Math.min(45, z * 1.2))} aria-label="Zoom in">+</button><button onClick={() => setZoom(z => Math.max(.7, z / 1.2))} aria-label="Zoom out">−</button><button onClick={() => { onCountry(null); setRotation(defaultRotation); setZoom(1); }}>Global view</button><button disabled={!records[selected]?.location} onClick={focus}>Locate record</button><button onClick={() => setTradeOpen(value => !value)}>Trade data & sources ↗</button></div>
    {tradeOpen && <section className="ev-trade-panel" aria-label="Trade data and sources"><button className="ev-ledger-close" onClick={() => setTradeOpen(false)}>Close sources ×</button><p className="ev-eyebrow">UN COMTRADE / {trade?.period || 'ANNUAL DATA'}</p><h2>Trade, with its source attached.</h2><p>{trade?.coverage || 'Connecting to the public trade source. No illustrative routes are displayed.'}</p><p>Status: {trade?.status || 'Loading'} · Retrieved: {trade?.fetched_at || 'No successful retrieval'} · {scopedTrade.length} bilateral links available{scopedTrade.length > 80 ? ' / 80 drawn, balanced by available exporter' : ''}.</p><p>Yellow moving points connect reporting and partner country reference points. They are schematic relationships, not tracked ships or actual transport paths. Animation speed and light counts do not encode money or shipment volume. Trade values are separate from procurement values.</p>{trade?.errors?.length > 0 && <p>{trade.errors.length} reporting-source requests failed. Missing routes do not imply absent trade.</p>}<div className="ev-table-scroll"><table><thead><tr><th>Reporter → partner</th><th>Period</th><th>Export value (USD)</th><th>Source</th><th>Reported flag</th></tr></thead><tbody>{scopedTrade.map((l,i) => <tr key={i}><td>{l.label}</td><td>{l.period}</td><td>{money(l.usd,'USD')}</td><td><a href={l.sourceURL} target="_blank" rel="noreferrer">Source query ↗</a></td><td>{l.reported === true ? 'true' : l.reported === false ? 'false / source aggregate' : 'Not supplied'}</td></tr>)}</tbody></table></div><p className="ev-caption">Country reference points: world-countries 5.1.0, ODbL. <a href="https://github.com/mledoze/countries" target="_blank" rel="noreferrer">Dataset source ↗</a> · <a href={countryDatasetURL} download="sunlight-country-catalog.json">Download country catalog</a> · <a href={countryLicenseURL} target="_blank" rel="noreferrer">ODbL license</a></p></section>}
    <ArmsContext snapshot={arms} country={country} open={armsOpen} onClose={closeArms} year={armsYear} onYear={setArmsYear} family={armsFamily} onFamily={setArmsFamily} category={armsCategory} onCategory={setArmsCategory}/><ConflictContext snapshot={conflicts} points={scopedConflictPoints} country={country} boundaryAvailable={Boolean(countryShape)} selection={conflictSelection} open={conflictsOpen} onClose={closeConflicts} type={conflictType} onType={changeConflictType}/><div ref={caption} className="ev-map-caption"><div><i/>{countryCatalog.length} countries & territories · {publishedCountries.size} with published observations at or before {sourceYear || published?.default_year || 'source year'} · {scopedTrade.length} goods trade links · {materialFlows.length.toLocaleString('en')} material links ({drawnMaterials.length} drawn) · {scopedConflictPoints.length} conflict reference points · {declaredArmsLinks.length} declared arms relationships ({drawnArms.length} drawn)</div><p>Gold labels show publisher contract counts; each marker carries its source year. White rings identify countries with material export observations. Gray dots remain selectable where neither source has figures. White moving points show selected material exports from CEPII BACI, {materials?.year || 'source year'}. {trade?.status === 'unavailable' ? 'The trade connection is unavailable; published procurement totals remain available.' : 'Yellow moving points use dated UN Comtrade data, with values and coverage in sources.'}</p><p className="ev-conflict-caption">Red points: dated, partial UCDP candidate observations; latest record start {conflicts?.latest_start || 'unavailable'}. Open red context for precision, coverage and sources. Co-location alone does not establish stolen funds. Blue moving points: historical UNROCA declarations, not untraced recoveries. No live tracking or global diversion total is implied.</p><small>{!motionAllowed ? 'System reduced-motion preference active' : country ? 'Country research · rotation held' : 'West → east · 3 min / turn (accelerated)'} · Natural Earth boundaries do not imply endorsement.</small></div>
  </section>;
}
