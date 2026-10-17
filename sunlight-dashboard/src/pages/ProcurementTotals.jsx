import { memo, useEffect, useMemo, useState } from 'react';
import { money, overview, recordCountry } from './watchOverview';

function ProcurementTotals({records,country,context,origin,onSelect}){
 const data=useMemo(()=>overview(records,country),[records,country]);
 const [open,setOpen]=useState(false),[category,setCategory]=useState('all'),[now,setNow]=useState(Date.now());
 const estimate=context?.annual_estimate;
 useEffect(()=>setCategory('all'),[country]);
 useEffect(()=>{if(!estimate)return;const id=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(id)},[estimate]);
 const year=new Date(now).getUTCFullYear();
 const pace=estimate?estimate.amount*((now-Date.UTC(year,0,1))/(Date.UTC(year+1,0,1)-Date.UTC(year,0,1))):null;
 return <>
  <div className="ev-procurement-pulse">
   <button onClick={()=>setOpen(true)} className="ev-document-counter" aria-label="Open procurement values and categories"><span>{country?`${country.name} / DOCUMENTED`:'DOCUMENTED PROCUREMENT'}</span><strong>{data.amounts.length===1?money(data.amounts[0].amount,data.amounts[0].currency):data.amounts.length?`${data.amounts.length} value series`:'No documented value'}</strong><small>{data.records} records · {data.documents} listed documents ↗</small></button>
   {!country&&<button className="ev-estimate-counter" onClick={()=>setOpen(true)}><span>GLOBAL ANNUAL CONTEXT</span><strong>{estimate?money(pace,estimate.currency):'Source required'}</strong><small>{estimate?`${year} modeled pace · ${estimate.year} annual baseline`:'No live global procurement feed connected'} ↗</small></button>}
  </div>
  {open&&<section className="ev-ledger-panel" aria-label="Procurement values and document coverage">
   <button className="ev-ledger-close" onClick={()=>setOpen(false)} aria-label="Close procurement ledger">Close ×</button><p className="ev-eyebrow">{data.scope.toUpperCase()} / {origin||'NO ANALYZED RECORDS'}</p><h2>Value, documents & completion evidence</h2>
   <p>Totals reflect the current analyzed inputs. Currency and value stage remain separate. Displayed money is rounded; retain the exact evidence packet for calculations.</p>
   <div className="ev-ledger-stats"><div><strong>{data.records}</strong><span>Records supplied</span></div><div><strong>{data.documents}</strong><span>Listed documents</span></div><div><strong>{data.linked}</strong><span>HTTP(S) document links</span></div><div><strong>{data.missingCompletion}</strong><span>Without completion-document links</span></div></div>
   <h3>Procurement categories</h3><div className="ev-category-buttons"><button aria-pressed={category==='all'} onClick={()=>setCategory('all')}>All categories</button>{data.categories.map(c=><button key={c.category} aria-pressed={category===c.category} onClick={()=>setCategory(c.category)}>{c.category} · {c.records}</button>)}</div>
   <div className="ev-table-scroll"><table><thead><tr><th>Category</th><th>Stage</th><th>Recorded value</th><th>On records without completion links</th></tr></thead><tbody>{data.categories.filter(c=>category==='all'||c.category===category).flatMap(c=>c.amounts.length?c.amounts.map(a=><tr key={`${c.category}-${a.currency}-${a.basis}`}><td>{c.category}</td><td>{a.basis}</td><td>{money(a.amount,a.currency)}</td><td>{money(a.withoutCompletion,a.currency)}</td></tr>):[<tr key={c.category}><td>{c.category}</td><td colSpan="3">No usable monetary value</td></tr>])}</tbody></table></div>
   {!data.records&&<p>No analyzed procurement documents in this scope. Missing coverage is not zero national expenditure.</p>}
   <h3>Completion and the documentary gap</h3><p>{data.completionLinked} records have a completion-document link; {data.missingCompletion} do not. {data.declaredComplete} declare a completed contract. A document link or declared status does not independently verify delivery. Amounts without links are an evidence gap, not a calculation of theft or undelivered value.</p>
   <p>{data.milestonesMet} / {data.milestones} implementation milestones are marked met; {data.milestonesNotMet} not met; {data.milestonesPartial} partially met. Remaining statuses are scheduled or unspecified. These are supplied milestone declarations, not independently verified physical completion or a project completion percentage.</p>
   <p className="ev-caption">Aggregation excludes {data.duplicates} records with repeated OCIDs and {data.invalid} records with missing OCIDs or analysis errors. {data.noValues} eligible records have no usable value. Country assignment follows the buyer’s stated country; {data.unassigned} records have no recognized buyer country. Supplier and delivery locations do not change that assignment.</p>
   <h3>Underlying record & document register</h3>{data.eligible.filter(r=>category==='all'||r.category===category).map(r=><article className="ev-ledger-record" key={r.index}><button onClick={()=>{onSelect(r.index);setOpen(false)}}>{r.result.ocid} · {r.label} ↗</button><small>{recordCountry(r.record)?.name||'Buyer country not supplied'} · {r.category}</small>{r.documents.length?r.documents.map((d,i)=><div key={i}>{d.safeURL?<a href={d.safeURL} target="_blank" rel="noreferrer">{d.title||d.id||d.documentType||'Document'} ↗</a>:<span>{d.title||d.id||'Listed document'} · no accessible link</span>}<small>{d.documentType||'Type unspecified'}</small></div>):<p>No documents listed in the supplied record.</p>}</article>)}
   {!country&&<section className="ev-estimate-source"><h3>Worldwide annual context</h3>{estimate?<><p>{money(estimate.amount,estimate.currency)} annual estimate, baseline {estimate.year}. <a href={estimate.source_url} target="_blank" rel="noreferrer">{estimate.source_title} ↗</a></p><p>The counter applies that annual amount uniformly across the current UTC year, updating every second. It is modeled pace, not observed contracts, a current-year forecast, or spending reconciled to this register. It cannot be subtracted from these partial records to infer a worldwide completion gap.</p></>:<p>No annual estimate with source and baseline year is configured. SUNLIGHT leaves this value unavailable rather than generating a growing spending figure. The deployment can supply a source-documented annual estimate separately from analyzed records.</p>}</section>}
  </section>}
 </>;
}

export default memo(ProcurementTotals);
