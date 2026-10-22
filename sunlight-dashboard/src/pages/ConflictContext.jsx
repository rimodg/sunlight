import {memo,useEffect,useRef,useState} from 'react';
import {conflictAge,locationPrecision,violenceTypes} from './conflicts';

function EventRows({events}){
 return <div className="ev-table-scroll"><table><thead><tr><th>Place / source ID</th><th>Reported interval</th><th>Violence type</th><th>Precision / reporting area</th></tr></thead><tbody>{events.map(e=><tr key={e.id}><td>{e.place||'Source location'}<small>UCDP {e.id} · {e.coordinates.map(n=>n.toFixed(5)).join(', ')} (lon, lat)</small><details><summary>Reported parties</summary>{e.sides.join(' / ')}</details></td><td>{e.start}{e.end!==e.start?` — ${e.end}`:''}<small>Date precision code {e.date_precision}; {e.event_clarity===2?'aggregated report':'individual report coding'}</small></td><td>{violenceTypes[e.type]}</td><td>{locationPrecision[e.location_precision]}<small>UCDP area: {e.reporting_area}</small></td></tr>)}</tbody></table></div>;
}
function ConflictContext({snapshot,points,country,boundaryAvailable,selection,open,onClose,type,onType}){
 const dialog=useRef(null),[query,setQuery]=useState(''),[page,setPage]=useState(0);
 useEffect(()=>{if(open){setQuery('');setPage(0);dialog.current?.showModal()}else dialog.current?.close()},[open]);
 useEffect(()=>setPage(0),[query,type,country,selection]);
 const age=conflictAge(snapshot);
 const selectedPlaces=[...new Set(selection?.events.map(e=>e.place)||[])];
 const scopedIds=country?new Set(points.flatMap(p=>p.events.map(e=>e.id))):null;
 const records=(selection?selection.events:snapshot?.events||[]).filter(e=>(!type||e.type===Number(type))&&(!scopedIds||scopedIds.has(e.id))&&(!query||`${e.place} ${e.reporting_area} ${e.id} ${e.sides.join(' ')}`.toLowerCase().includes(query.toLowerCase())));
 const rows=records.slice(page*100,(page+1)*100);
 return <dialog ref={dialog} className="ev-country-directory ev-conflict-dialog" aria-label="Conflict observations and sources" onCancel={onClose} onClose={onClose}>
  <div className="ev-directory-heading"><div><p className="ev-eyebrow">CONFLICT & ORGANIZED VIOLENCE / DATED CONTEXT</p><h2>{selection?selectedPlaces.length>1?'Shared source reference point':selection.events[0]?.place||'Recorded location':country?`${country.name} / map context`:'Recorded violence, with its source'}</h2></div><button onClick={onClose} aria-label="Close conflict context">Close ×</button></div>
  <p>{snapshot?.definition||'Conflict source unavailable. No locations have been invented.'}</p>
  {snapshot?.events&&<>
   <div className="ev-conflict-date"><strong>Latest record start: {snapshot.latest_start}</strong><span>{age} days before today · {snapshot.version} · preliminary</span><span>Available start dates: {snapshot.earliest_start} — {snapshot.latest_start}. Report intervals may extend to {snapshot.latest_end}.</span></div>
   <p>Partial source extract. Missing points do not imply peace. Only named or nearby-location references are plotted; broader location estimates remain in the register.</p>
   <div className="ev-conflict-filters"><label>Violence type<select value={type} onChange={e=>onType(e.target.value)}><option value="">All organized violence</option>{Object.entries(violenceTypes).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label><label>Find a location or source record<input type="search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Place, reporting area, actor or event ID"/></label></div>
   <p>{country?`Map-boundary selection: ${country.name}. ${boundaryAvailable?'Counts cover only plotted reference points within the approximate basemap boundary, not a complete national record.':'This basemap has no usable boundary for this country; no country count is inferred.'}`:`${snapshot.record_count.toLocaleString('en')} records in the 2026 extract; ${snapshot.plottable_count.toLocaleString('en')} have location precision 1 or 2, grouped into ${snapshot.location_count} reference points. ${snapshot.omitted_location_count} broader-location records are retained below but not plotted.`}</p>
   <p>{selection?'Selected reference point · ':''}{records.length.toLocaleString('en')} matching source records. Dots have the same small size and steady red color; size and brightness do not rank severity or imply an active front line.</p>
   {selectedPlaces.length>1&&<p>These source records share coordinates but have {selectedPlaces.length} place labels: {selectedPlaces.join('; ')}. A shared reference coordinate does not mean every incident occurred at the same exact site.</p>}
   <EventRows events={rows}/><div className="ev-conflict-pagination"><button disabled={page===0} onClick={()=>setPage(n=>n-1)}>Previous</button><span>{records.length?`${page*100+1}–${Math.min((page+1)*100,records.length)} of ${records.length}`:'No matching observations'}</span><button disabled={(page+1)*100>=records.length} onClick={()=>setPage(n=>n+1)}>Next</button></div>
   <h3>Interpretation</h3><p>{snapshot.interpretation}</p><p>{snapshot.reporting_areas}</p><p>{snapshot.dates}</p>
   <h3>Coverage and provenance</h3><p>{snapshot.coverage}</p><p>{snapshot.geography}</p><p>{snapshot.method}</p><p>UCDP source data, retrieved from a public WorldWatch mirror. SUNLIGHT has not independently recoded the underlying reports. The pinned mirror file is available for inspection.</p><p>Mirror generated: {snapshot.source_generated_at}. SUNLIGHT retrieved: {snapshot.retrieved_date}. Retrieval date is not an event date. This release is a bundled snapshot; refreshing SUNLIGHT does not fetch newer conflict observations.</p>
   <p><a href={snapshot.source_url} target="_blank" rel="noreferrer">UCDP source & codebooks ↗</a> · <a href={snapshot.candidate_url} target="_blank" rel="noreferrer">Candidate release directory ↗</a> · <a href={snapshot.mirror_url} target="_blank" rel="noreferrer">Pinned public mirror ↗</a> · <a href={snapshot.license_url} target="_blank" rel="noreferrer">{snapshot.license} ↗</a> · <a href="/watch-data/conflicts" download="sunlight-conflict-context-2026.json">Download conflict snapshot</a></p><div className="ev-source-reference"><a href={snapshot.source_file.url} target="_blank" rel="noreferrer">Pinned source JSON ↗</a><code>SHA-256 {snapshot.source_file.sha256}</code></div>{snapshot.citations.map(c=><p key={c.url}><a href={c.url} target="_blank" rel="noreferrer">{c.title} ↗</a></p>)}
  </>}
 </dialog>;
}
export default memo(ConflictContext);
