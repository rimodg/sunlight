// Visual time only: never a claim about shipment speed, value or observation year.
export const FLOW_LAP_SECONDS = 1.8;
const radians = Math.PI / 180;
export function unitVector([longitude, latitude]) {
 const lon=longitude*radians, lat=latitude*radians, cos=Math.cos(lat);
 return [cos*Math.cos(lon),cos*Math.sin(lon),Math.sin(lat)];
}
export function globeProjector(rotation, scale) {
 const lon=rotation[0]*radians, lat=rotation[1]*radians;
 const a=Math.cos(lon), b=Math.sin(lon), c=Math.cos(lat), d=Math.sin(lat);
 // Same longitude-then-latitude rotation as d3-geo's orthographic camera.
 return ([x,y,z])=>{
  const forward=x*a-y*b, right=x*b+y*a;
  return [360+scale*right,340-scale*(z*c+forward*d),forward*c-z*d];
 };
}
export function routeVector(samples, progress) {
 const index=Math.max(0,Math.min(1,progress))*(samples.length-1);
 const start=Math.floor(index), end=Math.min(start+1,samples.length-1), t=index-start;
 const a=samples[start], b=samples[end];
 const x=a[0]+(b[0]-a[0])*t,y=a[1]+(b[1]-a[1])*t,z=a[2]+(b[2]-a[2])*t;
 const length=Math.hypot(x,y,z);
 return [x/length,y/length,z/length];
}
export function flowProgress(seconds,index,duration=FLOW_LAP_SECONDS) { return (seconds/duration+index*.381966)%1; }
