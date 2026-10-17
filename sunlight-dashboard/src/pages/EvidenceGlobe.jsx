import { useMemo, useRef, useState } from 'react';
import { geoDistance, geoGraticule10, geoOrthographic, geoPath } from 'd3-geo';
import { feature, mesh } from 'topojson-client';
import atlas from 'world-atlas/countries-110m.json';

const land = feature(atlas, atlas.objects.land);
const borders = mesh(atlas, atlas.objects.countries, (a, b) => a !== b);
const graticule = geoGraticule10();

export default function EvidenceGlobe({ records, selected, onSelect }) {
  const [rotation, setRotation] = useState([-12, -15]);
  const [zoom, setZoom] = useState(1);
  const drag = useRef(null);
  const projection = useMemo(() => geoOrthographic().translate([360, 340]).scale(274 * zoom).rotate(rotation).clipAngle(90), [rotation, zoom]);
  const path = geoPath(projection);
  const mapped = records.filter(r => r.location);
  function focus() {
    const location = records[selected]?.location;
    if (location) setRotation([-location.coordinates[0], -location.coordinates[1]]);
  }
  function rotate(dx, dy) { setRotation(([x, y]) => [x + dx, Math.max(-85, Math.min(85, y + dy))]); }
  return <section className="ev-globe-panel" aria-label="Geographic evidence view">
    <div className="ev-map-heading"><div><span className="ev-eyebrow">GEOGRAPHIC CONTEXT</span><h1>Procurement watch</h1></div><span className="ev-map-mode">SESSION EVIDENCE</span></div>
    <svg viewBox="0 0 720 680" className="ev-globe" role="group" aria-label="Interactive globe. Drag or use arrow keys to rotate." tabIndex="0"
      onKeyDown={e => { const moves = { ArrowLeft: [-10, 0], ArrowRight: [10, 0], ArrowUp: [0, -10], ArrowDown: [0, 10] }; if (moves[e.key]) { e.preventDefault(); rotate(...moves[e.key]); } }}
      onPointerDown={e => { if (e.target.closest('[data-marker]')) return; drag.current = { x: e.clientX, y: e.clientY }; e.currentTarget.setPointerCapture(e.pointerId); }}
      onPointerMove={e => { if (!drag.current) return; rotate((e.clientX - drag.current.x) * .3, -(e.clientY - drag.current.y) * .3); drag.current = { x: e.clientX, y: e.clientY }; }}
      onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
      <defs><radialGradient id="ev-ocean" cx="38%" cy="30%"><stop stopColor="#162b34"/><stop offset="1" stopColor="#0c1922"/></radialGradient><clipPath id="ev-sphere-clip"><path d={path({ type: 'Sphere' })}/></clipPath></defs>
      <path d={path({ type: 'Sphere' })} fill="url(#ev-ocean)" stroke="#46606a" strokeWidth="1"/>
      <g clipPath="url(#ev-sphere-clip)">
        <path d={path(graticule)} fill="none" stroke="#28404a" strokeWidth=".55"/>
        <path d={path(land)} fill="#29434a" stroke="#567079" strokeWidth=".6"/>
        <path d={path(borders)} fill="none" stroke="#5c737a" strokeWidth=".5"/>
        {mapped.map(r => {
          if (geoDistance(r.location.coordinates, [-rotation[0], -rotation[1]]) > Math.PI / 2) return null;
          const [x, y] = projection(r.location.coordinates);
          return <g key={r.index} data-marker="true" role="button" tabIndex="0" aria-label={`Inspect ${r.label}`} className={`ev-map-marker ${selected === r.index ? 'selected' : ''}`} transform={`translate(${x},${y})`}
            onClick={() => onSelect(r.index)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); onSelect(r.index); } }}>
            <title>{r.label} — {r.location.label}</title><circle r="14" fill="transparent"/><circle r="9" className="ev-marker-ring"/><circle r="3.5" fill="#e3c582"/>
          </g>;
        })}
      </g>
    </svg>
    <div className="ev-map-controls"><button onClick={() => setZoom(z => Math.min(1.65, z + .15))} aria-label="Zoom in">+</button><button onClick={() => setZoom(z => Math.max(.7, z - .15))} aria-label="Zoom out">−</button><button onClick={() => { setRotation([-12, -15]); setZoom(1); }}>Reset view</button><button disabled={!records[selected]?.location} onClick={focus}>Locate selection</button></div>
    <div className="ev-map-caption"><div><i/>{mapped.length} located / {records.length - mapped.length} without coordinates</div><p>{mapped.length ? 'Markers represent supplied delivery coordinates. Select a marker or a record to inspect its evidence.' : 'Import procurement records to begin. The basemap is geographic context; no global feed is connected.'}</p><small>Drag to rotate · Arrow keys supported · Basemap: Natural Earth / world-atlas. Boundaries do not imply endorsement.</small></div>
  </section>;
}
