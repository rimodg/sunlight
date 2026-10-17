import {countryCatalog} from './watchOverview.js';

const countries = new Map(countryCatalog.map(c=>[c.alpha3,c]));
export function materialScope(snapshot,country=null,productCode='') {
 if(!Array.isArray(snapshot?.rows)||!Array.isArray(snapshot?.products))return null;
 const rows=snapshot.rows.filter(r=>(!country||r[0]===country.alpha3)&&(!productCode||r[1]===productCode));
 const worldRows=snapshot.rows.filter(r=>!productCode||r[1]===productCode);
 const worldTotal=worldRows.reduce((sum,r)=>sum+r[2],0);
 const countryValues=new Map(),productValues=new Map();
 for(const [iso,code,exports,imports] of rows){
  const c=countryValues.get(iso)||{country:countries.get(iso),iso,exports:0,imports:0};c.exports+=exports;c.imports+=imports;countryValues.set(iso,c);
  const p=productValues.get(code)||{...snapshot.products.find(p=>p.code===code),exports:0,imports:0};p.exports+=exports;p.imports+=imports;productValues.set(code,p);
 }
 const exports=rows.reduce((sum,r)=>sum+r[2],0),imports=rows.reduce((sum,r)=>sum+r[3],0);
 const goods=country?snapshot.country_goods_exports?.[country.alpha3]:null;
 return {exports,imports,worldTotal,hasObservation:rows.length>0,share:worldTotal?exports/worldTotal:null,goodsShare:goods>0?exports/goods:null,
  countries:[...countryValues.values()].sort((a,b)=>b.exports-a.exports),products:[...productValues.values()].sort((a,b)=>b.exports-a.exports)};
}

export function materialLinks(snapshot, country=null, productCode='') {
 if(!Array.isArray(snapshot?.routes))return [];
 const products=new Map(snapshot.products.map(p=>[p.code,p]));
 const unique=new Map();
 for(const [exporter,importer,code,share,direction,total] of snapshot.routes){
  if(productCode&&code!==productCode)continue;
  if(country&&exporter!==country.alpha3&&importer!==country.alpha3)continue;
  const a=countries.get(exporter),b=countries.get(importer),product=products.get(code);
  if(!a||!b||!product)continue;
  const key=`${exporter}-${importer}-${code}`;
  if(unique.has(key)&&direction!==1)continue;
  unique.set(key,{kind:'material',from:a.center,to:b.center,reporter:a,partner:b,product,period:snapshot.year,share,direction,referenceTotal:total,
   // Ranking proxy only; deliberately never presented as an exact bilateral value.
   rankValue:total*share/10000,label:`${a.name} → ${b.name} · ${product.name} (HS ${code})`});
 }
 return [...unique.values()].sort((a,b)=>b.rankValue-a.rankValue||a.label.localeCompare(b.label));
}

// Include each available exporting economy before allocating additional routes.
// Input is ranked by value; this changes map legibility, never source statistics.
export function originBalanced(links,limit=240) {
 const origins=new Set(),first=[],rest=[];
 for(const link of links){const key=link.reporter?.code||link.from.join(',');if(origins.has(key))rest.push(link);else{origins.add(key);first.push(link)}}
 return [...first,...rest].slice(0,limit);
}
export const percent=value=>value==null?'Not available':new Intl.NumberFormat('en',{style:'percent',maximumFractionDigits:2}).format(value);
export const routeShare=link=>`${(link.share/100).toFixed(2)}% of ${link.direction===1?link.reporter.name+' exports':link.partner.name+' imports'} for HS ${link.product.code} (rounded)`;
