import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { geoContains, geoDistance, geoGraticule10, geoInterpolate, geoOrthographic, geoPath } from 'd3-geo';
import {createPortal} from 'react-dom';
import { feature, mesh } from 'topojson-client';
import atlas from 'world-atlas/countries-110m.json';
import MonetaryAtlas from './MonetaryAtlas';
import {aidLinks,compactUSD,monetaryRows,totalBasis} from './moneyAtlas';
import ProcurementTotals from './ProcurementTotals';
import PublicProcurement from './PublicProcurement';
import CountryDirectory from './CountryDirectory';
import MaterialContributions from './MaterialContributions';
import FlowCanvas from './FlowCanvas';
import SourceCoverage from './SourceCoverage';
import FlowDirectory, {FlowInspector} from './FlowInspector';
import {flowId,flowKind,flowEnds,pickFlow,flowNames} from './flows';
import ArmsContext from './ArmsContext';
import {armsComparisons, armsLinks} from './arms';
import ConflictContext from './ConflictContext';
import {globeProjector,unitVector} from './flowMotion';
import {flowCorridors,corridorContains} from './flowScene';
import {conflictPoints, countryConflictPoints, pickConflictPoint, violenceTypes} from './conflicts';
import {materialLinks, materialScope, originBalanced} from './materials';
import { publicCountries, publicScope } from './publicProcurement';
import { countryCatalog, matchCountries, resolveCountry, recordCountry, overview, tradeLinks, money } from './watchOverview';

