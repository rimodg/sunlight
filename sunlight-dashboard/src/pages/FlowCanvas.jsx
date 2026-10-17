import {memo,useEffect,useRef} from 'react';
import {flowProgress,globeProjector,routeVector,unitVector} from './flowMotion';

const styles={
 material:{route:'rgba(220,238,255,.20)',trail:'#ffffff',head:'#ffffff',glow:'rgba(255,255,255,.5)'},
 trade:{route:'rgba(238,210,118,.45)',trail:'#ffe38b',head:'#fff5b0',glow:'rgba(255,225,123,.5)'},
 procurement:{route:'rgba(180,224,218,.8)',trail:'#b4e0da',head:'#e6fffa',glow:'rgba(180,224,218,.5)'},
};
function glowSprite(style) {
 const canvas=document.createElement('canvas');canvas.width=canvas.height=48;
 const ctx=canvas.getContext('2d'),gradient=ctx.createRadialGradient(24,24,1,24,24,24);
 gradient.addColorStop(0,style.glow);gradient.addColorStop(.25,style.glow);gradient.addColorStop(1,'rgba(0,0,0,0)');
 ctx.fillStyle=gradient;ctx.fillRect(0,0,48,48);return canvas;
}
function line(ctx, samples, project) {
 let drawing=false;
 for(const sample of samples){const [x,y,depth]=project(sample);if(depth<0){drawing=false;continue}if(drawing)ctx.lineTo(x,y);else{ctx.moveTo(x,y);drawing=true}}
}

function FlowCanvas({links,rotation,zoom,motionAllowed}) {
 const canvas=useRef(null), view=useRef({rotation,zoom}), data=useRef([]), revision=useRef(0);
 // Animation reads refs; it never schedules a React render or restarts on rotation.
 useEffect(()=>{view.current={rotation,zoom};revision.current++},[rotation,zoom]);
 useEffect(()=>{data.current=links.map((link,index)=>({index,kind:link.kind==='material'?'material':link.usd?'trade':'procurement',samples:link.geometry.coordinates.map(unitVector)}));revision.current++},[links]);
 useEffect(()=>{
  const surface=canvas.current,ctx=surface.getContext('2d');
  if(!ctx)return;
  const routes=document.createElement('canvas'),routeContext=routes.getContext('2d');
  const sprites=Object.fromEntries(Object.entries(styles).map(([kind,style])=>[kind,glowSprite(style)]));
  let frame,previous=null,seconds=0,painted=-1,scaleX=1,scaleY=1;
  function resize(){
   const box=surface.getBoundingClientRect(),ratio=Math.min(window.devicePixelRatio||1,2);
   surface.width=routes.width=Math.max(1,Math.round(box.width*ratio));surface.height=routes.height=Math.max(1,Math.round(box.height*ratio));
   scaleX=surface.width/720;scaleY=surface.height/680;painted=-1;
  }
  function paint(){
   const {rotation,zoom}=view.current,scale=300*zoom,project=globeProjector(rotation,scale);
   if(painted!==revision.current){
    routeContext.setTransform(1,0,0,1,0,0);routeContext.clearRect(0,0,routes.width,routes.height);routeContext.setTransform(scaleX,0,0,scaleY,0,0);
    for(const [kind,style] of Object.entries(styles)){
     routeContext.beginPath();for(const flow of data.current)if(flow.kind===kind)line(routeContext,flow.samples,project);
     routeContext.strokeStyle=style.route;routeContext.lineWidth=kind==='material'?.6:1.05;routeContext.setLineDash(kind==='procurement'?[3,3]:[]);routeContext.stroke();
    }
    painted=revision.current;
   }
   ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,surface.width,surface.height);ctx.drawImage(routes,0,0);ctx.setTransform(scaleX,0,0,scaleY,0,0);
   ctx.save();ctx.beginPath();ctx.arc(360,340,scale,0,Math.PI*2);ctx.clip();ctx.lineCap='round';
   for(const [kind,style] of Object.entries(styles)){
    const flows=data.current.filter(f=>f.kind===kind),heads=[];
    ctx.beginPath();
    for(const flow of flows){
     const progress=flowProgress(seconds,flow.index),tail=Math.max(0,progress-.055),samples=[];
     for(let i=0;i<=6;i++)samples.push(routeVector(flow.samples,tail+(progress-tail)*i/6));
     line(ctx,samples,project);
     const point=project(samples[6]);if(point[2]>=0)heads.push(point);
    }
    ctx.strokeStyle=style.trail;ctx.lineWidth=1.65;ctx.stroke();
    for(const [x,y] of heads)ctx.drawImage(sprites[kind],x-10,y-10,20,20);
    ctx.beginPath();for(const [x,y] of heads){ctx.moveTo(x+3,y);ctx.arc(x,y,3,0,Math.PI*2)}ctx.fillStyle=style.head;ctx.fill();
   }
   ctx.restore();
  }
  function tick(now){
   frame=requestAnimationFrame(tick);
   if(document.hidden){previous=null;return}
   if(previous!==null)seconds+=Math.min((now-previous)/1000,.1);
   previous=now;paint();
  }
  resize();const observer=new ResizeObserver(()=>{resize();if(!motionAllowed)paint()});observer.observe(surface);observer.observe(surface.closest('svg'));
  if(motionAllowed)frame=requestAnimationFrame(tick);else paint();
  // Reduced motion still redraws after an explicit drag, filter, zoom or selection.
  let observerId;
  if(!motionAllowed){const redraw=()=>{if(painted!==revision.current)paint();observerId=requestAnimationFrame(redraw)};observerId=requestAnimationFrame(redraw)}
  return ()=>{cancelAnimationFrame(frame);cancelAnimationFrame(observerId);observer.disconnect()};
 },[motionAllowed]);
 return <canvas ref={canvas} className="ev-flow-canvas" aria-hidden="true"/>;
}
export default memo(FlowCanvas);
