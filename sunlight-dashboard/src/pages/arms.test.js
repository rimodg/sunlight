import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {armsComparisons,armsLinks,comparisonCounts} from './arms.js';
const row=(direction,quantity,extra={})=>({id:direction+quantity,year:2022,exporter:'DE',importer:'LV',exporter_name:'Germany',importer_name:'Latvia',family:'small_arms',category:'4. Assault rifles',direction,quantity,duplicate_count:1,...extra});
test('mirrored declarations are compared, not added, and negative differences retain their sign',()=>{
 const rows=armsComparisons({rows:[row('export',2330),row('import',5753)]},2022);
 assert.equal(rows.length,1);assert.equal(rows[0].difference,-3423);assert.equal(rows[0].status,'different');assert.equal(armsLinks(rows).length,1);
});
test('missing, unknown and repeated-source declarations cannot become lost-weapon or zero counts',()=>{
 for(const [input,status] of [[ [row('export',8)],'one_sided'],[[row('export',null),row('import',8)],'unassessable'],[[row('export',8,{duplicate_count:2}),row('import',8)],'unassessable']]){
  const [comparison]=armsComparisons({rows:input},2022);assert.equal(comparison.status,status);assert.equal(comparison.difference,null);
 }
 const [zero]=armsComparisons({rows:[row('export',0),row('import',0)]},2022);assert.equal(zero.status,'equal');assert.equal(zero.difference,0);assert.equal(armsLinks([zero]).length,0);
});
test('year, category, family, direction and country remain separate',()=>{
 const rows=[row('export',2),row('import',2,{year:2021}),row('import',2,{category:'1. Revolvers and self-loading pistols'}),row('import',2,{family:'light_weapons'}),row('export',2,{exporter:'US'})];
 assert.equal(armsComparisons({rows},2022).length,4);assert(armsComparisons({rows},2022).every(r=>r.difference===null));
 assert.equal(armsComparisons({rows},2022,{code:'DE'},'small_arms','4. Assault rifles').length,1);
});
test('published snapshot comparison coverage is reproducible, with no double counting across reports',()=>{
 const s=JSON.parse(fs.readFileSync(new URL('../../../code/arms_snapshot.json',import.meta.url)));
 const comparisons=armsComparisons(s,2022);
 assert.deepEqual(comparisonCounts(comparisons),{equal:15,different:31,one_sided:1234,unassessable:112});
 assert.equal(armsLinks(comparisons).length,678);assert.equal(new Set(armsLinks(comparisons).map(l=>l.label)).size,678);
 const sample=comparisons.find(r=>r.exporter==='DE'&&r.importer==='LV'&&r.category==='4. Assault rifles');assert.equal(sample.difference,-3423);
 assert.equal(armsComparisons(s,2026).length,0);
});
