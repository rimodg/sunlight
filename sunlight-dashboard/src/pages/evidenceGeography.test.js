import { test } from 'node:test';
import assert from 'node:assert/strict';
import { recordLocation, investigationRecords } from './evidenceGeography.js';

const point = coordinates => ({ geometry: { type: 'Point', coordinates } });
test('geography requires explicit valid coordinates, including zero', () => {
  assert.equal(recordLocation({ buyer: { address: { countryName: 'France' } } }), null);
  assert.equal(recordLocation({ tender: { deliveryLocations: {}, items: [null] } }), null);
  for (const coordinates of [[181, 0], [0, 91], ['1', 2], [NaN, 3], [null, null]]) {
    assert.equal(recordLocation({ tender: { deliveryLocations: [point(coordinates)] } }), null);
  }
  assert.deepEqual(recordLocation({ tender: { items: [{ deliveryLocation: point([0, 0]) }] } }).coordinates, [0, 0]);
});
test('batch record association uses input position even with duplicate OCIDs or errors', () => {
  const inputs = [{ ocid: 'duplicate', tender: { title: 'First', deliveryLocations: [point([10, 20])] } }, { ocid: 'duplicate', tender: { title: 'Second' } }];
  const results = [{ ocid: 'duplicate', structure: { contradictions: [{}] }, errors: [] }, { ocid: 'duplicate', errors: ['failed'] }];
  const records = investigationRecords({ request: { contracts: inputs }, response: { results } });
  assert.equal(records[0].findings, 1);
  assert.equal(records[1].label, 'Second');
  assert.equal(records[1].location, null);
  assert.equal(records[1].result, results[1]);
});
test('single sparse records remain inspectable without coordinates', () => {
  assert.deepEqual(investigationRecords(null), []);
  const [record] = investigationRecords({ request: { contract: { ocid: 'sparse' } }, response: { ocid: 'sparse', errors: [] } });
  assert.equal(record.label, 'sparse');
  assert.equal(record.location, null);
});
