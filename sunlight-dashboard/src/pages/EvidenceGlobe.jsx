import { useEffect, useMemo, useRef, useState } from 'react';
import { geoDistance, geoGraticule10, geoInterpolate, geoOrthographic, geoPath } from 'd3-geo';
import { feature, mesh } from 'topojson-client';
import atlas from 'world-atlas/countries-110m.json';

const land = feature(atlas, atlas.objects.land);
const borders = mesh(atlas, atlas.objects.countries, (a, b) => a !== b);
const graticule = geoGraticule10();
const previewRoutes = [
  { from: [4.48, 51.92], to: [-77.04, 38.9], label: 'Illustrative route: Rotterdam → Washington' },
  { from: [103.82, 1.35], to: [36.82, -1.29], label: 'Illustrative route: Singapore → Nairobi' },
  { from: [-46.63, -23.55], to: [-9.14, 38.72], label: 'Illustrative route: São Paulo → Lisbon' },
];
// The exact user-supplied galaxy asset can be bundled without an external image service.
const galaxyAssets = import.meta.glob('../assets/galaxy-background.{jpg,jpeg,png,webp}', { eager: true, query: '?url', import: 'default' });
const galaxyImage = Object.values(galaxyAssets)[0];
const defaultRotation = [-12, -15];
const backgroundKey = 'sunlight.globe.background.v1';
function savedBackground() {
  try {
    const value = localStorage.getItem(backgroundKey);
    return value?.length < 4300000 && /^data:image\/(png|jpeg|webp);base64,/.test(value) ? value : '';
  } catch { return ''; }
}

