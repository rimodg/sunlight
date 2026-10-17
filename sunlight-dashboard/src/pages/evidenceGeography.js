// Coordinates are supplied evidence, not inferred from the calibration profile.
function pointLocation(location) {
  const geometry = location?.geometry;
  if (geometry?.type !== 'Point' || !Array.isArray(geometry.coordinates)) return null;
  const [lon, lat] = geometry.coordinates;
  if (typeof lon !== 'number' || typeof lat !== 'number' || !Number.isFinite(lon) || !Number.isFinite(lat)) return null;
  if (Math.abs(lon) > 180 || Math.abs(lat) > 90) return null;
  return { coordinates: [lon, lat], label: location.description || 'Supplied location' };
}

export function recordLocation(record) {
  const candidates = [
    ...(Array.isArray(record?.tender?.deliveryLocations) ? record.tender.deliveryLocations : []),
    ...(Array.isArray(record?.tender?.items) ? record.tender.items : []).map(item => item?.deliveryLocation),
  ];
  for (const location of candidates) {
    const valid = pointLocation(location);
    if (valid) return { ...valid, label: location.description || 'Supplied delivery location' };
  }
  return null;
}

// An award establishes the supplier relationship. Coordinates alone do not.
// A displayed link is schematic, not evidence of a shipment or a payment.
export function procurementLinks(record) {
  const destination = recordLocation(record);
  if (!destination) return [];
  const parties = Array.isArray(record?.parties) ? record.parties : [];
  const awards = Array.isArray(record?.awards) ? record.awards : [];
  const links = [], seen = new Set();
  for (const award of awards) {
    if (award?.status === 'cancelled' || award?.status === 'unsuccessful') continue;
    for (const supplier of Array.isArray(award?.suppliers) ? award.suppliers : []) {
      const party = supplier?.id == null ? null : parties.find(p => p?.id === supplier.id);
      const origin = pointLocation(supplier?.location) || pointLocation(party?.location);
      if (!origin) continue;
      const key = JSON.stringify([origin.coordinates, destination.coordinates, supplier?.id || supplier?.name]);
      if (seen.has(key) || origin.coordinates.every((n, i) => n === destination.coordinates[i])) continue;
      seen.add(key);
      links.push({ from: origin.coordinates, to: destination.coordinates, label: `${supplier?.name || party?.name || 'Award supplier'} → ${destination.label}` });
    }
  }
  return links;
}

export function investigationRecords(run) {
  if (!run) return [];
  const inputs = run.request.contracts || [run.request.contract];
  const results = run.response.results || [run.response];
  // Batch results preserve input order, including duplicate identifiers and errors.
  return results.map((result, index) => ({
    index, result, record: inputs[index], location: recordLocation(inputs[index]), links: procurementLinks(inputs[index]),
    findings: result.structure?.contradictions?.length || 0,
    label: inputs[index]?.tender?.title || result.ocid || `Record ${index + 1}`,
  }));
}
