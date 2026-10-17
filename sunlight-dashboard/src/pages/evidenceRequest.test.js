import {test} from 'node:test';
import assert from 'node:assert/strict';
import {analysisRequest} from './evidenceRequest.js';
test('an OCDS release with implementation contracts remains a single record',()=>{
 const contract={ocid:'release',contracts:[{id:'contract',implementation:{documents:[]}}]};
 assert.equal(analysisRequest(contract,'us_federal','').path,'/analyze');
 assert.equal(analysisRequest({contract},'us_federal','').request.contract,contract);
});
test('portfolio arrays and explicit wrappers retain capacity; malformed input is rejected',()=>{
 assert.equal(analysisRequest({contracts:[{ocid:'a'}]},'us_federal','1').request.capacity_budget,1);
 assert.equal(analysisRequest([],'us_federal','').path,'/batch');
 assert.throws(()=>analysisRequest(null,'us_federal',''));
 assert.throws(()=>analysisRequest([],'us_federal','1.5'));
 assert.throws(()=>analysisRequest(Array(1001).fill({}),'us_federal',''));
});
