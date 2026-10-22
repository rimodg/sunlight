import {test} from 'node:test';
import assert from 'node:assert/strict';
import {geoInterpolate,geoOrthographic} from 'd3-geo';
import {FLOW_LAP_SECONDS,flowProgress,globeProjector,routeVector,unitVector} from './flowMotion.js';

test('canvas camera aligns with the globe during global rotation, dragging and country zoom',()=>{
 for(const rotation of [[-12,-15],[91,30],[-120,-65],[170,85]])for(const zoom of [1,5,30]){
  const project=globeProjector(rotation,300*zoom),svg=geoOrthographic().translate([360,340]).scale(300*zoom).rotate(rotation);
  for(const coordinate of [[0,0],[-80,45],[31,-25],[145,80]]){
   const [x,y,depth]=project(unitVector(coordinate)),expected=svg(coordinate);
   assert(Math.abs(x-expected[0])<1e-8);assert(Math.abs(y-expected[1])<1e-8);
   const center=svg.invert([360,340]),view=unitVector(center),point=unitVector(coordinate);
   assert(Math.abs(depth-point.reduce((sum,n,i)=>sum+n*view[i],0))<1e-12);
  }
 }
});
test('cached samples follow the exporter-to-importer great circle, including long dateline and polar routes',()=>{
 for(const [from,to] of [[[0,0],[179,1]],[[-179,20],[179,-20]],[[0,85],[150,80]],[[0,5],[110,-30]]]){
  const interpolate=geoInterpolate(from,to),samples=Array.from({length:129},(_,i)=>unitVector(interpolate(i/128)));
  assert(Math.hypot(...routeVector(samples,0).map((v,i)=>v-unitVector(from)[i]))<1e-12);
  for(const t of [.017,.251,.617,.999,1]){
   const point=routeVector(samples,t),expected=unitVector(interpolate(t));
   assert(Math.hypot(...point.map((v,i)=>v-expected[i]))<3e-7);
  }
 }
});
test('visual speed is frame-rate independent and completes a lap in 1.8 seconds',()=>{
 assert.equal(FLOW_LAP_SECONDS,1.8);
 assert(Math.abs(flowProgress(.9,0)-.5)<1e-12);
 assert.equal(flowProgress(1.8,0),0);
 const source=unitVector([0,0]),destination=unitVector([90,0]);
 const interpolate=geoInterpolate([0,0],[90,0]);
 const samples=Array.from({length:129},(_,i)=>unitVector(interpolate(i/128)));
 const point=routeVector(samples,flowProgress(.45,0));
 // An eastbound source must advance eastward, rather than invert the trade flow.
 assert(point[1]>source[1]&&point[1]<destination[1]);
 assert(Math.abs(Math.atan2(point[1],point[0])*180/Math.PI-22.5)<.0001);
});
