import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {materialScope,materialLinks,originBalanced,routeShare} from './materials.js';
import {resolveCountry} from './watchOverview.js';
const snapshot=JSON.parse(readFileSync(new URL('../../../code/materials_snapshot.json',import.meta.url)));

test('actual national and selected-product totals reconcile with the covered world without treating missing observations as zeros',()=>{
 const world=materialScope(snapshot),ghana=materialScope(snapshot,resolveCountry('Ghana'));
 assert.equal(world.exports,snapshot.total_usd);assert.equal(ghana.exports,23231917535);
 assert.equal(ghana.share,ghana.exports/world.exports);assert(ghana.goodsShare>0&&ghana.goodsShare<=1);
 const gold=materialScope(snapshot,resolveCountry('Ghana'),'7108');assert.equal(gold.exports,15627290981);assert(gold.worldTotal>gold.exports);
 assert.equal(materialScope(snapshot,resolveCountry('Antarctica')).hasObservation,false);
 assert.equal(materialScope(null),null);
});

test('inbound source shares are drawn from their actual exporter toward the importer with the correct denominator',()=>{
 const data={...snapshot,routes:[['GHA','CHE','7108',2300,-1,1000000],['GHA','CHE','7108',5600,1,5000000],['COD','CHN','2603',4200,-1,6000000]]};
 const links=materialLinks(data);assert.equal(links.length,2);
 const copper=links.find(l=>l.product.code==='2603');assert.deepEqual(copper.from,resolveCountry('COD').center);assert.deepEqual(copper.to,resolveCountry('CHN').center);assert.match(routeShare(copper),/China imports/);assert.equal(copper.usd,undefined);
 const gold=links.find(l=>l.product.code==='7108');assert.equal(gold.direction,1);assert.equal(gold.share,5600);assert.match(routeShare(gold),/Ghana exports/);
 assert.equal(materialLinks(data,resolveCountry('COD'),'7108').length,0);
});

test('global map draws a route for every available exporting economy before filling its remaining route budget',()=>{
 const links=materialLinks(snapshot),drawn=originBalanced(links);
 const origins=new Set(links.map(l=>l.reporter.code));assert.equal(origins.size,204);
 assert.equal(drawn.length,240);assert.equal(new Set(drawn.map(l=>l.reporter.code)).size,204);
 assert(drawn.some(l=>l.reporter.code==='GH'));assert(drawn.some(l=>l.reporter.code==='CD'));assert(drawn.some(l=>l.reporter.code==='ZM'));
 assert.equal(materialLinks(snapshot,resolveCountry('Ghana')).every(l=>l.reporter.code==='GH'||l.partner.code==='GH'),true);
});
