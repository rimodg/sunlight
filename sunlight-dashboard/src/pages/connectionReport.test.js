import test from 'node:test';
import assert from 'node:assert/strict';
import {connectionReport} from './connectionReport.js';
test('connection brief has a readable measure, original source and print action without executing labels',()=>{const link={usd:12345,period:'2023',from:[0,0],to:[10,20],reporter:{name:'A <script>bad()</script>'},partner:{name:'B'},sourceURL:'https://example.org/report'};const html=connectionReport(link,null,'Obtain a dated receipt.');assert.match(html,/Print \/ save as PDF/);assert.match(html,/12345|12,345/);assert.match(html,/example.org\/report/);assert(!html.includes('<script>bad()'));assert.match(html,/&lt;script&gt;/);assert.match(html,/not identify a payment/)});
test('unsafe source links stay text in readable export',()=>{const link={usd:1,from:[0,0],to:[1,1],sourceURL:'javascript:alert(1)'};assert(!connectionReport(link,null,'Review source').includes('href="javascript:'))});
