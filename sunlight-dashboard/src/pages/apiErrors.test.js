import test from 'node:test';
import assert from 'node:assert/strict';
import {humanApiError} from './apiErrors.js';
test('operator validation errors identify readable fields without dumping raw input',()=>{const message=humanApiError({detail:[{loc:['body','events',0,'expected','document_url'],msg:'Provide a valid URL',input:'private raw input'}]});assert.equal(message,'events → record 1 → expected → document url: Provide a valid URL');assert(!message.includes('private raw input'));assert.equal(humanApiError({detail:'Reload before saving'}),'Reload before saving')});
