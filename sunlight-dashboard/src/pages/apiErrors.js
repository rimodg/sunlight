export function humanApiError(data){
 const detail=data?.detail;
 if(typeof detail==='string')return detail;
 if(Array.isArray(detail))return detail.map(d=>{const field=(d.loc||[]).filter(p=>!['body','query'].includes(p)).map(p=>typeof p==='number'?`record ${p+1}`:String(p).replaceAll('_',' ')).join(' → ');return `${field?field+': ':''}${d.msg||'Invalid value'}`}).join('\n');
 return 'The request could not be completed. Check the supplied values and try again.';
}
