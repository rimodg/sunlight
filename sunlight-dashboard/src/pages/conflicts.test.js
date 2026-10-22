import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {conflictPoints,countryConflictPoints,pickConflictPoint,conflictAge} from './conflicts.js';
import {globeProjector} from './flowMotion.js';
const snapshot=JSON.parse(readFileSync(new URL('../../../code/conflict_snapshot.json',import.meta.url)));

test('only named/nearby locations produce points; repeated source coordinates are grouped without inflating their severity',()=>{
 const points=conflictPoints(snapshot);assert.equal(points.length,658);assert.equal(points.reduce((n,p)=>n+p.events.length,0),1018);
 assert(points.every(p=>p.events.every(e=>[1,2].includes(e.location_precision)&&e.coordinates.join(',')===p.key)));
 for(const type of [1,2,3])assert(conflictPoints(snapshot,String(type)).every(p=>p.events.every(e=>e.type===type)));
 assert.equal(conflictPoints(null).length,0);
});
test('hit tests select visible geographic reference points and exclude points behind the globe',()=>{
 const points=conflictPoints(snapshot),point=points.find(p=>p.events[0].place==='Gaza town');assert(point);
 const rotation=[-point.coordinates[0],-point.coordinates[1]],project=globeProjector(rotation,300);
 const screen=project(point.vector);assert.equal(pickConflictPoint(points,rotation,1,screen)?.key,point.key);
 const behind=[rotation[0]+180,-rotation[1]];assert.equal(pickConflictPoint([point],behind,1,[360,340]),null);
 assert.equal(pickConflictPoint([point],rotation,1,[0,0]),null);
});
test('geographic country selection does not substitute UCDP reporting areas for procurement jurisdictions',()=>{
 // Small clockwise rectangle enclosing Gaza reference points, deliberately named differently from the source area.
 const shape={type:'Polygon',coordinates:[[[34,31],[34,32],[35,32],[35,31],[34,31]]]};
 const scoped=countryConflictPoints(conflictPoints(snapshot),{name:'Selected map territory'},shape);
 assert(scoped.length>0);assert(scoped.some(p=>p.events.some(e=>e.reporting_area==='Israel')));
 assert.equal(countryConflictPoints(scoped,{name:'Small territory'},null).length,0);
 assert.equal(countryConflictPoints(scoped,null,null),scoped);
});
test('freshness uses the observation date, rather than the mirror generation or retrieval date',()=>{
 assert.equal(conflictAge(snapshot,Date.parse('2026-10-17T00:00:00Z')),47);
 assert.equal(conflictAge({source_generated_at:'2026-10-17T00:00:00Z'}),null);
});
