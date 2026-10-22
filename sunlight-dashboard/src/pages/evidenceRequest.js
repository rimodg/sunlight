// OCDS releases have their own contracts[]; it is not a portfolio wrapper.
export function analysisRequest(payload, profile, budget) {
  if (payload === null || typeof payload !== 'object') throw new Error('Supply a procurement object or an array of records.');
  const isRelease = !Array.isArray(payload) && ['ocid', 'tender', 'buyer', 'awards'].some(key => key in payload);
  const contracts = Array.isArray(payload) ? payload : !isRelease && Array.isArray(payload.contracts) ? payload.contracts : null;
  if (contracts) {
    if (contracts.length > 1000) throw new Error('A batch can contain at most 1,000 records.');
    const capacity = budget === '' ? null : Number(budget);
    if (capacity !== null && (!Number.isSafeInteger(capacity) || capacity < 0)) throw new Error('Batch capacity must be a nonnegative whole number.');
    return { path: '/batch', request: { contracts, profile, capacity_budget: capacity } };
  }
  return { path: '/analyze', request: { contract: payload.contract || payload, profile } };
}
