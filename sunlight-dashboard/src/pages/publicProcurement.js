export function publicScope(snapshot,country,requestedYear){
 const year=Number(requestedYear || snapshot?.default_year);
 if(!Array.isArray(snapshot?.rows)||!Array.isArray(snapshot?.annual))return null;
 if(country){
  const rows=snapshot.rows.filter(r=>r.code===country.code&&r.year<=year).sort((a,b)=>b.year-a.year);
  const row=rows[0];return row?{...row,countries:1,requestedYear:year,rows:[row]}:null;
 }
 const annual=snapshot.annual.find(a=>a.year===year);if(!annual)return null;
 const rows=snapshot.rows.filter(r=>r.year===year),categories=new Map();
 for(const row of rows)for(const category of row.categories){const value=categories.get(category.name)||{name:category.name,contracts:0,usd:0,countries:0};value.contracts+=category.contracts;value.usd+=category.usd;value.countries++;categories.set(category.name,value)}
 return {...annual,requestedYear:year,rows,categories:[...categories.values()].sort((a,b)=>b.usd-a.usd)};
}
export function publicCountries(snapshot,year){
 const rows=new Map();
 for(const row of snapshot?.rows||[]){if(row.year>Number(year||snapshot.default_year))continue;const previous=rows.get(row.code);if(!previous||previous.year<row.year)rows.set(row.code,row)}
 return rows;
}
export function compactCount(value){return new Intl.NumberFormat('en',{notation:'compact',maximumFractionDigits:1}).format(value)}

export const compactMoney=value=>new Intl.NumberFormat('en',{style:'currency',currency:'USD',notation:'compact',minimumFractionDigits:2,maximumFractionDigits:2}).format(value);