const land = feature(atlas, atlas.objects.land);
const borders = mesh(atlas, atlas.objects.countries, (a, b) => a !== b);
const graticule = geoGraticule10();
const countryShapes = feature(atlas, atlas.objects.countries).features;
const countryDatasetURL = new URL('../data/countries.json', import.meta.url).href;
const countryLicenseURL = new URL('../data/COUNTRIES-LICENSE.txt', import.meta.url).href;
const defaultRotation = [-12, -15];
export default function EvidenceGlobe({ records, selected, onSelect, country, onCountry, origin, active=true, onInvestigate,connectionsOpen=false,onConnections,onCloseConnections,onMoney,moneyOpen=false,reviewOverview,onReview,onDelivery }) {
  const [portalReady,setPortalReady]=useState(false);
  useEffect(()=>setPortalReady(true),[]);
  const [rotation, setRotation] = useState(defaultRotation);
  const [zoom, setZoom] = useState(1);
  const cameraRef=useRef({rotation:[...defaultRotation],zoom:1});
  const [hoveredFlow,setHoveredFlow]=useState(null);
  const lastHover=useRef(0);
  const [motionAllowed, setMotionAllowed] = useState(() => !window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const [query, setQuery] = useState('');
  const [searchMessage, setSearchMessage] = useState('');
  const [monetary,setMonetary]=useState(null),[moneyError,setMoneyError]=useState(false),[moneyYear,setMoneyYear]=useState(()=>{const value=new URLSearchParams(location.search).get('money_year');return /^202[0-6]$|^2019$/.test(value||'')?value:''}),[moneyMetric,setMoneyMetric]=useState(()=>{const value=new URLSearchParams(location.search).get('money_measure');return value==='none'?'':value||'goods_exports'}),[hoveredMoney,setHoveredMoney]=useState(null);
  const [moneyRetry,setMoneyRetry]=useState(0);
  const selectedMoney=useMemo(()=>monetary?.layers?.find(l=>l.id===moneyMetric),[monetary,moneyMetric]);
  const moneyPoints=useMemo(()=>monetaryRows(selectedMoney).map(r=>({...r,vector:unitVector(r.countryInfo.center)})),[selectedMoney]);
  const aidFlows=useMemo(()=>aidLinks(monetary,country),[monetary,country]);
  const drawnAid=useMemo(()=>originBalanced(aidFlows.slice().sort((a,b)=>b.usd-a.usd),country?80:70),[aidFlows,country]);
  function chooseMoney(id){setMoneyMetric(id);setFlowLayer(id==='aid'?'aid':id?'observations':'');closeFlow();setHoveredMoney(null)}
  useEffect(()=>{const controller=new AbortController();setMoneyError(false);setMonetary(null);fetch('/watch-data/money'+(moneyYear?'?year='+moneyYear:''),{signal:controller.signal}).then(r=>{if(!r.ok)throw new Error();return r.json()}).then(setMonetary).catch(e=>{if(e.name!=='AbortError')setMoneyError(true)});return()=>controller.abort()},[moneyYear,moneyRetry]);
  useEffect(()=>{const url=new URL(location.href);moneyYear?url.searchParams.set('money_year',moneyYear):url.searchParams.delete('money_year');url.searchParams.set('money_measure',moneyMetric||'none');history.replaceState(null,'',url)},[moneyYear,moneyMetric]);
  useEffect(()=>{if(monetary&&moneyMetric&&moneyMetric!=='aid'&&!monetary.layers.some(l=>l.id===moneyMetric))setMoneyMetric('goods_exports')},[monetary,moneyMetric]);
  const [trade, setTrade] = useState(null);
  const [coverageOpen,setCoverageOpen]=useState(false);
  const [tradeOpen, setTradeOpen] = useState(false);
  const [context, setContext] = useState(null);
  const [published, setPublished] = useState(null);
  const [sourceYear, setSourceYear] = useState(null);
  const [materials, setMaterials] = useState(null);
  const [materialCode, setMaterialCode] = useState('');
  const [flowLayer, setFlowLayer] = useState(()=>new URLSearchParams(location.search).has('money_measure')?(moneyMetric==='aid'?'aid':moneyMetric?'observations':''):'');
  useEffect(()=>{if(moneyOpen&&moneyMetric)setFlowLayer(moneyMetric==='aid'?'aid':'observations')},[moneyOpen,moneyMetric]);
  const [flowsOpen, setFlowsOpen] = useState(false);
  const [flowSelection, setFlowSelection] = useState(null);
  const [arms, setArms] = useState(null);
  const [armsOpen, setArmsOpen] = useState(false);
  const [armsRelationship, setArmsRelationship] = useState(null);
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
  const cameraBeforeTrace = useRef(null);
  const panel = useRef(null), controls = useRef(null), caption = useRef(null);
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
  const closeArms = useCallback(() => {setArmsOpen(false);setArmsRelationship(null)}, []);
  useEffect(()=>{closeFlow()},[armsYear,armsFamily,armsCategory,materialCode,moneyYear]);
  const availableFlows = useMemo(() => [...aidFlows,...scopedTrade,...materialFlows,...declaredArmsLinks,...suppliedLinks], [aidFlows,scopedTrade,materialFlows,declaredArmsLinks,suppliedLinks]);
  const links = useMemo(() => {
    const selectedLinks = suppliedLinks.filter(l => l.recordIndex === selected);
    const otherLinks = suppliedLinks.filter(l => l.recordIndex !== selected);
    const routes = [...drawnAid, ...drawnTrade, ...drawnMaterials, ...drawnArms, ...otherLinks.slice(0, 20), ...selectedLinks.slice(0, 20)];
    const visible=flowCorridors(routes.filter(l=>!flowLayer||flowKind(l)===flowLayer));
    if(flowSelection){const index=visible.findIndex(c=>corridorContains(c,flowSelection));if(index>=0)visible[index]={...flowSelection,members:visible[index].members};else visible.push(flowSelection)}
    return visible.map(link => { const interpolate = geoInterpolate(link.from, link.to); return { ...link, geometry: { type: 'LineString', coordinates: Array.from({ length: 129 }, (_, i) => interpolate(i / 128)) } }; });
  }, [suppliedLinks, drawnAid, drawnTrade, drawnMaterials, drawnArms, selected, flowLayer, flowSelection]);

  const scene=useMemo(()=>({land,borders,graticule,countryShape,country,countries:countryCatalog.map(c=>({...c,vector:unitVector(c.center)})),moneyPoints,conflicts:scopedConflictPoints,records:mapped}),[countryShape,country,moneyPoints,scopedConflictPoints,records]);
  const drawnCounts = useMemo(()=>links.reduce((counts,l)=>{const kind=flowKind(l);counts[kind]=(counts[kind]||0)+1;return counts},{}),[links]);

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
    setFlowSelection(null);cameraBeforeTrace.current=null;
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

  function focus() {
    const location = records[selected]?.location;
    if (location) { setRotation([-location.coordinates[0], -location.coordinates[1]]); }
  }
  function rotate(dx,dy){const [x,y]=cameraRef.current.rotation;const next=[x+dx,Math.max(-85,Math.min(85,y+dy))];if(drag.current?.x!=null)cameraRef.current={...cameraRef.current,rotation:next};setRotation(next)}
  const chooseCountry = useCallback(value => { onCountry(value); setQuery(value.name); setSearchMessage(''); }, [onCountry]);
  function selectConflictObservation(event) {
    if (drag.current?.moved) return;
    const matrix = event.currentTarget.getScreenCTM(); if (!matrix) return;
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
    const observation = pickConflictPoint(scopedConflictPoints, cameraRef.current.rotation, cameraRef.current.zoom, [point.x, point.y],5/Math.hypot(matrix.a,matrix.b));
    if (observation) { event.stopPropagation(); setConflictSelection(observation); setConflictsOpen(true); }
  }
  function traceFlow(link) {
    if(!flowSelection)cameraBeforeTrace.current={rotation:[...cameraRef.current.rotation],zoom:cameraRef.current.zoom};
    setFlowSelection(link);
    if(flowLayer==='observations')setFlowLayer(flowKind(link));
    onConnections?.();
    requestAnimationFrame(()=>document.getElementById('watch-connection-dock')?.scrollTo({top:0,behavior:motionAllowed?'smooth':'auto'}));
    const midpoint=geoInterpolate(link.from,link.to)(.5);
    setRotation([-midpoint[0],-midpoint[1]]);setZoom(Math.min(1.08,Math.max(.95,.70/Math.max(.01,Math.sin(geoDistance(link.from,link.to)/2)))));
  }
  function closeFlow(){setFlowSelection(null);if(cameraBeforeTrace.current){setRotation(cameraBeforeTrace.current.rotation);setZoom(cameraBeforeTrace.current.zoom);cameraBeforeTrace.current=null}}
  function changeFlowLayer(value){setFlowLayer(value);setHoveredFlow(null);closeFlow()}
  function selectMapCountry(event) {
    if (event.target.closest('[data-marker], [data-country]') || drag.current?.moved) return;
    const matrix = event.currentTarget.getScreenCTM(); if (!matrix) return;
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
    const camera=cameraRef.current,currentProjection=geoOrthographic().translate([360,340]).rotate(camera.rotation).scale(300*camera.zoom);
    if (Math.hypot(point.x - 360, point.y - 340) > currentProjection.scale()) return;
    const project=globeProjector(camera.rotation,300*camera.zoom);
    const record=mapped.find(r=>{const p=project(unitVector(r.location.coordinates));return p[2]>=0&&Math.hypot(p[0]-point.x,p[1]-point.y)<7/Math.hypot(matrix.a,matrix.b)});
    if(record){onSelect(record.index);return}
    const monetaryPoint=moneyPoints.find(r=>{const p=project(r.vector);return p[2]>.04&&Math.hypot(p[0]-point.x,p[1]-point.y)<8/Math.hypot(matrix.a,matrix.b)});
    if(monetaryPoint){chooseCountry(monetaryPoint.countryInfo);onMoney?.();requestAnimationFrame(()=>document.getElementById('watch-money-dock')?.scrollTo({top:0}));return}
    const flow=pickFlow(links,camera.rotation,camera.zoom,[point.x,point.y],5/Math.hypot(matrix.a,matrix.b));
    if(flow){traceFlow(flow);return}
    const coordinates = currentProjection.invert([point.x, point.y]);
    const shape = countryShapes.find(s => geoContains(s, coordinates));
    const match = shape && countryCatalog.find(c => c.numeric && c.numeric === String(shape.id).padStart(3, '0'));
    if (match) chooseCountry(match);
  }
  const matches = query && query !== country?.name ? matchCountries(query) : [];
  return <section ref={panel} className="ev-globe-panel" aria-label="Geographic evidence view">
    {(country||flowSelection)&&<div className="ev-camera-scope" role="status">{country?'Country research: '+country.name:'Tracing: '+flowEnds(flowSelection).join(' → ')}</div>}
    <div className="ev-map-heading"><div><span className="ev-eyebrow">GLOBAL WATCH / GEOGRAPHIC CONTEXT</span><h1>Global economic watch</h1><p className="ev-watch-time-basis">Source-dated relationships · direction animation · amounts and source periods in each connection</p><button className="ev-open-money" onClick={onMoney}>Monetary atlas · {moneyMetric?`${compactUSD(moneyMetric==='aid'?monetary?.aid?.total:selectedMoney?.total)} ${selectedMoney?.label||'bilateral aid'}`:'Explore monetary measures'} · {monetary?.layers?.length||'…'} measures ↗</button></div><div className="ev-watch-counters"><PublicProcurement snapshot={published} country={country} year={sourceYear} onYear={setSourceYear} onCountry={chooseCountry}/><MaterialContributions snapshot={materials} country={country} onCountry={onCountry} productCode={materialCode} onProduct={setMaterialCode} links={materialFlows} drawn={drawnCounts.material||0}/><ProcurementTotals records={records} country={country} context={context} origin={origin} onSelect={onSelect}/></div></div>
    <div className="ev-country-search"><form onSubmit={e => { e.preventDefault(); const exact = resolveCountry(query); if (exact) chooseCountry(exact); else setSearchMessage('Choose a matching country below.'); }}><label htmlFor="country-research">Research a country or territory</label><div><input id="country-research" type="search" autoComplete="off" placeholder="Country name or ISO code" value={query} onChange={e => { setQuery(e.target.value); setSearchMessage(''); }}/><button type="submit">Find ↗</button></div></form>{matches.length > 0 && <ul>{matches.map(c => <li key={c.code}><button onClick={() => chooseCountry(c)}>{c.name}<span>{c.code}</span></button></li>)}</ul>}{searchMessage && <p role="status">{searchMessage}</p>}<CountryDirectory snapshot={published} year={sourceYear} onCountry={chooseCountry}/>
      {country && <div className="ev-country-research"><span className="ev-eyebrow">COUNTRY RESEARCH</span><h2>{country.name}</h2><p>{country.official}</p>{!countryShape && <p>Boundary unavailable at this basemap resolution. The map marks a country reference point.</p>}<div className="ev-published-country"><span>PUBLISHED PROCUREMENT / {publicData?.year || 'SOURCE COVERAGE'}</span><strong>{publicData ? money(publicData.usd, 'USD') : 'No published figure'}</strong><p>{publicData ? `${publicData.contracts.toLocaleString('en')} contracts in publisher coverage. Open the published total above for markets and provenance.` : 'This country is included. No spending value is invented where the source has no observation.'}</p></div><div className="ev-country-materials"><span>RAW MATERIALS & PRIMARY INPUTS / {materials?.year || 'SOURCE'}</span><strong>{countryMaterials?.hasObservation ? money(countryMaterials.exports, 'USD') : 'No source observation'}</strong><p>Selected material exports · {countryMaterials?.products.filter(p=>p.exports>0).length || 0} HS4 headings. Open the white total for materials, partners and source coverage.</p></div><div className="ev-country-conflicts"><span>RECORDED VIOLENCE / UCDP 2026 EXTRACT</span><p>{conflicts?.events ? `${scopedConflictPoints.reduce((n,p)=>n+p.events.length,0)} plotted source records at ${scopedConflictPoints.length} reference locations within the map boundary. Coverage is partial; a missing point does not establish peace.` : 'Conflict data unavailable. No location is invented.'}</p><button onClick={()=>{setConflictSelection(null);setConflictsOpen(true)}}>Conflict context & sources ↗</button></div><div className="ev-country-arms"><span>ARMS DECLARATIONS / {armsYear}</span><p>{armsRows.length} declared pair/categories in partial UNROCA mirror coverage. Missing data is unknown.</p><button onClick={()=>setArmsOpen(true)}>Arms reporting & accountability ↗</button></div><div className="ev-country-numbers"><div><strong>{countryData.records}</strong><span>Supplied records</span></div><div><strong>{countryData.documents}</strong><span>Listed documents</span></div><div><strong>{countryData.missingCompletion}</strong><span>Completion-link gaps</span></div><div><strong>{scopedTrade.length}</strong><span>Available trade links</span></div></div>{countryData.amounts.map(a => <p className="ev-country-amount" key={`${a.currency}-${a.basis}`}>{money(a.amount,a.currency)} <small>{a.basis}</small></p>)}<p>{countryData.milestonesMet} / {countryData.milestones} implementation milestones marked met in supplied records.</p><p>Analysis figures cover your supplied records. Published figures come from the cited source dataset; open either total above for its own evidence and coverage.</p>{!countryData.records && <p>No contract-level records have been analyzed for this buyer country in this session. Published aggregates are shown separately above.</p>}<button onClick={() => onCountry(null)}>Return to global watch ↗</button></div>}
    </div>
    {moneyMetric&&monetary&&<div className="ev-money-map-key"><button onClick={onMoney}>{selectedMoney?.label||'Bilateral development assistance'}{country&&selectedMoney?' · '+country.name:''} <strong>{compactUSD(moneyMetric==='aid'?monetary?.aid?.total:country?selectedMoney?.rows?.find(r=>r.country===country.code)?.value:selectedMoney?.total)}</strong><small>{selectedMoney?`${selectedMoney.year} · ${country?'Selected country observation':totalBasis(selectedMoney)}`:`${monetary?.aid?.year} · covered donor-recipient pairs`} · {moneyMetric==='aid'?'Net disbursement relationships':'Country observations · logarithmic absolute sizes'}{country&&selectedMoney?' · Global / covered '+compactUSD(selectedMoney.total):''}</small></button><button aria-label="Clear monetary map measure" onClick={()=>{setMoneyMetric('');setFlowLayer('');setHoveredMoney(null)}}>×</button></div>}
    {portalReady&&document.getElementById('watch-money-dock')&&createPortal(<MonetaryAtlas onRetry={()=>setMoneyRetry(v=>v+1)} reviewOverview={reviewOverview} onReview={onReview} onDelivery={onDelivery} onConnections={()=>{changeFlowLayer('');onConnections?.()}} snapshot={monetary} error={moneyError} year={moneyYear} onYear={setMoneyYear} selected={moneyMetric} onSelected={chooseMoney} country={country} onCountry={value=>{value?chooseCountry(value):onCountry(null);requestAnimationFrame(()=>document.getElementById('watch-money-dock')?.scrollTo({top:0}))}} onTrace={traceFlow} onInvestigate={onInvestigate}/>,document.getElementById('watch-money-dock'))}
    <svg viewBox="0 0 720 680" className="ev-globe" role="group" aria-label="Interactive globe. Drag or use arrow keys to rotate." tabIndex="0" onClick={selectMapCountry} onClickCapture={selectConflictObservation}
      onKeyDown={e => { const moves = { ArrowLeft: [-10, 0], ArrowRight: [10, 0], ArrowUp: [0, -10], ArrowDown: [0, 10] }; if (moves[e.key]) { e.preventDefault(); rotate(...moves[e.key]); } }}
      onPointerDown={e => { if (e.target.closest('[data-marker], [data-country]')) return; drag.current = { x: e.clientX, y: e.clientY, moved: false }; e.currentTarget.setPointerCapture(e.pointerId); }}
      onPointerLeave={()=>{setHoveredFlow(null);setHoveredMoney(null)}} onPointerMove={e => { if (!drag.current || drag.current.x == null){if(performance.now()-lastHover.current<80)return;lastHover.current=performance.now();const matrix=e.currentTarget.getScreenCTM();if(!matrix)return;const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(matrix.inverse());const camera=cameraRef.current;const project=globeProjector(camera.rotation,300*camera.zoom);const point=moneyPoints.find(r=>{const xy=project(r.vector);return xy[2]>.04&&Math.hypot(xy[0]-p.x,xy[1]-p.y)<8/Math.hypot(matrix.a,matrix.b)});setHoveredMoney(point||null);const link=point?null:pickFlow(links,camera.rotation,camera.zoom,[p.x,p.y],5/Math.hypot(matrix.a,matrix.b));setHoveredFlow(old=>old&&link&&flowId(old)===flowId(link)?old:link);return;} rotate((e.clientX - drag.current.x) * .3, -(e.clientY - drag.current.y) * .3); drag.current = { x: e.clientX, y: e.clientY, moved: drag.current.moved || Math.abs(e.movementX) + Math.abs(e.movementY) > 2 }; }}
      onPointerUp={() => { const moved = drag.current?.moved; drag.current = null; if (moved) { drag.current = { moved: true }; setTimeout(() => { drag.current = null; }, 0); } }} onPointerCancel={() => { drag.current = null; }}>
      <title>Global economic relationships. Use country search or the connection register to inspect source evidence.</title>
      <foreignObject x="0" y="0" width="720" height="680" pointerEvents="none" aria-hidden="true">
        <FlowCanvas links={links} rotation={rotation} zoom={zoom} motionAllowed={motionAllowed&&active} selectedId={flowSelection?flowId(flowSelection):null} hoveredId={hoveredFlow?flowId(hoveredFlow):null} cameraRef={cameraRef} dragRef={drag} rotateWorld={!country&&!flowSelection} scene={scene}/>
      </foreignObject>
    </svg>
    {flowSelection&&!connectionsOpen&&<button className="ev-trace-return" onClick={onConnections}>Tracing {flowEnds(flowSelection).join(' → ')} · open evidence ↗</button>}
    {hoveredMoney&&<div className="ev-flow-readout" role="status"><strong>{hoveredMoney.countryInfo.name} · {money(Number(hoveredMoney.value),'USD')}</strong><span>{selectedMoney?.label} · {hoveredMoney.year} · Click for country evidence</span></div>}
    {hoveredFlow&&!flowSelection&&<div className="ev-flow-readout" role="status"><strong>{flowEnds(hoveredFlow).join(' → ')}</strong><span>{flowNames[flowKind(hoveredFlow)]} · {hoveredFlow.period||hoveredFlow.year} · {hoveredFlow.members?.length||1} source records · Click to trace</span></div>}
    {portalReady&&document.getElementById('watch-connection-focus')?createPortal(<FlowInspector onMember={traceFlow} link={flowSelection} materials={materials} onClose={closeFlow} onCountry={chooseCountry} onArms={link=>{setArmsRelationship(link);setArmsOpen(true)}} onRecord={onSelect} onInvestigate={onInvestigate}/>,document.getElementById('watch-connection-focus')):<FlowInspector onMember={traceFlow} link={flowSelection} materials={materials} onClose={closeFlow} onCountry={chooseCountry} onArms={link=>{setArmsRelationship(link);setArmsOpen(true)}} onRecord={onSelect} onInvestigate={onInvestigate}/>}
    <SourceCoverage open={coverageOpen} onClose={()=>setCoverageOpen(false)} published={published} materials={materials} arms={arms} conflicts={conflicts} trade={trade} monetary={monetary} onMoney={onMoney}/>
    {portalReady&&document.getElementById('watch-connection-dock')?createPortal(<FlowDirectory embedded links={availableFlows} drawn={links.length} open={connectionsOpen} onClose={onCloseConnections} onSelect={traceFlow} layer={flowLayer} onLayer={changeFlowLayer}/>,document.getElementById('watch-connection-dock')):<FlowDirectory links={availableFlows} drawn={links.length} open={flowsOpen} onClose={()=>setFlowsOpen(false)} onSelect={traceFlow} layer={flowLayer} onLayer={changeFlowLayer}/>}

    <div className="ev-flow-legend" aria-label="Flow legend"><span><i style={{background:'#93d1a4'}}/>Sage → net aid ({monetary?.aid?.year||'source'})</span><span><i className="gold"/>Teal → goods exports (2023)</span><span><i className="white"/>Pale → material subset ({materials?.year || 'source'})</span><button className="ev-conflict-legend" onClick={()=>{setConflictSelection(null);setConflictsOpen(true)}} aria-label="Open conflict observations"><i className="red"/>Red · {conflicts?.latest_start ? 'recorded violence (Aug 2026)' : conflicts ? 'conflict source unavailable' : 'loading conflict context'} ↗</button><button className="ev-arms-legend" onClick={()=>setArmsOpen(true)} aria-label="Open arms reporting and accountability"><i className="blue"/>Indigo → arms declarations ({armsYear}) ↗</button>{(armsFamily || armsCategory) && <button onClick={()=>{setArmsFamily('');setArmsCategory('')}}>Arms category filter · clear ×</button>}{conflictType && <button onClick={()=>changeConflictType('')}>{violenceTypes[conflictType]} · clear filter ×</button>}{materialCode && <button onClick={()=>setMaterialCode('')}>HS {materialCode} · clear filter ×</button>}</div><div ref={controls} className="ev-map-controls"><button onClick={()=>setCoverageOpen(true)}>Coverage & source periods ↗</button><button onClick={()=>{if(flowLayer==='observations')setFlowLayer('');onConnections?onConnections():setFlowsOpen(true)}}>Explore connections ↗</button><select aria-label="Visible flow layer" value={flowLayer} onChange={e=>changeFlowLayer(e.target.value)}><option value="">All flow layers</option><option value="observations">Country monetary observations</option>{Object.entries(flowNames).map(([v,n])=><option key={v} value={v}>{n}</option>)}</select><button onClick={() => setZoom(z => Math.min(45, z * 1.2))} aria-label="Zoom in">+</button><button onClick={() => setZoom(z => Math.max(.7, z / 1.2))} aria-label="Zoom out">−</button>{flowSelection&&<button onClick={closeFlow}>Clear trace ×</button>}<button onClick={() => { onCountry(null); setFlowSelection(null); setRotation(defaultRotation); setZoom(1); }}>Global view</button><button disabled={!records[selected]?.location} onClick={focus}>Locate record</button><button onClick={() => setTradeOpen(value => !value)}>Trade data & sources ↗</button></div>
    {tradeOpen && <section className="ev-trade-panel" aria-label="Trade data and sources"><button className="ev-ledger-close" onClick={() => setTradeOpen(false)}>Close sources ×</button><p className="ev-eyebrow">UN COMTRADE / {trade?.period || 'ANNUAL DATA'}</p><h2>Trade, with its source attached.</h2><p>{trade?.coverage || 'Connecting to the public trade source. No illustrative routes are displayed.'}</p><p>Status: {trade?.status || 'Loading'} · Retrieved: {trade?.fetched_at || 'No successful retrieval'} · {scopedTrade.length} bilateral links available{scopedTrade.length > 80 ? ' / 80 drawn, balanced by available exporter' : ''}.</p><p>Directional connections link reporting and partner country reference points. They are schematic relationships, not tracked ships or actual transport paths. The animation indicates direction; it does not encode money or shipment volume. Trade values are separate from procurement values.</p>{trade?.errors?.length > 0 && <p>{trade.errors.length} reporting-source requests failed. Missing routes do not imply absent trade.</p>}<div className="ev-table-scroll"><table><thead><tr><th>Reporter → partner</th><th>Period</th><th>Export value (USD)</th><th>Source</th><th>Reported flag</th></tr></thead><tbody>{scopedTrade.map((l,i) => <tr key={i}><td>{l.label}</td><td>{l.period}</td><td>{money(l.usd,'USD')}</td><td><a href={l.sourceURL} target="_blank" rel="noreferrer">Source query ↗</a></td><td>{l.reported === true ? 'true' : l.reported === false ? 'false / source aggregate' : 'Not supplied'}</td></tr>)}</tbody></table></div><p className="ev-caption">Country reference points: world-countries 5.1.0, ODbL. <a href="https://github.com/mledoze/countries" target="_blank" rel="noreferrer">Dataset source ↗</a> · <a href={countryDatasetURL} download="sunlight-country-catalog.json">Download country catalog</a> · <a href={countryLicenseURL} target="_blank" rel="noreferrer">ODbL license</a></p></section>}
    <ArmsContext relationship={armsRelationship} snapshot={arms} country={country} open={armsOpen} onClose={closeArms} year={armsYear} onYear={setArmsYear} family={armsFamily} onFamily={setArmsFamily} category={armsCategory} onCategory={setArmsCategory}/><ConflictContext snapshot={conflicts} points={scopedConflictPoints} country={country} boundaryAvailable={Boolean(countryShape)} selection={conflictSelection} open={conflictsOpen} onClose={closeConflicts} type={conflictType} onType={changeConflictType}/><div ref={caption} className="ev-map-caption"><div><i/>{countryCatalog.length} countries & territories · {publishedCountries.size} with published observations at or before {sourceYear || published?.default_year || 'source year'} · {scopedTrade.length} goods trade links · {aidFlows.length} aid pairs ({drawnCounts.aid||0} corridors) · {materialFlows.length.toLocaleString('en')} material links ({drawnCounts.material||0} corridors) · {scopedConflictPoints.length} conflict reference points · {declaredArmsLinks.length} declared arms relationships ({drawnCounts.arms||0} corridors)</div><p>Country reference points remain included where source coverage is missing. Corridors combine drawn relationships with matching endpoints, layer and source period; source records remain separate in the register. Pale directional connections show selected material exports from CEPII BACI, {materials?.year || 'source year'}. {trade?.status === 'unavailable' ? 'The trade connection is unavailable; published procurement totals remain available.' : 'Teal directional connections use dated UN Comtrade data, with values and coverage in sources.'}</p><p className="ev-conflict-caption">Red points: dated, partial UCDP candidate observations; latest record start {conflicts?.latest_start || 'unavailable'}. Open red context for precision, coverage and sources. Co-location alone does not establish stolen funds. Thin connections show source → destination; click a line or explore the register to inspect its evidence. Indigo connections: historical UNROCA declarations, not untraced recoveries. No live tracking or global diversion total is implied.</p><small>{!motionAllowed ? 'System reduced-motion preference active' : country ? 'Country research · rotation held' : flowSelection ? 'Connection research · rotation held' : 'West → east · 3 min / turn (accelerated)'} · Natural Earth boundaries do not imply endorsement.</small></div>
  </section>;
}
