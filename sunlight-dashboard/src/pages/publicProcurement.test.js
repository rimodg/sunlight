import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {publicScope,publicCountries} from './publicProcurement.js';
import {countryCatalog,resolveCountry} from './watchOverview.js';
const snapshot=JSON.parse(readFileSync(new URL('../../../code/public_procurement_snapshot.json',import.meta.url),'utf8'));
test('published totals use one year and are independent of the analyst session',()=>{
 const scope=publicScope(snapshot,null,2024);assert.equal(scope.usd,4301531960000);assert.equal(scope.contracts,10617058);assert.equal(scope.rows.length,52);
 assert.equal(publicScope(snapshot,null,2023).usd,7457387630000);
});
test('all 250 countries remain selectable, source coverage is a separate fact',()=>{
 assert.equal(countryCatalog.length,250);const available=publicCountries(snapshot,2024);assert.equal(available.size,59);
 assert.equal(publicScope(snapshot,resolveCountry('Ghana'),2024),null);
 assert.equal(publicScope(snapshot,resolveCountry('US'),2024).contracts,1491557);
 assert.equal(publicScope(snapshot,resolveCountry('GB'),2024).usd,6708150000);
});
test('country fallback years remain attached and category slices do not claim full reconciliation',()=>{
 const missing=snapshot.rows.find(r=>r.year<2024&&!snapshot.rows.some(other=>other.code===r.code&&other.year===2024));
 const scope=publicScope(snapshot,resolveCountry(missing.code),2024);assert(scope.year<2024);assert.equal(scope.requestedYear,2024);
 const us=publicScope(snapshot,resolveCountry('US'),2024);assert.notEqual(us.categories.reduce((sum,c)=>sum+c.usd,0),us.usd);
 assert.equal(publicScope(null,null,null),null);
});