export default function EvidenceGlobe({ records, selected, onSelect }) {
  const [rotation, setRotation] = useState(defaultRotation);
  const [zoom, setZoom] = useState(1);
  const [running, setRunning] = useState(() => !window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const [clock, setClock] = useState(0);
  const [preview, setPreview] = useState(false);
  const [customBackground, setCustomBackground] = useState(savedBackground);
  const [backgroundStatus, setBackgroundStatus] = useState('');
  const backgroundInput = useRef(null);
  const drag = useRef(null);
  const projection = useMemo(() => geoOrthographic().translate([360, 340]).scale(274 * zoom).rotate(rotation).clipAngle(90), [rotation, zoom]);
  const path = geoPath(projection);
  const mapped = records.filter(r => r.location);
  const suppliedLinks = useMemo(() => records.flatMap(r => (r.links || []).map(link => ({ ...link, recordIndex: r.index }))), [records]);
  // Bound visual work for a 1,000-record batch, prioritizing the selected record.
  const links = useMemo(() => {
    const routes = preview ? previewRoutes : [...suppliedLinks.filter(l => l.recordIndex === selected), ...suppliedLinks.filter(l => l.recordIndex !== selected)];
    return routes.slice(0, 80).map(link => {
      const interpolate = geoInterpolate(link.from, link.to);
      return { ...link, interpolate, geometry: { type: 'LineString', coordinates: Array.from({ length: 65 }, (_, i) => interpolate(i / 64)) } };
    });
  }, [suppliedLinks, selected, preview]);

  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const change = () => { if (preference.matches) setRunning(false); };
    preference.addEventListener('change', change);
    return () => preference.removeEventListener('change', change);
  }, []);
  useEffect(() => {
    if (!running) return;
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
      setRotation(([longitude, latitude]) => [(longitude + seconds * 2) % 360, latitude]);
      setClock(time => time + seconds);
    }
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [running]);

  function focus() {
    const location = records[selected]?.location;
    if (location) { setRunning(false); setRotation([-location.coordinates[0], -location.coordinates[1]]); }
  }
  function rotate(dx, dy) { setRunning(false); setRotation(([x, y]) => [x + dx, Math.max(-85, Math.min(85, y + dy))]); }
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
  return <section className={`ev-globe-panel ${background ? 'ev-galaxy-background' : ''}`} style={backgroundStyle} aria-label="Geographic evidence view">
    <div className="ev-map-heading"><div><span className="ev-eyebrow">GEOGRAPHIC CONTEXT</span><h1>Procurement watch</h1></div><span className="ev-map-mode">{preview ? 'ILLUSTRATIVE ROUTES' : 'SESSION EVIDENCE'}</span></div>
    {preview && <div className="ev-flow-notice" role="status">Illustration only · These routes are not observed procurement.</div>}
    <svg viewBox="0 0 720 680" className="ev-globe" role="group" aria-label="Interactive globe. Drag or use arrow keys to rotate." tabIndex="0" onFocus={() => setRunning(false)}
      onKeyDown={e => { const moves = { ArrowLeft: [-10, 0], ArrowRight: [10, 0], ArrowUp: [0, -10], ArrowDown: [0, 10] }; if (moves[e.key]) { e.preventDefault(); rotate(...moves[e.key]); } }}
      onPointerDown={e => { if (e.target.closest('[data-marker], [data-flow]')) return; setRunning(false); drag.current = { x: e.clientX, y: e.clientY }; e.currentTarget.setPointerCapture(e.pointerId); }}
      onPointerMove={e => { if (!drag.current) return; rotate((e.clientX - drag.current.x) * .3, -(e.clientY - drag.current.y) * .3); drag.current = { x: e.clientX, y: e.clientY }; }}
      onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
      <defs><radialGradient id="ev-ocean" cx="38%" cy="30%"><stop stopColor="#162b34"/><stop offset="1" stopColor="#0c1922"/></radialGradient><clipPath id="ev-sphere-clip"><path d={path({ type: 'Sphere' })}/></clipPath></defs>
      <path d={path({ type: 'Sphere' })} fill="url(#ev-ocean)" stroke="#46606a" strokeWidth="1"/>
      <g clipPath="url(#ev-sphere-clip)">
        <path d={path(graticule)} fill="none" stroke="#28404a" strokeWidth=".55"/>
        <path d={path(land)} fill="#29434a" stroke="#567079" strokeWidth=".6"/>
        <path d={path(borders)} fill="none" stroke="#5c737a" strokeWidth=".5"/>
        {links.map((link, i) => {
          const progress = (clock / 6 + i * .27) % 1;
          const point = link.interpolate(progress);
          const trail = { type: 'LineString', coordinates: Array.from({ length: 10 }, (_, n) => link.interpolate(Math.max(0, progress - .1 + n / 90))) };
          return <g key={`${link.recordIndex ?? 'preview'}-${i}`} className={`ev-procurement-flow ${preview ? 'illustrative' : ''}`} data-flow="true">
            <title>{link.label}. Schematic supplier-to-delivery relationship; not shipment tracking.</title>
            <path d={path(link.geometry)} className="ev-flow-route"/>
            <path d={path(trail)} className="ev-flow-trail"/>
            {front(point) && <circle className="ev-flow-particle" cx={projection(point)[0]} cy={projection(point)[1]} r="2.8"/>}
            {[link.from, link.to].filter(front).map((coordinate, j) => <circle key={j} cx={projection(coordinate)[0]} cy={projection(coordinate)[1]} r="2" className="ev-flow-endpoint"/>)}
          </g>;
        })}
        {mapped.map(r => {
          if (!front(r.location.coordinates)) return null;
          const [x, y] = projection(r.location.coordinates);
          return <g key={r.index} data-marker="true" role="button" tabIndex="0" aria-label={`Inspect ${r.label}`} className={`ev-map-marker ${selected === r.index ? 'selected' : ''}`} transform={`translate(${x},${y})`}
            onClick={() => { setRunning(false); onSelect(r.index); }} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); setRunning(false); onSelect(r.index); } }}>
            <title>{r.label} — {r.location.label}</title><circle r="14" fill="transparent"/><circle r="9" className="ev-marker-ring"/><circle r="3.5" fill="#e3c582"/>
          </g>;
        })}
      </g>
    </svg>
    <div className="ev-map-controls"><button onClick={() => setZoom(z => Math.min(1.65, z + .15))} aria-label="Zoom in">+</button><button onClick={() => setZoom(z => Math.max(.7, z - .15))} aria-label="Zoom out">−</button><button onClick={() => { setRotation(defaultRotation); setZoom(1); }}>Reset view</button><button disabled={!records[selected]?.location} onClick={focus}>Locate selection</button><button aria-pressed={!running} onClick={() => setRunning(value => !value)}>{running ? 'Pause motion' : 'Resume motion'}</button><button aria-pressed={preview} onClick={() => setPreview(value => !value)}>{preview ? 'Show record links' : 'Illustrate flows'}</button></div>
    <div className="ev-background-controls"><button onClick={() => backgroundInput.current?.click()}>Background image</button><input ref={backgroundInput} type="file" accept="image/jpeg,image/png,image/webp" aria-label="Choose globe background image" hidden onChange={chooseBackground}/>{customBackground && <button onClick={resetBackground}>Reset background</button>}<span role="status">{backgroundStatus || (customBackground ? 'Custom background · saved in this browser' : 'Choose your own image · stays on this device')}</span></div>
    <div className="ev-map-caption"><div><i/>{mapped.length} located / {records.length - mapped.length} without coordinates</div>
      <p>{preview ? 'Illustrative geography only. Traveling lights explain the visual language; they are not included in record or finding counts.' : suppliedLinks.length ? `${suppliedLinks.length} supplier-to-delivery links from supplied coordinates${suppliedLinks.length > 80 ? ' · first 80 shown, selection prioritized' : ''}. Lights show schematic direction, not tracked goods, payments or volume.` : mapped.length ? 'Markers represent supplied delivery coordinates. Flow links need an awarded supplier’s location and a delivery point.' : 'Import procurement records to begin. No global feed is connected. Use Illustrate flows to preview the visual language.'}</p>
      <small>{running ? 'West → east · 3 min / turn (accelerated)' : 'Motion paused'} · Drag or focus globe to pause · Basemap: Natural Earth / world-atlas. Boundaries do not imply endorsement.</small></div>
  </section>;
}
