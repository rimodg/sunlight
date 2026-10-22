import {geoContains} from 'd3-geo';
import {globeProjector,unitVector} from './flowMotion.js';

export const violenceTypes={1:'State-based conflict',2:'Non-state conflict',3:'One-sided violence against civilians'};
export const locationPrecision={1:'Named location',2:'Near a named location',3:'Broader local area / centroid',4:'Administrative area / centroid',5:'Broader location',6:'Country-level reference',7:'Uncertain location'};
export function conflictPoints(snapshot,type=''){
 const grouped=new Map();
 for(const event of snapshot?.events||[]){
  if(![1,2].includes(event.location_precision)||(type&&event.type!==Number(type)))continue;
  const key=event.coordinates.join(',');
  const group=grouped.get(key)||{key,coordinates:event.coordinates,vector:unitVector(event.coordinates),events:[]};
  group.events.push(event);grouped.set(key,group);
 }
 return [...grouped.values()];
}
export function countryConflictPoints(points,country,shape){
 if(!country)return points;
 // Do not assign Gaza events to Israel merely because of UCDP's reporting area.
 // Basemap boundaries are approximate; missing small-country geometry is explicit.
 return shape?points.filter(point=>geoContains(shape,point.coordinates)):[];
}
export function pickConflictPoint(points,rotation,zoom,position,radius=6){
 const project=globeProjector(rotation,300*zoom);
 let closest=null,distance=radius;
 for(const point of points){
  const [x,y,depth]=project(point.vector);if(depth<0)continue;
  const candidate=Math.hypot(x-position[0],y-position[1]);
  if(candidate<=distance){closest=point;distance=candidate}
 }
 return closest;
}
export function conflictAge(snapshot,now=Date.now()){
 const time=Date.parse(snapshot?.latest_start+'T00:00:00Z');
 return Number.isFinite(time)?Math.max(0,Math.floor((now-time)/86400000)):null;
}
