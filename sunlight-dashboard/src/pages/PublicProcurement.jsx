import {memo,useMemo,useState} from 'react';
import {money,resolveCountry} from './watchOverview';
import {publicScope,compactMoney} from './publicProcurement';

function PublicProcurement({snapshot,country,year,onYear,onCountry}){
 const [open,setOpen]=useState(false);
 const hasSnapshot=Array.isArray(snapshot?.rows)&&Array.isArray(snapshot?.years)&&Array.isArray(snapshot?.annual);
 const data=useMemo(()=>publicScope(snapshot,country,year),[snapshot,country,year]);
 return <>
  <button className="ev-public-counter" onClick={()=>setOpen(true)} aria-label="Open published procurement totals"><span>{country?`${country.name} / PUBLISHED PROCUREMENT (USD)`:'PUBLISHED PROCUREMENT / USD'}</span><strong>{data?compactMoney(data.usd):hasSnapshot?'No published figure':snapshot?'Public data unavailable':'Loading public data'}</strong><small>{data?`${data.contracts.toLocaleString('en')} contracts · ${data.countries} ${data.countries===1?'country':'countries'} · ${data.year}`:'Country remains included; source coverage is separate'} ↗</small></button>
  {open&&<section className="ev-ledger-panel ev-public-ledger" aria-label="Published procurement totals and sources"><button className="ev-ledger-close" onClick={()=>setOpen(false)} aria-label="Close published totals">Close ×</button><p className="ev-eyebrow">PUBLISHED AGGREGATES / {data?.year||year||'SOURCE'}</p><h2>{country?.name||'Procurement across covered countries'}</h2>
   <p>Publisher: {snapshot?.publisher||'Source unavailable'}. These are source-published aggregates, separate from your analyzed records and SUNLIGHT’s findings.</p>
   {hasSnapshot&&<><label htmlFor="public-procurement-year">Source year</label><select id="public-procurement-year" value={year||snapshot.default_year} onChange={e=>onYear(Number(e.target.value))}>{snapshot.years.map(y=><option key={y} value={y}>{y}</option>)}</select><p>{snapshot.coverage}</p></>}
   {data?<><div className="ev-ledger-stats"><div><strong>{money(data.usd,'USD')}</strong><span>Published contract value / {data.year}</span></div><div><strong>{data.contracts.toLocaleString('en')}</strong><span>Source contract count</span></div><div><strong>{data.countries}</strong><span>Countries in this selection</span></div></div>{country&&data.year!==Number(year||snapshot.default_year)&&<p>Latest available for this country at or before the selected year: {data.year}. It is not a {year} figure.</p>}
    <h3>Published procurement markets</h3><p>{snapshot.category_coverage}</p><div className="ev-table-scroll"><table><thead><tr><th>Market</th><th>Published value (USD)</th><th>Contracts</th></tr></thead><tbody>{data.categories.map(c=><tr key={c.name}><td>{c.name}</td><td>{money(c.usd,'USD')}</td><td>{c.contracts.toLocaleString('en')}</td></tr>)}</tbody></table></div>
    {!country&&<><h3>Country register / {data.year}</h3><div className="ev-table-scroll"><table><thead><tr><th>Country</th><th>Published value (USD)</th><th>Contracts</th></tr></thead><tbody>{[...data.rows].sort((a,b)=>b.usd-a.usd).map(r=><tr key={r.code}><td><button onClick={()=>{const c=resolveCountry(r.code);if(c){onCountry(c);setOpen(false)}}}>{r.name} ↗</button></td><td>{money(r.usd,'USD')}</td><td>{r.contracts.toLocaleString('en')}</td></tr>)}</tbody></table></div></>}
   </>:<p>No published procurement amount is present for this country and source period. It is included on the globe; no zero expenditure or estimated amount is assigned to it.</p>}
   {hasSnapshot&&<><h3>Provenance and calculation</h3><p>{snapshot.method}</p><p>{snapshot.value_precision}</p><p>Source commit: {snapshot.source_commit_date}. Snapshot retrieved: {snapshot.retrieved_date}. Publication year and procurement observation year differ.</p>{snapshot.source_files.map(f=><div className="ev-source-reference" key={f.name}><a href={f.url} target="_blank" rel="noreferrer">{f.name} / pinned source ↗</a><code>SHA-256 {f.sha256}</code></div>)}<p>{snapshot.completion}</p><p>This snapshot contains aggregate counts and values, not the underlying contract documents. Completion gaps and SUNLIGHT findings remain available only for records and evidence actually supplied for analysis.</p></>}
  </section>}
 </>;
}
export default memo(PublicProcurement);
