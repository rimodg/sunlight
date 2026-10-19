import { flowId, flowKind } from "./flows.js";

// One corridor per layer, source period and geographic pair. Keep all source
// members inspectable; never add unlike product/category measurements.
export function flowCorridors(links) {
  const groups = new Map();
  for (const link of links) {
    const key = JSON.stringify([
      flowKind(link),
      link.from,
      link.to,
      link.period || link.year || null,
    ]);
    if (!groups.has(key))
      groups.set(key, { ...link, members: [], corridorId: key });
    groups.get(key).members.push(link);
  }
  return [...groups.values()];
}
export function corridorContains(corridor, link) {
  return (
    flowId(corridor) === flowId(link) ||
    corridor.members?.some((member) => flowId(member) === flowId(link))
  );
}
export function cameraBetween(from, to, progress) {
  const t = Math.min(1, Math.max(0, progress)),
    ease = 1 - (1 - t) ** 3;
  const longitude =
    ((((to.rotation[0] - from.rotation[0]) % 360) + 540) % 360) - 180;
  return {
    rotation: [
      from.rotation[0] + longitude * ease,
      from.rotation[1] + (to.rotation[1] - from.rotation[1]) * ease,
    ],
    zoom: from.zoom + (to.zoom - from.zoom) * ease,
  };
}
