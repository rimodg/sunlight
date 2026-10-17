import { test } from 'node:test';
import assert from 'node:assert/strict';
import { recordLocation, investigationRecords, procurementLinks } from './evidenceGeography.js';

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

test('flows require an awarded supplier and valid endpoints, not country names or unrelated parties', () => {
  const record = { tender: { deliveryLocations: [point([-77, 39])] }, parties: [{ id: 'supplier', location: point([4, 52]) }] };
  assert.deepEqual(procurementLinks(record), []);
  record.awards = [{ suppliers: [{ id: 'other' }] }];
  assert.deepEqual(procurementLinks(record), []);
  record.awards = [{ suppliers: [{ id: 'supplier' }] }];
  assert.deepEqual(procurementLinks(record).map(l => [l.from, l.to]), [[[4, 52], [-77, 39]]]);
  record.parties[0].location = { countryName: 'Netherlands' };
  assert.deepEqual(procurementLinks(record), []);
});

test('cancelled/unsuccessful awards, malformed geometry, identical endpoints and duplicates do not invent links', () => {
  const record = { tender: { deliveryLocations: [point([0, 0])] }, awards: [{ suppliers: [{ id: 's', location: point([10, 20]) }] }] };
  record.awards.push(record.awards[0]);
  assert.equal(procurementLinks(record).length, 1);
  for (const status of ['cancelled', 'unsuccessful']) {
    assert.equal(procurementLinks({ ...record, awards: [{ ...record.awards[0], status }] }).length, 0);
  }
  record.awards = [{ suppliers: [{ location: point([0, 0]) }, { location: point([190, 20]) }, null] }];
  assert.equal(procurementLinks(record).length, 0);
  assert.deepEqual(procurementLinks({ awards: {}, parties: {}, tender: {} }), []);
});
