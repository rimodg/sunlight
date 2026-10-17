import {test} from 'node:test';
import assert from 'node:assert/strict';
import {resolveCountry,recordCountry,overview,recordDocuments,tradeLinks} from './watchOverview.js';
const entry=(ocid,changes={})=>({index:0,result:{errors:[]},record:{ocid,buyer:{address:{countryName:'US'}},tender:{mainProcurementCategory:'goods'},awards:[{value:{amount:100,currency:'USD'}}],...changes}});
test('country lookup accepts ISO, aliases and accents without using jurisdiction or delivery as buyer country',()=>{
 assert.equal(resolveCountry('USA').code,'US');assert.equal(resolveCountry('United States').code,'US');assert.equal(resolveCountry('Cote d’Ivoire').code,'CI');
 assert.equal(recordCountry({tender:{deliveryLocations:[{description:'France'}]}}),null);
 assert.equal(recordCountry({parties:[{id:'buyer',roles:['buyer'],address:{countryName:'FR'}}]}).code,'FR');
});
test('totals separate currencies and stages; completion gaps are documentary, not payments or theft',()=>{
 const records=[entry('a'),entry('b',{contracts:[{status:'complete',value:{amount:200,currency:'EUR'},implementation:{transactions:[{value:{amount:200,currency:'EUR'}}]}}]}),entry('c',{awards:[],tender:{mainProcurementCategory:'works',value:{amount:50,currency:'USD'}}})];
 const value=overview(records);assert.equal(value.amounts.length,3);assert.equal(value.missingCompletion,3);assert.equal(value.declaredComplete,1);assert.equal(value.categories.length,2);assert.equal(value.amounts.find(a=>a.currency==='EUR').withoutCompletion,200);
});
test('duplicate identities, error records and unsafe URLs cannot inflate verified-looking totals',()=>{
 const data=overview([entry('duplicate'),entry('duplicate'),{...entry('error'),result:{errors:['failed']}}]);assert.equal(data.amounts.length,0);assert.equal(data.duplicates,2);assert.equal(data.invalid,1);
 const docs=recordDocuments({documents:[{id:'unsafe',url:'javascript:alert(1)',documentType:'completionCertificate'},{id:'ok',url:'https://example.org/a'},{id:'ok',url:'https://example.org/a'},{id:'deleted',documentStatus:'deleted'}]});assert.equal(docs.length,2);assert.equal(docs[0].safeURL,null);
});
test('country scopes do not pretend unknown coverage is zero national spending; linked completion is explicitly partial',()=>{
 const a=entry('a',{documents:[{id:'c',documentType:'completionCertificate',url:'https://example.org/certificate'}]});
 const data=overview([a,entry('b',{buyer:{}})],resolveCountry('US'));assert.equal(data.records,1);assert.equal(data.completionLinked,1);assert.equal(data.missingCompletion,0);assert.equal(data.unassigned,1);
 assert.equal(overview([a],resolveCountry('FR')).records,0);
});
test('trade uses source reporter codes in source queries and never enters procurement totals',()=>{
 const routes=tradeLinks({period:'2023',source_url:'https://comtradeapi.un.org/public/v1/preview/C/A/HS',routes:[{reporter:840,partner:356,source_reporter:842,source_partner:699,usd:500,period:'2023'}]});assert.equal(routes[0].reporter.code,'US');assert.match(routes[0].sourceURL,/partnerCode=699/);assert.equal(overview([]).amounts.length,0);
});

test('completion declarations are milestone counts, with repeated identifiers excluded',()=>{
 const data=overview([entry('a',{contracts:[{id:'c',implementation:{milestones:[{id:'1',status:'met'},{id:'1',status:'met'},{id:'2',status:'notMet'},{id:'3',status:'partiallyMet'},{id:'4'}]}}]})]);assert.equal(data.milestones,4);assert.equal(data.milestonesMet,1);assert.equal(data.milestonesNotMet,1);assert.equal(data.milestonesPartial,1);assert.equal(data.missingCompletion,1);
});
