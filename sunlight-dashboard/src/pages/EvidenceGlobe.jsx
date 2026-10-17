import { useEffect, useMemo, useRef, useState } from 'react';
import { geoDistance, geoGraticule10, geoInterpolate, geoOrthographic, geoPath } from 'd3-geo';
import { feature, mesh } from 'topojson-client';
import atlas from 'world-atlas/countries-110m.json';
import ProcurementTotals from './ProcurementTotals';
import { matchCountries, resolveCountry, recordCountry, overview, tradeLinks, money } from './watchOverview';

const land = feature(atlas, atlas.objects.land);
const borders = mesh(atlas, atlas.objects.countries, (a, b) => a !== b);
const graticule = geoGraticule10();
const countryShapes = feature(atlas, atlas.objects.countries).features;
// The exact user-supplied galaxy asset can be bundled without an external image service.
const galaxyAssets = import.meta.glob('../assets/galaxy-background.{jpg,jpeg,png,webp}', { eager: true, query: '?url', import: 'default' });
const galaxyImage = Object.values(galaxyAssets)[0];
const countryDatasetURL = new URL('../data/countries.json', import.meta.url).href;
const countryLicenseURL = new URL('../data/COUNTRIES-LICENSE.txt', import.meta.url).href;
const defaultRotation = [-12, -15];
const backgroundKey = 'sunlight.globe.background.v1';
function savedBackground() {
  try {
    const value = localStorage.getItem(backgroundKey);
    return value?.length < 4300000 && /^data:image\/(png|jpeg|webp);base64,/.test(value) ? value : '';
  } catch { return ''; }
}

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
  const [customBackground, setCustomBackground] = useState(savedBackground);
  const [backgroundStatus, setBackgroundStatus] = useState('');
  const backgroundInput = useRef(null);
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
    return [...counts.values()];
  }, [records]);
  const links = useMemo(() => {
    const selectedLinks = suppliedLinks.filter(l => l.recordIndex === selected);
    const otherLinks = suppliedLinks.filter(l => l.recordIndex !== selected);
    const routes = [...selectedLinks.slice(0, 20), ...scopedTrade.slice(0, 80), ...otherLinks.slice(0, 20)];
    return routes.map(link => { const interpolate = geoInterpolate(link.from, link.to); return { ...link, interpolate, geometry: { type: 'LineString', coordinates: Array.from({ length: 65 }, (_, i) => interpolate(i / 64)) } }; });
  }, [suppliedLinks, scopedTrade, selected]);
  const routePaths = useMemo(() => links.map(link => geoPath(projection)(link.geometry)), [links, projection]);

  useEffect(() => {
    const controller = new AbortController();
    async function load(path, setter) { try { const response = await fetch(path, { signal: controller.signal }); if (!response.ok) throw new Error('Source unavailable'); setter(await response.json()); } catch (error) { if (error.name !== 'AbortError') setter({ status: 'unavailable', routes: [], errors: [{ reason: 'Source connection unavailable' }] }); } }
    load('/watch-data/trade', setTrade); load('/watch-data/context', setContext);
    return () => controller.abort();
  }, []);
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
  async function chooseBackground(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 3 * 1024 * 1024) {
      setBackgroundStatus('Choose a JPG, PNG or WebP image up to 3 MB.'); return;
    }
    try {
      const data = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(file); });
      const picture = new Image(); picture.src = data; await picture.decode();
      setCustomBackground(data);
      try { localStorage.setItem(backgroundKey, data); setBackgroundStatus('Background saved in this browser. The image stays on this device.'); }
      catch { setBackgroundStatus('Background applied for this visit; browser storage is unavailable or full.'); }
    } catch { setBackgroundStatus('This image could not be opened. Choose a valid JPG, PNG or WebP.'); }
  }
  function resetBackground() {
    setCustomBackground('');
    try { localStorage.removeItem(backgroundKey); } catch { /* Local storage can be disabled. */ }
    setBackgroundStatus('Default background restored.');
  }
  const background = customBackground || galaxyImage;
  const backgroundStyle = useMemo(() => background ? { '--ev-galaxy-image': `url("${background}")` } : undefined, [background]);
  const front = coordinates => geoDistance(coordinates, [-rotation[0], -rotation[1]]) <= Math.PI / 2;
  function chooseCountry(value) { onCountry(value); setQuery(value.name); setSearchMessage(''); }
  const matches = query && query !== country?.name ? matchCountries(query) : [];
  return <section className={`ev-globe-panel ${background ? 'ev-galaxy-background' : ''}`} style={backgroundStyle} aria-label="Geographic evidence view">
    <div className="ev-map-heading"><div><span className="ev-eyebrow">GLOBAL WATCH / GEOGRAPHIC CONTEXT</span><h1>Procurement watch</h1></div><ProcurementTotals records={records} country={country} context={context} origin={origin} onSelect={onSelect}/></div>
    <div className="ev-country-search"><form onSubmit={e => { e.preventDefault(); const exact = resolveCountry(query); if (exact) chooseCountry(exact); else setSearchMessage('Choose a matching country below.'); }}><label htmlFor="country-research">Research a country or territory</label><div><input id="country-research" type="search" autoComplete="off" placeholder="Country name or ISO code" value={query} onChange={e => { setQuery(e.target.value); setSearchMessage(''); }}/><button type="submit">Find ↗</button></div></form>{matches.length > 0 && <ul>{matches.map(c => <li key={c.code}><button onClick={() => chooseCountry(c)}>{c.name}<span>{c.code}</span></button></li>)}</ul>}{searchMessage && <p role="status">{searchMessage}</p>}
      {country && <div className="ev-country-research"><span className="ev-eyebrow">COUNTRY RESEARCH</span><h2>{country.name}</h2><p>{country.official}</p>{!countryShape && <p>Boundary unavailable at this basemap resolution. The map marks a country reference point.</p>}<div className="ev-country-numbers"><div><strong>{countryData.records}</strong><span>Supplied records</span></div><div><strong>{countryData.documents}</strong><span>Listed documents</span></div><div><strong>{countryData.missingCompletion}</strong><span>Completion-link gaps</span></div><div><strong>{scopedTrade.length}</strong><span>Available trade links</span></div></div>{countryData.amounts.map(a => <p className="ev-country-amount" key={`${a.currency}-${a.basis}`}>{money(a.amount,a.currency)} <small>{a.basis}</small></p>)}<p>{countryData.milestonesMet} / {countryData.milestones} implementation milestones marked met in supplied records.</p><p>Procurement figures cover supplied records only. Open the documented total above for categories and source documents.</p>{!countryData.records && <p>No analyzed procurement records for this buyer country. This is missing coverage, not zero spending.</p>}<button onClick={() => onCountry(null)}>Return to global watch ↗</button></div>}
    </div>
    <svg viewBox="0 0 720 680" className="ev-globe" role="group" aria-label="Interactive globe. Drag or use arrow keys to rotate." tabIndex="0"
      onKeyDown={e => { const moves = { ArrowLeft: [-10, 0], ArrowRight: [10, 0], ArrowUp: [0, -10], ArrowDown: [0, 10] }; if (moves[e.key]) { e.preventDefault(); rotate(...moves[e.key]); } }}
      onPointerDown={e => { if (e.target.closest('[data-marker], [data-flow], [data-country]')) return; drag.current = { x: e.clientX, y: e.clientY }; e.currentTarget.setPointerCapture(e.pointerId); }}
      onPointerMove={e => { if (!drag.current) return; rotate((e.clientX - drag.current.x) * .3, -(e.clientY - drag.current.y) * .3); drag.current = { x: e.clientX, y: e.clientY }; }}
      onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
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
          const [x,y] = projection(c.center);
          return <g className="ev-country-count" data-country="true" key={c.code} transform={`translate(${x},${y})`} role="button" tabIndex="0" aria-label={`Research ${c.name}: ${count} supplied records`} onClick={() => chooseCountry(c)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); chooseCountry(c); } }}><circle r="13"/><text textAnchor="middle" dy="4">{count}</text><title>{c.name}: {count} supplied procurement records</title></g>;
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
    <div className="ev-background-controls"><button onClick={() => backgroundInput.current?.click()}>Background image</button><input ref={backgroundInput} type="file" accept="image/jpeg,image/png,image/webp" aria-label="Choose globe background image" hidden onChange={chooseBackground}/>{customBackground && <button onClick={resetBackground}>Reset background</button>}<span role="status">{backgroundStatus || (customBackground ? 'Custom background · saved in this browser' : 'Choose your own image · stays on this device')}</span></div>
    <div className="ev-map-caption"><div><i/>{mapped.length} delivery points · {links.filter(l => !l.usd).length} / {suppliedLinks.length} procurement links drawn · {scopedTrade.length} trade links ({trade?.period || 'source connecting'})</div><p>{trade?.status === 'unavailable' ? 'Trade source unavailable. Supplied procurement relationships remain visible; no substitute routes are generated.' : 'Country numbers count supplied buyer-country records. Yellow trade trails use dated UN Comtrade data; open sources for values and coverage.'}</p><small>{!motionAllowed ? 'System reduced-motion preference active' : country ? 'Country research · rotation held' : 'West → east · 3 min / turn (accelerated)'} · Natural Earth boundaries do not imply endorsement.</small></div>
  </section>;
}
