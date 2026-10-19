import test from "node:test";
import assert from "node:assert/strict";
import { cameraBetween, flowCorridors, corridorContains } from "./flowScene.js";
import { flowId } from "./flows.js";
import { flowProgress } from "./flowMotion.js";

test("corridors preserve source records without inventing a combined economic measure", () => {
  const first = {
    kind: "material",
    from: [0, 0],
    to: [10, 20],
    period: 2023,
    product: { code: "2709" },
    share: 100,
    rankValue: 12,
    label: "Crude oil",
    direction: 0,
  };
  const second = {
    ...first,
    product: { code: "2601" },
    share: 8000,
    label: "Iron ore",
  };
  const inputs = [
    first,
    second,
    { ...first, period: 2022 },
    { ...first, from: first.to, to: first.from },
    { ...first, kind: "arms" },
  ];
  const groups = flowCorridors(inputs);
  assert.equal(groups.length, 4);
  assert.equal(groups[0].members.length, 2);
  assert.equal(groups[0].share, 100);
  assert.equal(groups[0].usd, undefined);
  assert.deepEqual(groups[0].members, [first, second]);
  assert.equal(first.members, undefined);
  assert(corridorContains(groups[0], second));
  assert(!corridorContains(groups[1], second));
});
test("source identities distinguish import and export bases along the same geographic corridor", () => {
  const a = {
    kind: "material",
    from: [0, 0],
    to: [10, 20],
    period: 2023,
    product: { code: "2709" },
    direction: 0,
  };
  const b = { ...a, direction: 1 };
  assert.notEqual(flowId(a), flowId(b));
  assert.equal(flowCorridors([a, b])[0].members.length, 2);
});
test("camera focus eases along the shortest longitude including repeated manual turns", () => {
  for (const [from, to] of [
    [170, -170],
    [730, -170],
    [-730, 170],
  ]) {
    const a = { rotation: [from, 10], zoom: 1 },
      b = { rotation: [to, -20], zoom: 1.25 };
    assert.deepEqual(cameraBetween(a, b, 0), a);
    const end = cameraBetween(a, b, 1),
      half = cameraBetween(a, b, 0.5);
    assert(Math.abs((((end.rotation[0] - to) % 360) + 360) % 360) < 1e-8);
    assert.equal(end.zoom, 1.25);
    assert.equal(end.rotation[1], -20);
    assert(Math.abs(half.rotation[0] - from) < 180);
    assert(half.zoom > 1 && half.zoom < 1.25);
  }
});
test("visual flow duration is independent of frame count and does not encode reported quantities", () => {
  for (const duration of [1.6, 2.1, 3.8]) {
    assert.equal(flowProgress(duration, 0, duration), 0);
    assert(Math.abs(flowProgress(duration / 2, 0, duration) - 0.5) < 1e-12);
  }
});
