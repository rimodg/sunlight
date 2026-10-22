import {memo,useEffect,useRef} from 'react';
import {globeProjector} from './flowMotion';

// A steady overlay above trade lights and country badges, not an alert animation.
function ConflictCanvas({points,rotation,zoom}){
 const canvas=useRef(null),view=useRef({points,rotation,zoom}),draw=useRef(null);
 useEffect(()=>{
  const surface=canvas.current,ctx=surface.getContext('2d');if(!ctx)return;
  draw.current=()=>{
   const box=surface.getBoundingClientRect(),ratio=Math.min(devicePixelRatio||1,2);
   const width=Math.max(1,Math.round(box.width*ratio)),height=Math.max(1,Math.round(box.height*ratio));
   if(surface.width!==width||surface.height!==height){surface.width=width;surface.height=height}
   ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,width,height);ctx.setTransform(width/720,0,0,height/680,0,0);
   const {points,rotation,zoom}=view.current,scale=300*zoom,project=globeProjector(rotation,scale);
   ctx.save();ctx.beginPath();ctx.arc(360,340,scale,0,Math.PI*2);ctx.clip();ctx.beginPath();
   for(const point of points){const [x,y,depth]=project(point.vector);if(depth<0)continue;ctx.moveTo(x+1.9,y);ctx.arc(x,y,1.9,0,Math.PI*2)}
   ctx.fillStyle='#d87976';ctx.fill();ctx.strokeStyle='#432c32';ctx.lineWidth=.45;ctx.stroke();ctx.restore();
  };
  draw.current();const observer=new ResizeObserver(()=>draw.current?.());observer.observe(surface.closest('svg'));
  return ()=>{observer.disconnect();draw.current=null};
 },[]);
 useEffect(()=>{view.current={points,rotation,zoom};draw.current?.()},[points,rotation,zoom]);
 return <canvas ref={canvas} className="ev-conflict-canvas" aria-hidden="true"/>;
}
export default memo(ConflictCanvas);
