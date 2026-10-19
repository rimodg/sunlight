import { memo, useEffect, useRef } from "react";
import { geoDistance, geoOrthographic, geoPath } from "d3-geo";
import { flowId, flowKind, flowColors, flowEnds } from "./flows";
import {
  flowProgress,
  globeProjector,
  routeVector,
  unitVector,
} from "./flowMotion";
import { cameraBetween } from "./flowScene";

// One camera and RAF clock. No React updates or SVG path strings per frame.
function FlowCanvas({
  links,
  rotation,
  zoom,
  motionAllowed,
  selectedId,
  hoveredId,
  cameraRef,
  dragRef,
  rotateWorld,
  scene,
}) {
  const canvas = useRef(null),
    view = useRef({ selectedId, hoveredId, rotateWorld, scene }),
    data = useRef([]),
    transition = useRef(null);
  useEffect(() => {
    view.current = { selectedId, hoveredId, rotateWorld, scene };
  }, [selectedId, hoveredId, rotateWorld, scene]);
  useEffect(() => {
    data.current = links.map((link, index) => ({
      link,
      index,
      id: flowId(link),
      kind: flowKind(link),
      samples: link.geometry.coordinates.map(unitVector),
      duration: 1.6 + geoDistance(link.from, link.to) * 0.7,
    }));
  }, [links]);
  useEffect(() => {
    const to = { rotation: [...rotation], zoom };
    if (dragRef.current?.x != null || !motionAllowed) {
      cameraRef.current = to;
      transition.current = null;
    } else
      transition.current = {
        from: {
          rotation: [...cameraRef.current.rotation],
          zoom: cameraRef.current.zoom,
        },
        to,
        start: performance.now(),
      };
  }, [rotation, zoom, motionAllowed, cameraRef, dragRef]);
  useEffect(() => {
    const surface = canvas.current,
      ctx = surface.getContext("2d", { alpha: false });
    if (!ctx) return;
    const world = document.createElement("canvas"),
      base = world.getContext("2d", { alpha: false });
    const projection = geoOrthographic().translate([360, 340]).clipAngle(90),
      path = geoPath(projection, base);
    let frame,
      previous = null,
      seconds = 0,
      sx = 1,
      sy = 1,
      baseKey = "";
    function resize() {
      const box = surface.getBoundingClientRect(),
        ratio = Math.min(devicePixelRatio || 1, 1.75);
      const width = Math.max(1, Math.round(box.width * ratio)),
        height = Math.max(1, Math.round(box.height * ratio));
      if (surface.width === width && surface.height === height) return;
      surface.width = world.width = width;
      surface.height = world.height = height;
      sx = width / 720;
      sy = height / 680;
      baseKey = "";
    }
    function paint(now) {
      const state = view.current;
      if (transition.current) {
        const t = transition.current,
          p = (now - t.start) / 550;
        cameraRef.current = cameraBetween(t.from, t.to, motionAllowed ? p : 1);
        if (p >= 1 || !motionAllowed) transition.current = null;
      } else if (
        motionAllowed &&
        state.rotateWorld &&
        dragRef.current?.x == null &&
        previous !== null
      )
        cameraRef.current.rotation[0] =
          (cameraRef.current.rotation[0] +
            Math.min((now - previous) / 1000, 0.05) * 2) %
          360;
      const camera = cameraRef.current,
        scale = 300 * camera.zoom,
        project = globeProjector(camera.rotation, scale),
        currentScene = state.scene;
      const key = JSON.stringify([
        camera.rotation,
        camera.zoom,
        currentScene?.country?.code,
        world.width,
        world.height,
      ]);
      if (baseKey !== key) {
        base.setTransform(1, 0, 0, 1, 0, 0);
        base.fillStyle = "#0b1922";
        base.fillRect(0, 0, world.width, world.height);
        base.setTransform(sx, 0, 0, sy, 0, 0);
        projection.rotate(camera.rotation).scale(scale);
        const draw = (feature, fill, stroke, width) => {
          if (!feature) return;
          base.beginPath();
          path(feature);
          if (fill) {
            base.fillStyle = fill;
            base.fill();
          }
          if (stroke) {
            base.strokeStyle = stroke;
            base.lineWidth = width;
            base.stroke();
          }
        };
        draw({ type: "Sphere" }, "#10242e", "#46636f", 0.7);
        draw(currentScene?.graticule, null, "#243f4a", 0.35);
        draw(currentScene?.land, "#223d47", "#53707c", 0.5);
        draw(currentScene?.borders, null, "#48616c", 0.35);
        draw(currentScene?.countryShape, "#3d5a60", "#e5c880", 0.9);
        baseKey = key;
      }
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.drawImage(world, 0, 0);
      ctx.setTransform(sx, 0, 0, sy, 0, 0);
      ctx.save();
      ctx.beginPath();
      ctx.arc(360, 340, scale, 0, Math.PI * 2);
      ctx.clip();
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      const focus = state.selectedId || state.hoveredId,
        step = camera.zoom > 3 ? 1 : 2;
      for (const flow of data.current) {
        const chosen = flow.id === focus;
        ctx.beginPath();
        let drawing = false;
        for (let i = 0; i < flow.samples.length; i += step) {
          const p = project(flow.samples[i]);
          if (p[2] < 0.005) {
            drawing = false;
            continue;
          }
          if (drawing) ctx.lineTo(p[0], p[1]);
          else {
            ctx.moveTo(p[0], p[1]);
            drawing = true;
          }
        }
        ctx.strokeStyle = flowColors[flow.kind];
        ctx.lineWidth = chosen ? 1.2 : 0.5;
        ctx.globalAlpha = focus ? (chosen ? 0.95 : 0.055) : 0.16;
        ctx.stroke();
        // Fine moving direction marks follow a continuous path, without a comet tail.
        const progress = flowProgress(seconds, flow.index, flow.duration);
        for (const t of chosen ? [progress, 0.35, 0.72] : [progress]) {
          const p = project(routeVector(flow.samples, t)),
            a = project(routeVector(flow.samples, Math.max(0, t - 0.008))),
            b = project(routeVector(flow.samples, Math.min(1, t + 0.008)));
          if (p[2] < 0.015 || a[2] < 0 || b[2] < 0) continue;
          const angle = Math.atan2(b[1] - a[1], b[0] - a[0]),
            size = chosen ? 4.2 : 2.6;
          ctx.globalAlpha = focus ? (chosen ? 1 : 0.1) : 0.7;
          ctx.strokeStyle = flowColors[flow.kind];
          ctx.lineWidth = chosen ? 1.45 : 0.85;
          ctx.beginPath();
          ctx.moveTo(
            p[0] - size * Math.cos(angle - 0.5),
            p[1] - size * Math.sin(angle - 0.5),
          );
          ctx.lineTo(p[0], p[1]);
          ctx.lineTo(
            p[0] - size * Math.cos(angle + 0.5),
            p[1] - size * Math.sin(angle + 0.5),
          );
          ctx.stroke();
        }
      }
      ctx.globalAlpha = 0.7;
      ctx.fillStyle = "#91acb7";
      for (const c of currentScene?.countries || []) {
        const p = project(c.vector);
        if (p[2] < 0.04) continue;
        ctx.beginPath();
        ctx.arc(
          p[0],
          p[1],
          c.code === currentScene.country?.code ? 3.3 : 1.25,
          0,
          Math.PI * 2,
        );
        ctx.fill();
      }
      ctx.globalAlpha = 0.85;
      ctx.fillStyle = "#d87976";
      ctx.beginPath();
      for (const point of currentScene?.conflicts || []) {
        const p = project(point.vector);
        if (p[2] < 0.015) continue;
        ctx.moveTo(p[0] + 1.35, p[1]);
        ctx.arc(p[0], p[1], 1.35, 0, Math.PI * 2);
      }
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.fillStyle = "#edcc82";
      for (const r of currentScene?.records || []) {
        const p = project(unitVector(r.location.coordinates));
        if (p[2] < 0) continue;
        ctx.beginPath();
        ctx.arc(p[0], p[1], 3, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();
      const chosen = data.current.find((f) => f.id === focus);
      if (chosen) {
        ctx.fillStyle = flowColors[chosen.kind];
        ctx.strokeStyle = flowColors[chosen.kind];
        ctx.lineWidth = 1.3;
        const ends = flowEnds(chosen.link);
        for (const [i, v] of [
          chosen.samples[0],
          chosen.samples.at(-1),
        ].entries()) {
          const p = project(v);
          if (p[2] < 0.02) continue;
          ctx.strokeStyle = flowColors[chosen.kind];
          ctx.lineWidth = 1.3;
          ctx.beginPath();
          ctx.arc(p[0], p[1], i ? 4.5 : 3, 0, Math.PI * 2);
          if (i) ctx.stroke();
          else ctx.fill();
          const text = (i ? "TO · " : "FROM · ") + ends[i];
          ctx.font = "600 10px system-ui";
          ctx.textAlign = p[0] > 520 ? "right" : "left";
          ctx.lineWidth = 3;
          ctx.strokeStyle = "#0b1922";
          const x = p[0] + (p[0] > 520 ? -8 : 8),
            y = p[1] - 11;
          ctx.strokeText(text, x, y);
          ctx.fillText(text, x, y);
        }
      }
    }
    function tick(now) {
      frame = requestAnimationFrame(tick);
      if (document.hidden) {
        previous = null;
        return;
      }
      if (previous !== null && motionAllowed)
        seconds += Math.min((now - previous) / 1000, 0.05);
      paint(now);
      previous = now;
    }
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(surface.closest("svg"));
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [motionAllowed, cameraRef, dragRef]);
  return (
    <canvas
      ref={canvas}
      className="ev-flow-canvas ev-world-canvas"
      aria-hidden="true"
    />
  );
}
export default memo(FlowCanvas);
