import test from 'node:test';
import assert from 'node:assert/strict';
import {geoInterpolate,geoOrthographic} from 'd3-geo';
import {flowKind,flowId,flowMeasure,flowDiscrepancies,pickFlow} from './flows.js';
import {armsLinks,armsComparisons} from './arms.js';
const route=(from,to)=>{const lerp=geoInterpolate(from,to);return {from,to,geometry:{coordinates:Array.from({length:129},(_,i)=>lerp(i/128))}}};
test('route selection uses the visible great-circle segment, rejects far side and unrelated points',()=>{
 const link=route([-40,10],[40,10]);const p=geoOrthographic().translate([360,340]).scale(300).rotate([0,0])(geoInterpolate(link.from,link.to)(.5));
 assert.equal(pickFlow([link],[0,0],1,p),link);assert.equal(pickFlow([link],[180,0],1,p),null);assert.equal(pickFlow([link],[0,0],1,[0,0]),null);
});
test('material inspector preserves rounded source shares and does not invent bilateral dollars',()=>{
 const l={kind:'material',from:[0,0],to:[1,1],direction:2,share:1234,product:{code:'2601'},referenceTotal:1e9};assert.match(flowMeasure(l),/12.34% of importer imports/);assert.doesNotMatch(flowMeasure(l),/\$/);assert.equal(flowKind(l),'material');assert.notEqual(flowId(l),flowId({...l,product:{code:'2701'}}));
});
test('arms relationships keep all category evidence and review leads without adding mirrored counts',()=>{
 const r={year:2022,exporter:'DE',importer:'LV',exporter_name:'Germany',importer_name:'Latvia',family:'small_arms',category:'Assault rifles',duplicate_count:1};
 const rows=armsComparisons({rows:[{...r,direction:'export',quantity:4},{...r,direction:'import',quantity:6},{...r,category:'Pistols',direction:'export',quantity:8}]},2022),links=armsLinks(rows);
 assert.equal(links.length,1);assert.equal(links[0].comparisons.length,2);assert.equal(flowDiscrepancies(links[0]).length,1);assert.equal(flowDiscrepancies(links[0])[0].difference,-2);assert.match(flowMeasure(links[0]),/counts kept separate/);
});
