import {globeProjector,unitVector} from './flowMotion.js';
import {money} from './watchOverview.js';
export const flowKind=l=>l.kind==='aid'?'aid':l.kind==='arms'?'arms':l.kind==='material'?'material':l.usd?'trade':'procurement';
export const flowNames={aid:'Development assistance · net',trade:'Goods exports',material:'Material exports',arms:'Arms declarations',procurement:'Supplied record link'};
export const flowColors={aid:'#93d1a4',trade:'#5fcac4',material:'#d8e7ed',arms:'#a5b4ef',procurement:'#edcc82'};
export const flowId=l=>JSON.stringify([flowKind(l),l.from,l.to,l.product?.code,l.period||l.year,l.recordIndex,l.label,l.direction]);
export const flowEnds=l=>[l.reporter?.name||l.fromLabel||l.from.join(', '),l.partner?.name||l.toLabel||l.to.join(', ')];
export function flowMeasure(l){
 if(flowKind(l)==='aid')return `${money(l.usd,'USD')} · net aid disbursements`;
 if(flowKind(l)==='trade')return money(l.usd,'USD');
 if(flowKind(l)==='material')return `${(l.share/100).toFixed(2)}% of ${l.direction===1?'exporter exports':'importer imports'} · HS ${l.product.code}`;
 if(flowKind(l)==='arms')return `${l.comparisons?.length||0} declared categories · counts kept separate`;
 return 'Supplied relationship; no independent trade amount';
}
export const flowDiscrepancies=l=>(l.comparisons||[]).filter(r=>r.status==='different');
const sampleCache=new WeakMap();
export function pickFlow(links,rotation,zoom,point,tolerance=4){
 const project=globeProjector(rotation,300*zoom);let nearest=null,best=tolerance*tolerance;
 for(const link of links){let previous=null;
  if(!sampleCache.has(link))sampleCache.set(link,link.geometry.coordinates.map(unitVector));
  for(const c of sampleCache.get(link)){const p=project(c);
   if(p[2]<0){previous=null;continue}
   if(previous){const dx=p[0]-previous[0],dy=p[1]-previous[1],length=dx*dx+dy*dy,t=length?Math.max(0,Math.min(1,((point[0]-previous[0])*dx+(point[1]-previous[1])*dy)/length)):0;
    const distance=(point[0]-previous[0]-t*dx)**2+(point[1]-previous[1]-t*dy)**2;
    if(distance<best){best=distance;nearest=link}
   }previous=p;
  }
 }return nearest;
}
