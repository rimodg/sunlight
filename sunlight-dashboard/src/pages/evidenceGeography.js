// Coordinates are supplied evidence, not inferred from the calibration profile.
export function recordLocation(record) {
  const candidates = [
    ...(Array.isArray(record?.tender?.deliveryLocations) ? record.tender.deliveryLocations : []),
    ...(Array.isArray(record?.tender?.items) ? record.tender.items : []).map(item => item?.deliveryLocation),
  ];
  for (const location of candidates) {
    const geometry = location?.geometry;
    if (geometry?.type !== 'Point' || !Array.isArray(geometry.coordinates)) continue;
    const [lon, lat] = geometry.coordinates;
    if (typeof lon !== 'number' || typeof lat !== 'number' || !Number.isFinite(lon) || !Number.isFinite(lat)) continue;
    if (Math.abs(lon) > 180 || Math.abs(lat) > 90) continue;
    return { coordinates: [lon, lat], label: location.description || 'Supplied delivery location' };
  }
  return null;
}

export function investigationRecords(run) {
  if (!run) return [];
  const inputs = run.request.contracts || [run.request.contract];
  const results = run.response.results || [run.response];
  // Batch results preserve input order, including duplicate identifiers and errors.
  return results.map((result, index) => ({
    index, result, record: inputs[index], location: recordLocation(inputs[index]),
    findings: result.structure?.contradictions?.length || 0,
    label: inputs[index]?.tender?.title || result.ocid || `Record ${index + 1}`,
  }));
}
