import countries from '../data/countries.json' with { type: 'json' };
export const countryCatalog = [...countries].sort((a,b)=>a.name.localeCompare(b.name));
export const normalized = value => String(value || '').normalize('NFD').replace(/\p{Diacritic}/gu,'').toLowerCase().replace(/[^\p{L}\p{N}]/gu,'');
export function resolveCountry(value) {
  const key = normalized(value);
  if (!key) return null;
  const matches = countryCatalog.filter(c => [c.name,c.official,c.code,c.alpha3,c.numeric,...c.aliases].some(name=>normalized(name)===key));
  return matches.length === 1 ? matches[0] : null;
}
export function matchCountries(value) {
  const key = normalized(value);
  return key ? countryCatalog.filter(c=>[c.name,c.official,c.code,c.alpha3,...c.aliases].some(name=>normalized(name).includes(key))).slice(0,8) : [];
}
export function recordCountry(record) {
  const parties=Array.isArray(record?.parties)?record.parties:[];
  const buyer=parties.find(p=>p?.id && p.id===record?.buyer?.id) || parties.find(p=>Array.isArray(p?.roles)&&p.roles.includes('buyer'));
  return resolveCountry(record?.buyer?.address?.countryName || buyer?.address?.countryName);
}
const list=value=>Array.isArray(value)?value:[];
export const safeURL=value=>{try { const u=new URL(value);return ['https:','http:'].includes(u.protocol)?u.href:null; }catch{return null}};
export function recordDocuments(record) {
  const docs=[...list(record?.documents),...list(record?.tender?.documents),...list(record?.awards).flatMap(a=>list(a?.documents)),...list(record?.contracts).flatMap(c=>[...list(c?.documents),...list(c?.implementation?.documents),...list(c?.implementation?.milestones).flatMap(m=>list(m?.documents))])];
  const unique=new Map();
  for (const doc of docs) if(doc && typeof doc==='object') { const key=String(doc.id || doc.url || JSON.stringify(doc)); if(doc.documentStatus==='deleted') unique.delete(key); else unique.set(key,{...doc,safeURL:safeURL(doc.url)}); }
  return [...unique.values()];
}
export function reportedValues(record) {
  const contracts=list(record?.contracts), awards=list(record?.awards).filter(a=>!['cancelled','unsuccessful'].includes(a?.status));
  const basis=contracts.length?'contract':awards.length?'award':'tender estimate';
  const entries=contracts.length?contracts:awards.length?awards:[record?.tender];
  return entries.map(e=>({amount:e?.value?.amount,currency:e?.value?.currency,basis})).filter(v=>typeof v.amount==='number'&&Number.isFinite(v.amount)&&v.amount>=0&&v.amount<=Number.MAX_SAFE_INTEGER&&/^[A-Z]{3}$/.test(v.currency));
}
export function overview(records, country=null) {
  const scoped=country?records.filter(r=>recordCountry(r.record)?.code===country.code):records;
  const frequencies=new Map();for(const r of records)if(r.record?.ocid)frequencies.set(r.record.ocid,(frequencies.get(r.record.ocid)||0)+1);
  const amounts=new Map(), categories=new Map();
  let documents=0, linked=0, completionLinked=0, missingCompletion=0, duplicates=0, invalid=0, noValues=0, declaredComplete=0,milestones=0,milestonesMet=0,milestonesNotMet=0,milestonesPartial=0;
  const eligible=[];
  for(const r of scoped){
    if(!r.record?.ocid || r.result?.errors?.length){invalid++;continue}
    if(frequencies.get(r.record.ocid)>1){duplicates++;continue}
    const docs=recordDocuments(r.record), hasCompletion=docs.some(d=>d.safeURL&&['completionCertificate','completionReport','deliveryCertificate','handoverCertificate'].includes(d.documentType));
    documents+=docs.length;linked+=docs.filter(d=>d.safeURL).length;
    completionLinked+=Number(hasCompletion);missingCompletion+=Number(!hasCompletion);
    declaredComplete+=Number(list(r.record.contracts).some(c=>c?.status==='complete'));
    for(const contract of list(r.record.contracts)) { const seen=new Set(); for(const [index,milestone] of list(contract?.implementation?.milestones).entries()) { if(!milestone || typeof milestone!=='object')continue; const id=milestone.id??index; if(seen.has(id))continue;seen.add(id);milestones++;milestonesMet+=Number(milestone.status==='met');milestonesNotMet+=Number(milestone.status==='notMet');milestonesPartial+=Number(milestone.status==='partiallyMet'); } }
    const category=['goods','works','services'].includes(r.record.tender?.mainProcurementCategory)?r.record.tender.mainProcurementCategory:'unclassified';
    const row=categories.get(category)||{category,records:0,missingCompletion:0,amounts:new Map()};row.records++;row.missingCompletion+=Number(!hasCompletion);categories.set(category,row);
    const values=reportedValues(r.record);if(!values.length)noValues++;
    for(const value of values){
      const key=`${value.currency}|${value.basis}`;
      for(const map of [amounts,row.amounts]){const item=map.get(key)||{currency:value.currency,basis:value.basis,amount:0,withoutCompletion:0};item.amount+=value.amount;if(!hasCompletion)item.withoutCompletion+=value.amount;map.set(key,item)}
    }
    eligible.push({...r,documents:docs,hasCompletion,category});
  }
  return {scope:country?.name||'Current analysis',records:scoped.length,eligible,documents,linked,completionLinked,missingCompletion,duplicates,invalid,noValues,declaredComplete,milestones,milestonesMet,milestonesNotMet,milestonesPartial,unassigned:records.filter(r=>!recordCountry(r.record)).length,amounts:[...amounts.values()],categories:[...categories.values()].map(c=>({...c,amounts:[...c.amounts.values()]}))};
}
export function tradeLinks(snapshot) {
  if(!Array.isArray(snapshot?.routes))return [];
  const byNumeric=new Map(countryCatalog.map(c=>[Number(c.numeric),c]));
  return snapshot.routes.flatMap(row=>{
    const a=byNumeric.get(row.reporter),b=byNumeric.get(row.partner);
    if(!a||!b||!Number.isFinite(row.usd)||row.usd<=0||row.period!==snapshot.period)return [];
    return [{from:a.center,to:b.center,reporter:a,partner:b,usd:row.usd,period:row.period,reported:row.reported,sourceURL:`${snapshot.source_url}?period=${encodeURIComponent(row.period)}&reporterCode=${encodeURIComponent(row.source_reporter)}&cmdCode=TOTAL&flowCode=X&partnerCode=${encodeURIComponent(row.source_partner ?? row.partner)}&partner2Code=0&customsCode=C00&motCode=0&maxRecords=500`,label:`${row.reporter_name || a.name} → ${row.partner_name || b.name}`}];
  });
}
export const money=(amount,currency)=>{try{return new Intl.NumberFormat('en',{style:'currency',currency,maximumFractionDigits:0}).format(amount)}catch{return `${currency} ${Number(amount).toLocaleString('en',{maximumFractionDigits:0})}`}};
