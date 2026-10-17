import {countryCatalog} from './watchOverview.js';
const countries=new Map(countryCatalog.map(c=>[c.code,c]));
export const armsFamilies={major:'Major conventional arms',small_arms:'Small arms',light_weapons:'Light weapons'};
function side(rows){
 if(!rows.length)return {status:'not_reported',quantity:null,rows};
 if(rows.some(r=>r.quantity===null||!Number.isSafeInteger(r.quantity)||r.quantity<0||r.duplicate_count>1))return {status:'unassessable',quantity:null,rows};
 const quantity=rows.reduce((n,r)=>n+r.quantity,0);
 return {status:Number.isSafeInteger(quantity)?'reported':'unassessable',quantity:Number.isSafeInteger(quantity)?quantity:null,rows};
}
export function armsComparisons(snapshot,year,country=null,family='',category=''){
 const groups=new Map();
 for(const row of snapshot?.rows||[]){
  if(row.year!==Number(year)||(country&&row.exporter!==country.code&&row.importer!==country.code)||(family&&row.family!==family)||(category&&row.category!==category))continue;
  const key=JSON.stringify([row.year,row.exporter,row.importer,row.family,row.category]);
  if(!groups.has(key))groups.set(key,{key,year:row.year,exporter:row.exporter,importer:row.importer,exporter_name:row.exporter_name,importer_name:row.importer_name,family:row.family,category:row.category,exports:[],imports:[]});
  const group=groups.get(key);if(row.direction==='export')group.exports.push(row);else if(row.direction==='import')group.imports.push(row);
 }
 return [...groups.values()].map(g=>{
  const exports=side(g.exports),imports=side(g.imports),comparable=exports.status==='reported'&&imports.status==='reported';
  return {...g,exports,imports,difference:comparable?exports.quantity-imports.quantity:null,status:comparable?exports.quantity===imports.quantity?'equal':'different':exports.status==='unassessable'||imports.status==='unassessable'?'unassessable':'one_sided'};
 }).sort((a,b)=>(a.status==='different'?-1:0)-(b.status==='different'?-1:0)||a.exporter_name.localeCompare(b.exporter_name)||a.importer_name.localeCompare(b.importer_name)||a.category.localeCompare(b.category));
}
export function armsLinks(comparisons){
 // Each relationship appears once, even where both governments declare it.
 const links=new Map();
 for(const row of comparisons){
  const a=countries.get(row.exporter),b=countries.get(row.importer);
  if(!a||!b||a.code===b.code||!([row.exports,row.imports].some(s=>s.status==='reported'&&s.quantity>0)))continue;
  const key=`${a.code}-${b.code}`;
  if(!links.has(key))links.set(key,{kind:'arms',from:a.center,to:b.center,reporter:a,partner:b,year:row.year,label:`${a.name} → ${b.name} · declared arms relationship`});
 }
 return [...links.values()];
}
export function comparisonCounts(rows){return rows.reduce((n,r)=>{n[r.status]++;return n},{equal:0,different:0,one_sided:0,unassessable:0})}
