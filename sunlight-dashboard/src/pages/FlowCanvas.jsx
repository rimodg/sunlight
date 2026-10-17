import {memo,useEffect,useRef} from 'react';
import {flowId,flowKind,flowColors} from './flows';
import {flowProgress,globeProjector,routeVector,unitVector} from './flowMotion';

const styles={
 material:{head:'#ffffff',glow:'rgba(255,255,255,.5)'},
 trade:{head:'#fff5b0',glow:'rgba(255,225,123,.5)'},
 arms:{head:'#356cba',glow:'rgba(83,139,222,.6)'},
 procurement:{head:'#e6fffa',glow:'rgba(180,224,218,.5)'},
};
function glowSprite(style) {
 const canvas=document.createElement('canvas');canvas.width=canvas.height=48;
 const ctx=canvas.getContext('2d'),gradient=ctx.createRadialGradient(24,24,1,24,24,24);
 gradient.addColorStop(0,style.glow);gradient.addColorStop(.25,style.glow);gradient.addColorStop(1,'rgba(0,0,0,0)');
 ctx.fillStyle=gradient;ctx.fillRect(0,0,48,48);return canvas;
}

function FlowCanvas({links,rotation,zoom,motionAllowed,selectedId}) {
 const canvas=useRef(null), view=useRef({rotation,zoom,selectedId}), data=useRef([]), revision=useRef(0);
 // Animation reads refs; it never schedules a React render or restarts on rotation.
 useEffect(()=>{view.current={rotation,zoom,selectedId};revision.current++},[rotation,zoom,selectedId]);
 useEffect(()=>{data.current=links.map((link,index)=>({index,id:flowId(link),kind:flowKind(link),samples:link.geometry.coordinates.map(unitVector)}));revision.current++},[links]);
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
   const {rotation,zoom,selectedId}=view.current,scale=300*zoom,project=globeProjector(rotation,scale);
   if(painted!==revision.current){
    routeContext.setTransform(1,0,0,1,0,0);routeContext.clearRect(0,0,routes.width,routes.height);routeContext.setTransform(scaleX,0,0,scaleY,0,0);
    routeContext.save();routeContext.beginPath();routeContext.arc(360,340,scale,0,Math.PI*2);routeContext.clip();
    const trace=flow=>{let drawing=false;const stride=zoom<=1.5?4:zoom<=3?2:1;for(let i=0;i<flow.samples.length;i+=stride){const [x,y,depth]=project(flow.samples[i]);if(depth<0){drawing=false;continue}if(drawing)routeContext.lineTo(x,y);else{routeContext.moveTo(x,y);drawing=true}}};
    for(const kind of Object.keys(styles)){
     routeContext.beginPath();for(const flow of data.current)if(flow.kind===kind&&flow.id!==selectedId)trace(flow);
     routeContext.globalAlpha=selectedId ? .07 : .23;routeContext.strokeStyle=flowColors[kind];routeContext.lineWidth=.55;routeContext.stroke();
    }
    const flow=data.current.find(f=>f.id===selectedId);
    if(flow){
     routeContext.globalAlpha=1;routeContext.strokeStyle=flowColors[flow.kind];routeContext.lineWidth=1.5;routeContext.beginPath();trace(flow);routeContext.stroke();
      routeContext.globalAlpha=1;
      const start=project(flow.samples[0]),end=project(flow.samples.at(-1));
      if(start[2]>=0){routeContext.beginPath();routeContext.arc(start[0],start[1],4,0,Math.PI*2);routeContext.fillStyle=flowColors[flow.kind];routeContext.fill()}
      if(end[2]>=0){routeContext.beginPath();routeContext.arc(end[0],end[1],5.5,0,Math.PI*2);routeContext.stroke()}
      const a=project(routeVector(flow.samples,.69)),b=project(routeVector(flow.samples,.71));
      if(a[2]>=0&&b[2]>=0){const angle=Math.atan2(b[1]-a[1],b[0]-a[0]);routeContext.beginPath();routeContext.moveTo(b[0]-6*Math.cos(angle-.5),b[1]-6*Math.sin(angle-.5));routeContext.lineTo(b[0],b[1]);routeContext.lineTo(b[0]-6*Math.cos(angle+.5),b[1]-6*Math.sin(angle+.5));routeContext.stroke()}
    }
    routeContext.restore();painted=revision.current;
   }
   ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,surface.width,surface.height);ctx.drawImage(routes,0,0);ctx.setTransform(scaleX,0,0,scaleY,0,0);
   ctx.save();ctx.beginPath();ctx.arc(360,340,scale,0,Math.PI*2);ctx.clip();ctx.lineCap='round';
   for(const [kind,style] of Object.entries(styles)){
    const flows=data.current.filter(f=>f.kind===kind),heads=[];
    for(const flow of flows){
     const point=project(routeVector(flow.samples,flowProgress(seconds,flow.index)));
     if(point[2]>=0)heads.push([...point,flow.id===selectedId]);
    }
    const radius=kind==='arms'?1.9:2.6;
    ctx.globalAlpha=selectedId ? .35 : 1;
    for(const [x,y] of heads)ctx.drawImage(sprites[kind],x-7,y-7,14,14);
    ctx.beginPath();for(const [x,y] of heads){ctx.moveTo(x+radius,y);ctx.arc(x,y,radius,0,Math.PI*2)}ctx.fillStyle=style.head;ctx.fill();
    ctx.globalAlpha=1;for(const [x,y,,chosen] of heads)if(chosen){ctx.drawImage(sprites[kind],x-9,y-9,18,18);ctx.beginPath();ctx.arc(x,y,radius+.6,0,Math.PI*2);ctx.fill()}
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
