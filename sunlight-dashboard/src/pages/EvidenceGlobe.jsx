import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { geoContains, geoDistance, geoGraticule10, geoInterpolate, geoOrthographic, geoPath } from 'd3-geo';
import { feature, mesh } from 'topojson-client';
import atlas from 'world-atlas/countries-110m.json';
import ProcurementTotals from './ProcurementTotals';
import PublicProcurement from './PublicProcurement';
import CountryDirectory from './CountryDirectory';
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
  const [clock, setClock] = useState(0);
  const [query, setQuery] = useState('');
  const [searchMessage, setSearchMessage] = useState('');
  const [trade, setTrade] = useState(null);
  const [tradeOpen, setTradeOpen] = useState(false);
  const [context, setContext] = useState(null);
  const [published, setPublished] = useState(null);
  const [sourceYear, setSourceYear] = useState(null);
  const publicData = useMemo(() => publicScope(published, country, sourceYear), [published, country, sourceYear]);
  const publishedCountries = useMemo(() => publicCountries(published, sourceYear), [published, sourceYear]);
  const drag = useRef(null);
  const projection = useMemo(() => geoOrthographic().translate([360, 340]).scale(300 * zoom).rotate(rotation).clipAngle(90), [rotation, zoom]);
  const path = geoPath(projection);
  const mapped = records.filter(r => r.location);
  const suppliedLinks = useMemo(() => records.flatMap(r => (r.links || []).map(link => ({ ...link, recordIndex: r.index }))), [records]);
  const observedTrade = useMemo(() => tradeLinks(trade), [trade]);
  const scopedTrade = useMemo(() => country ? observedTrade.filter(l => l.reporter.code === country.code || l.partner.code === country.code) : observedTrade, [observedTrade, country]);
  const countryData = useMemo(() => country ? overview(records, country) : null, [records, country]);
  const countryShape = country ? countryShapes.find(s => String(s.id).padStart(3, '0') === country.numeric) : null;
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
    const routes = [...selectedLinks.slice(0, 20), ...scopedTrade.slice(0, 80), ...otherLinks.slice(0, 20)];
    return routes.map(link => { const interpolate = geoInterpolate(link.from, link.to); return { ...link, interpolate, geometry: { type: 'LineString', coordinates: Array.from({ length: 65 }, (_, i) => interpolate(i / 64)) } }; });
  }, [suppliedLinks, scopedTrade, selected]);
  const routePaths = useMemo(() => links.map(link => geoPath(projection)(link.geometry)), [links, projection]);

  useEffect(() => {
    try { localStorage.removeItem('sunlight.globe.background.v1'); } catch { /* Storage may be disabled. */ }
    const controller = new AbortController();
    async function load(path, setter) { try { const response = await fetch(path, { signal: controller.signal }); if (!response.ok) throw new Error('Source unavailable'); setter(await response.json()); } catch (error) { if (error.name !== 'AbortError') setter({ status: 'unavailable', routes: [], errors: [{ reason: 'Source connection unavailable' }] }); } }
    load('/watch-data/context', setContext); load('/watch-data/procurement', setPublished);
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
    if (!motionAllowed) return;
    let frame, previous = null;
    function tick(now) {
      frame = requestAnimationFrame(tick);
      if (document.hidden) { previous = null; return; }
      if (previous === null) { previous = now; return; }
      const elapsed = now - previous;
      if (elapsed < 1000 / 30) return;
      const seconds = Math.min(elapsed / 1000, .1);
      previous = now;
      // Positive longitude rotation moves the surface eastward; one turn / 180 s.
      if (!country) setRotation(([longitude, latitude]) => [(longitude + seconds * 2) % 360, latitude]);
      setClock(time => time + seconds);
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
  function selectMapCountry(event) {
    if (event.target.closest('[data-marker], [data-flow], [data-country]') || drag.current?.moved) return;
    const matrix = event.currentTarget.getScreenCTM(); if (!matrix) return;
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
    if (Math.hypot(point.x - 360, point.y - 340) > projection.scale()) return;
    const coordinates = projection.invert([point.x, point.y]);
    const shape = countryShapes.find(s => geoContains(s, coordinates));
    const match = shape && countryCatalog.find(c => c.numeric && c.numeric === String(shape.id).padStart(3, '0'));
    if (match) chooseCountry(match);
  }
  const matches = query && query !== country?.name ? matchCountries(query) : [];
  return <section className="ev-globe-panel" aria-label="Geographic evidence view">
    <div className="ev-map-heading"><div><span className="ev-eyebrow">GLOBAL WATCH / GEOGRAPHIC CONTEXT</span><h1>Procurement watch</h1></div><div className="ev-watch-counters"><PublicProcurement snapshot={published} country={country} year={sourceYear} onYear={setSourceYear} onCountry={chooseCountry}/><ProcurementTotals records={records} country={country} context={context} origin={origin} onSelect={onSelect}/></div></div>
    <div className="ev-country-search"><form onSubmit={e => { e.preventDefault(); const exact = resolveCountry(query); if (exact) chooseCountry(exact); else setSearchMessage('Choose a matching country below.'); }}><label htmlFor="country-research">Research a country or territory</label><div><input id="country-research" type="search" autoComplete="off" placeholder="Country name or ISO code" value={query} onChange={e => { setQuery(e.target.value); setSearchMessage(''); }}/><button type="submit">Find ↗</button></div></form>{matches.length > 0 && <ul>{matches.map(c => <li key={c.code}><button onClick={() => chooseCountry(c)}>{c.name}<span>{c.code}</span></button></li>)}</ul>}{searchMessage && <p role="status">{searchMessage}</p>}<CountryDirectory snapshot={published} year={sourceYear} onCountry={chooseCountry}/>
      {country && <div className="ev-country-research"><span className="ev-eyebrow">COUNTRY RESEARCH</span><h2>{country.name}</h2><p>{country.official}</p>{!countryShape && <p>Boundary unavailable at this basemap resolution. The map marks a country reference point.</p>}<div className="ev-published-country"><span>PUBLISHED PROCUREMENT / {publicData?.year || 'SOURCE COVERAGE'}</span><strong>{publicData ? money(publicData.usd, 'USD') : 'No published figure'}</strong><p>{publicData ? `${publicData.contracts.toLocaleString('en')} contracts in publisher coverage. Open the published total above for markets and provenance.` : 'This country is included. No spending value is invented where the source has no observation.'}</p></div><div className="ev-country-numbers"><div><strong>{countryData.records}</strong><span>Supplied records</span></div><div><strong>{countryData.documents}</strong><span>Listed documents</span></div><div><strong>{countryData.missingCompletion}</strong><span>Completion-link gaps</span></div><div><strong>{scopedTrade.length}</strong><span>Available trade links</span></div></div>{countryData.amounts.map(a => <p className="ev-country-amount" key={`${a.currency}-${a.basis}`}>{money(a.amount,a.currency)} <small>{a.basis}</small></p>)}<p>{countryData.milestonesMet} / {countryData.milestones} implementation milestones marked met in supplied records.</p><p>Analysis figures cover your supplied records. Published figures come from the cited source dataset; open either total above for its own evidence and coverage.</p>{!countryData.records && <p>No contract-level records have been analyzed for this buyer country in this session. Published aggregates are shown separately above.</p>}<button onClick={() => onCountry(null)}>Return to global watch ↗</button></div>}
    </div>
    <svg viewBox="0 0 720 680" className="ev-globe" role="group" aria-label="Interactive globe. Drag or use arrow keys to rotate." tabIndex="0" onClick={selectMapCountry}
      onKeyDown={e => { const moves = { ArrowLeft: [-10, 0], ArrowRight: [10, 0], ArrowUp: [0, -10], ArrowDown: [0, 10] }; if (moves[e.key]) { e.preventDefault(); rotate(...moves[e.key]); } }}
      onPointerDown={e => { if (e.target.closest('[data-marker], [data-flow], [data-country]')) return; drag.current = { x: e.clientX, y: e.clientY, moved: false }; e.currentTarget.setPointerCapture(e.pointerId); }}
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
        {links.map((link, i) => {
          const progress = (clock / 6 + i * .27) % 1;
          const point = link.interpolate(progress);
          const trail = { type: 'LineString', coordinates: Array.from({ length: 10 }, (_, n) => link.interpolate(Math.max(0, progress - .1 + n / 90))) };
          return <g key={`${link.recordIndex ?? 'trade'}-${i}`} className={`ev-procurement-flow ${link.usd ? 'trade' : 'procurement'}`} data-flow="true">
            <title>{link.usd ? `${link.label}: ${money(link.usd, 'USD')} exports, ${link.period}. UN Comtrade; country-center connection, not a shipping route.` : `${link.label}. Supplied procurement relationship; not shipment tracking.`}</title>
            <path d={routePaths[i]} className="ev-flow-route"/>
            <path d={path(trail)} className="ev-flow-trail"/>
            {front(point) && <circle className="ev-flow-particle" cx={projection(point)[0]} cy={projection(point)[1]} r={link.usd ? 3.6 : 3}/>}
            {[link.from, link.to].filter(front).map((coordinate, j) => <circle key={j} cx={projection(coordinate)[0]} cy={projection(coordinate)[1]} r="2" className="ev-flow-endpoint"/>)}
          </g>;
        })}
        {countryCounts.map(({country:c,count}) => {
          if (!front(c.center)) return null;
          const [x,y] = projection(c.center), source = publishedCountries.get(c.code);
          const description = `${c.name}: ${source ? `${source.contracts.toLocaleString('en')} source contracts, ${money(source.usd,'USD')}, ${source.year}` : 'published procurement data not available'}; ${count} supplied records`;
          return <g className={`ev-country-count ${source ? 'has-public-data' : 'coverage-pending'}`} data-country="true" data-country-code={c.code} key={c.code} transform={`translate(${x},${y})`} role="button" tabIndex="0" aria-label={`Research ${description}`} onClick={() => chooseCountry(c)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); chooseCountry(c); } }}><circle r={source ? 9 : 3}/>{source && <text textAnchor="middle" dy="3">{compactCount(source.contracts)}</text>}<title>{description}</title></g>;
        })}
        {mapped.map(r => {
          if (!front(r.location.coordinates)) return null;
          const [x, y] = projection(r.location.coordinates);
          return <g key={r.index} data-marker="true" role="button" tabIndex="0" aria-label={`Inspect ${r.label}`} className={`ev-map-marker ${selected === r.index ? 'selected' : ''}`} transform={`translate(${x},${y})`}
            onClick={() => { onSelect(r.index); }} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); onSelect(r.index); } }}>
            <title>{r.label} — {r.location.label}</title><circle r="14" fill="transparent"/><circle r="9" className="ev-marker-ring"/><circle r="3.5" fill="#e3c582"/>
          </g>;
        })}
      </g>
    </svg>
    <div className="ev-map-controls"><button onClick={() => setZoom(z => Math.min(45, z * 1.2))} aria-label="Zoom in">+</button><button onClick={() => setZoom(z => Math.max(.7, z / 1.2))} aria-label="Zoom out">−</button><button onClick={() => { onCountry(null); setRotation(defaultRotation); setZoom(1); }}>Global view</button><button disabled={!records[selected]?.location} onClick={focus}>Locate record</button><button onClick={() => setTradeOpen(value => !value)}>Trade data & sources ↗</button></div>
    {tradeOpen && <section className="ev-trade-panel" aria-label="Trade data and sources"><button className="ev-ledger-close" onClick={() => setTradeOpen(false)}>Close sources ×</button><p className="ev-eyebrow">UN COMTRADE / {trade?.period || 'ANNUAL DATA'}</p><h2>Trade, with its source attached.</h2><p>{trade?.coverage || 'Connecting to the public trade source. No illustrative routes are displayed.'}</p><p>Status: {trade?.status || 'Loading'} · Retrieved: {trade?.fetched_at || 'No successful retrieval'} · {scopedTrade.length} bilateral links available{scopedTrade.length > 80 ? ' / top 80 drawn' : ''}.</p><p>Yellow trails connect reporting and partner country reference points. They are schematic relationships, not tracked ships or actual transport paths. Animation speed and light counts do not encode money or shipment volume. Trade values are separate from procurement values.</p>{trade?.errors?.length > 0 && <p>{trade.errors.length} reporting-source requests failed. Missing routes do not imply absent trade.</p>}<div className="ev-table-scroll"><table><thead><tr><th>Reporter → partner</th><th>Period</th><th>Export value (USD)</th><th>Source</th><th>Reported flag</th></tr></thead><tbody>{scopedTrade.map((l,i) => <tr key={i}><td>{l.label}</td><td>{l.period}</td><td>{money(l.usd,'USD')}</td><td><a href={l.sourceURL} target="_blank" rel="noreferrer">Source query ↗</a></td><td>{l.reported === true ? 'true' : l.reported === false ? 'false / source aggregate' : 'Not supplied'}</td></tr>)}</tbody></table></div><p className="ev-caption">Country reference points: world-countries 5.1.0, ODbL. <a href="https://github.com/mledoze/countries" target="_blank" rel="noreferrer">Dataset source ↗</a> · <a href={countryDatasetURL} download="sunlight-country-catalog.json">Download country catalog</a> · <a href={countryLicenseURL} target="_blank" rel="noreferrer">ODbL license</a></p></section>}
    <div className="ev-map-caption"><div><i/>{countryCatalog.length} countries & territories · {publishedCountries.size} with published observations at or before {sourceYear || published?.default_year || 'source year'} · {scopedTrade.length} trade links</div><p>Gold labels show publisher contract counts; each marker carries its source year. Gray dots remain selectable where published figures are missing. {trade?.status === 'unavailable' ? 'The trade connection is unavailable; published procurement totals remain available.' : 'Yellow trade trails use dated UN Comtrade data, with values and coverage in sources.'}</p><small>{!motionAllowed ? 'System reduced-motion preference active' : country ? 'Country research · rotation held' : 'West → east · 3 min / turn (accelerated)'} · Natural Earth boundaries do not imply endorsement.</small></div>
  </section>;
}
