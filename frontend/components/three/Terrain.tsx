"use client";
/* eslint-disable react-hooks/immutability, react-hooks/refs --
   Three.js materials, textures and buffers are mutable GPU resources driven
   from useFrame and pointer handlers; the compiler's immutability model does
   not apply to them. */

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import {
  BufferAttribute,
  BufferGeometry,
  Color,
  DataTexture,
  DynamicDrawUsage,
  FloatType,
  LineBasicMaterial,
  LineSegments,
  NearestFilter,
  RedFormat,
  ShaderMaterial,
  Vector2,
  Vector3,
  type PerspectiveCamera,
} from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import { gsap } from "@/lib/gsap";
import { fmtPrice, fmtQty } from "@/lib/format";
import type { DepthRing } from "@/lib/store/depth";
import { motionAllowed, useEffectiveMotion, useEffectiveTier, useStore } from "@/lib/store";
import { COLORS } from "@/lib/theme";
import type { RegimeLabel } from "@/lib/ws/types";
import { useVisible } from "./useVisible";
import { HEIGHT_CLAMP, HEIGHT_GAMMA, PARTICLE_FRAG, PARTICLE_VERT, TERRAIN_FRAG, TERRAIN_VERT } from "./shaders";

// World units: X = price (±band), Z = time (front = now), Y = depth.
const SIZE_X = 16;
const SIZE_Z = 10;
const HEIGHT = 3.2;
const FPS = 5; // book frames per second (one terrain row each)
const PRICE_FRACTIONS = [-1, -0.5, 0, 0.5, 1]; // of the half band
const TIME_TICKS_S = [5, 10, 15]; // the front edge is "now": the mid price label marks it
const DEPTH_FRACTIONS = [0.5, 1]; // of the terrain height

export interface TerrainHover {
  bin: number;
  age: number;
  offsetBps: number;
  price: number;
  depth: number;
  ageS: number;
  x: number;
  y: number;
}

/** What the scene exposes to the DOM layer: a surface probe and a redraw hook. */
interface SceneApi {
  probe: (ndcX: number, ndcY: number) => (TerrainHover & { point: Vector3 }) | null;
  setCrosshair: (hit: (TerrainHover & { point: Vector3 }) | null) => void;
  invalidate: () => void;
}

interface AxisRefs {
  price: (HTMLSpanElement | null)[];
  time: (HTMLSpanElement | null)[];
  depth: (HTMLSpanElement | null)[];
}

// age (frames) → world z; the newest row is the front edge
const zOfAge = (age: number, slices: number) => SIZE_Z / 2 - (age / (slices - 1)) * SIZE_Z;

/** Surface height at plane coords (u, v) — the CPU twin of the vertex shader's `depthAt`. */
function surfaceHeight(depth: DepthRing, max: number, u: number, v: number): number {
  const bin = Math.min(depth.bins - 1, Math.max(0, Math.floor(u * depth.bins)));
  const age = Math.round(Math.min(1, Math.max(0, v)) * (depth.slices - 1));
  const d = depth.at(bin, age);
  if (!Number.isFinite(d)) return 0;
  return Math.pow(Math.min(HEIGHT_CLAMP, Math.max(0, d / Math.max(max, 1e-6))), HEIGHT_GAMMA) * HEIGHT;
}

// ── Terrain mesh ────────────────────────────────────────────────────

function useDepthTexture(depth: DepthRing): DataTexture {
  const tex = useMemo(() => {
    const t = new DataTexture(depth.data, depth.bins, depth.slices, RedFormat, FloatType);
    t.magFilter = NearestFilter;
    t.minFilter = NearestFilter;
    t.generateMipmaps = false;
    t.needsUpdate = true;
    return t;
  }, [depth]);
  useEffect(() => () => tex.dispose(), [tex]);
  return tex;
}

function TerrainMesh({ depth, mat, segments }: { depth: DepthRing; mat: ShaderMaterial; segments: [number, number] }) {
  const lastHead = useRef(-1);
  useFrame(() => {
    const u = mat.uniforms;
    if (depth.head !== lastHead.current) {
      lastHead.current = depth.head;
      (u.uDepth!.value as DataTexture).needsUpdate = true;
      u.uHead!.value = depth.head;
    }
    u.uMax!.value += (Math.max(depth.maxDepth, 1e-6) - u.uMax!.value) * 0.12;
  });
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]}>
      <planeGeometry args={[SIZE_X, SIZE_Z, segments[0], segments[1]]} />
      <primitive object={mat} attach="material" />
    </mesh>
  );
}

// ── Floor grid, axis lines and crosshair ────────────────────────────

function lines(points: number[], color: string, opacity: number): LineSegments {
  const g = new BufferGeometry();
  g.setAttribute("position", new BufferAttribute(new Float32Array(points), 3));
  return new LineSegments(g, new LineBasicMaterial({ color, transparent: true, opacity, depthWrite: false }));
}

/** Price lines along time, time lines along price, and a depth axis at the front-left corner. */
function FloorGrid({ slices }: { slices: number }) {
  const grid = useMemo(() => {
    const pts: number[] = [];
    const y = -0.01;
    for (const f of PRICE_FRACTIONS) pts.push(f * (SIZE_X / 2), y, SIZE_Z / 2, f * (SIZE_X / 2), y, -SIZE_Z / 2);
    for (const s of [0, ...TIME_TICKS_S]) {
      const z = zOfAge(s * FPS, slices);
      pts.push(-SIZE_X / 2, y, z, SIZE_X / 2, y, z);
    }
    pts.push(-SIZE_X / 2, y, -SIZE_Z / 2, SIZE_X / 2, y, -SIZE_Z / 2); // back edge
    return lines(pts, "#ffffff", 0.07);
  }, [slices]);
  const axis = useMemo(() => {
    const x = -SIZE_X / 2 - 0.25;
    const z = SIZE_Z / 2;
    const pts = [x, 0, z, x, HEIGHT, z];
    for (const f of DEPTH_FRACTIONS) pts.push(x, f * HEIGHT, z, x + 0.18, f * HEIGHT, z);
    return lines(pts, "#ffffff", 0.18);
  }, []);
  useEffect(
    () => () => {
      for (const o of [grid, axis]) {
        o.geometry.dispose();
        (o.material as LineBasicMaterial).dispose();
      }
    },
    [grid, axis],
  );
  return (
    <>
      <primitive object={grid} />
      <primitive object={axis} />
    </>
  );
}

/** A drop line from the probed surface point to the floor, plus its price and time lines on the floor. */
function useCrosshair(): LineSegments {
  const obj = useMemo(() => {
    const o = lines(new Array(18).fill(0), COLORS.accent, 0.85);
    o.visible = false;
    o.frustumCulled = false;
    return o;
  }, []);
  useEffect(
    () => () => {
      obj.geometry.dispose();
      (obj.material as LineBasicMaterial).dispose();
    },
    [obj],
  );
  return obj;
}

// ── Trade particles ─────────────────────────────────────────────────

function Particles({ depth, tex, cap }: { depth: DepthRing; tex: DataTexture; cap: number }) {
  const geom = useMemo(() => {
    const g = new BufferGeometry();
    g.setAttribute("position", new BufferAttribute(new Float32Array(cap * 3), 3));
    for (const name of ["aBirth", "aSide", "aSize", "aX", "aSeed"]) {
      const attr = new BufferAttribute(new Float32Array(cap), 1);
      attr.setUsage(DynamicDrawUsage);
      g.setAttribute(name, attr);
    }
    return g;
  }, [cap]);
  const mat = useMemo(
    () =>
      new ShaderMaterial({
        vertexShader: PARTICLE_VERT,
        fragmentShader: PARTICLE_FRAG,
        transparent: true,
        depthWrite: false,
        uniforms: {
          uTime: { value: 0 },
          uLife: { value: 2.4 },
          uSize: { value: new Vector2(SIZE_X, SIZE_Z) },
          uHeight: { value: HEIGHT },
          uDepth: { value: tex },
          uHead: { value: 0 },
          uSlices: { value: depth.slices },
          uMax: { value: 1 },
          uPixelRatio: { value: 1 },
          uBid: { value: new Color(COLORS.bid) },
          uAsk: { value: new Color(COLORS.ask) },
          uRim: { value: new Color(COLORS.page) },
        },
      }),
    [tex, depth.slices],
  );
  useEffect(
    () => () => {
      geom.dispose();
      mat.dispose();
    },
    [geom, mat],
  );

  const write = useRef(0);
  const lastId = useRef(-1);
  const qtyEwma = useRef(0);
  const dpr = useThree((s) => s.viewport.dpr);

  useFrame((state) => {
    const u = mat.uniforms;
    u.uTime!.value = state.clock.elapsedTime;
    u.uHead!.value = depth.head;
    u.uMax!.value += (Math.max(depth.maxDepth, 1e-6) - u.uMax!.value) * 0.12;
    u.uPixelRatio!.value = dpr;

    const s = useStore.getState();
    const trades = s.trades;
    if (trades.length === 0) return;
    if (lastId.current < 0) {
      // first frame: don't replay the whole snapshot as a burst
      lastId.current = trades[trades.length - 1]!.trade_id;
      return;
    }
    let i = trades.length - 1;
    while (i >= 0 && trades[i]!.trade_id > lastId.current) i -= 1;
    if (i === trades.length - 1) return;
    const fresh = trades.slice(Math.max(i + 1, trades.length - cap));
    lastId.current = trades[trades.length - 1]!.trade_id;

    const mid = s.book?.mid ?? fresh[0]!.price;
    const band = depth.bandBps;
    const birth = geom.getAttribute("aBirth") as BufferAttribute;
    const side = geom.getAttribute("aSide") as BufferAttribute;
    const size = geom.getAttribute("aSize") as BufferAttribute;
    const px = geom.getAttribute("aX") as BufferAttribute;
    const seed = geom.getAttribute("aSeed") as BufferAttribute;
    const now = state.clock.elapsedTime;
    const spread = Math.min(0.2, 0.2 / Math.max(fresh.length, 1));
    fresh.forEach((t, j) => {
      qtyEwma.current = qtyEwma.current === 0 ? t.qty : qtyEwma.current + 0.05 * (t.qty - qtyEwma.current);
      const rel = Math.sqrt(t.qty / Math.max(qtyEwma.current, 1e-9));
      const w = write.current;
      birth.setX(w, now - (fresh.length - 1 - j) * spread);
      side.setX(w, t.side === "buy" ? 1 : -1);
      size.setX(w, 1.4 + 1.6 * Math.min(Math.max(rel, 0.4), 2.5));
      px.setX(w, Math.max(-1, Math.min(1, ((t.price / mid - 1) * 10_000) / band)));
      seed.setX(w, Math.random());
      write.current = (w + 1) % cap;
    });
    birth.needsUpdate = side.needsUpdate = size.needsUpdate = px.needsUpdate = seed.needsUpdate = true;
  });

  return (
    <points geometry={geom} frustumCulled={false}>
      <primitive object={mat} attach="material" />
    </points>
  );
}

// ── Camera ──────────────────────────────────────────────────────────

// Viewing direction (from the target): the camera rises with the volatility
// state and leans towards the trend while one is significant. The distance is
// fitted so the whole terrain, its axes and its tallest walls stay in frame.
const ELEVATION: Record<RegimeLabel | "none", number> = { none: 0.62, calm: 0.62, normal: 0.66, elevated: 0.8, extreme: 0.9 };
const viewDirection = (label: RegimeLabel | "none", trend: number): [number, number, number] => [
  trend * 0.36,
  ELEVATION[label] ?? ELEVATION.none,
  1,
];
const TARGET = new Vector3(0, HEIGHT * 0.3, 0.2);
const CORNERS = [-1, 1].flatMap((sx) =>
  [0, HEIGHT].flatMap((y) => [-1, 1].map((sz) => new Vector3(sx * (SIZE_X / 2 + 0.6), y, sz * (SIZE_Z / 2 + 0.4)))),
);

/** Distance along `dir` at which every corner of the terrain's box (with room for its labels) stays in view. */
function fitDistance(camera: PerspectiveCamera, dir: Vector3, aspect: number): number {
  const cam = camera.clone();
  cam.aspect = aspect;
  cam.updateProjectionMatrix();
  const p = new Vector3();
  let lo = 4;
  let hi = 80;
  for (let i = 0; i < 24; i += 1) {
    const d = (lo + hi) / 2;
    cam.position.copy(TARGET).addScaledVector(dir, d);
    cam.lookAt(TARGET);
    cam.updateMatrixWorld();
    const fits = CORNERS.every((c) => {
      p.copy(c).project(cam);
      return Math.abs(p.x) <= 0.86 && Math.abs(p.y) <= 0.9; // x: room for the DOM axis labels
    });
    if (fits) hi = d;
    else lo = d;
  }
  return hi;
}

function CameraRig({ interactive }: { interactive: boolean }) {
  const camera = useThree((s) => s.camera) as PerspectiveCamera;
  const gl = useThree((s) => s.gl);
  const size = useThree((s) => s.size);
  const controls = useRef<OrbitControls | null>(null);
  const userTouchedAt = useRef(0);
  const placed = useRef(false);
  const label = useStore((s) => (s.regime?.label ?? "none") as RegimeLabel | "none");
  const trend = useStore((s) => (s.regime?.trend === "up" ? 1 : s.regime?.trend === "down" ? -1 : 0));
  const aspect = size.width / Math.max(size.height, 1);

  useEffect(() => {
    const c = new OrbitControls(camera, gl.domElement);
    c.enableDamping = true;
    c.dampingFactor = 0.08;
    c.enablePan = false;
    c.minDistance = 6;
    c.maxDistance = 60;
    c.maxPolarAngle = Math.PI / 2 - 0.06;
    c.minPolarAngle = 0.2;
    c.enabled = interactive;
    c.target.copy(TARGET);
    const onStart = () => {
      userTouchedAt.current = Date.now();
    };
    c.addEventListener("start", onStart);
    controls.current = c;
    return () => {
      c.removeEventListener("start", onStart);
      c.dispose();
      controls.current = null;
    };
  }, [camera, gl, interactive]);

  useEffect(() => {
    const c = controls.current;
    if (!c) return;
    if (Date.now() - userTouchedAt.current < 12_000) return; // the user is driving
    const dir = new Vector3(...viewDirection(label, trend)).normalize();
    const pos = TARGET.clone().addScaledVector(dir, fitDistance(camera, dir, aspect));
    if (!placed.current || !motionAllowed()) {
      placed.current = true;
      camera.position.copy(pos);
      c.target.copy(TARGET);
      return;
    }
    const tl = gsap.timeline({ defaults: { duration: 2.4, ease: "power2.inOut" } });
    tl.to(camera.position, { x: pos.x, y: pos.y, z: pos.z }, 0);
    return () => {
      tl.kill();
    };
  }, [label, trend, camera, aspect]);

  useFrame(() => controls.current?.update());
  return null;
}

/** On the low tier render on demand at a capped rate instead of every vsync. */
function FrameThrottle({ fps }: { fps: number }) {
  const invalidate = useThree((s) => s.invalidate);
  useEffect(() => {
    const id = setInterval(() => invalidate(), 1000 / fps);
    return () => clearInterval(id);
  }, [invalidate, fps]);
  return null;
}

// ── Scene ───────────────────────────────────────────────────────────

function TerrainScene({
  depth,
  segments,
  cap,
  particles,
  api,
  axes,
  unit,
}: {
  depth: DepthRing;
  segments: [number, number];
  cap: number;
  particles: boolean;
  api: MutableRefObject<SceneApi | null>;
  axes: MutableRefObject<AxisRefs>;
  unit: string;
}) {
  const tex = useDepthTexture(depth);
  const mat = useMemo(
    () =>
      new ShaderMaterial({
        vertexShader: TERRAIN_VERT,
        fragmentShader: TERRAIN_FRAG,
        transparent: true,
        uniforms: {
          uDepth: { value: tex },
          uHead: { value: 0 },
          uSlices: { value: depth.slices },
          uBins: { value: depth.bins },
          uMax: { value: 1 },
          uHeight: { value: HEIGHT },
          uSize: { value: new Vector2(SIZE_X, SIZE_Z) },
          uBid: { value: new Color(COLORS.bid) },
          uAsk: { value: new Color(COLORS.ask) },
          uMid: { value: new Color(COLORS.mid) },
          uHover: { value: -1 },
          uHoverAge: { value: 0 },
        },
      }),
    [tex, depth.slices, depth.bins],
  );
  useEffect(() => () => mat.dispose(), [mat]);
  const crosshair = useCrosshair();
  const camera = useThree((s) => s.camera);
  const invalidate = useThree((s) => s.invalidate);

  // The surface is displaced on the GPU, so a raycast against the flat plane would
  // land under the peaks. March the pointer ray through the height field instead.
  useEffect(() => {
    const origin = new Vector3();
    const direction = new Vector3();
    const p = new Vector3();
    const inside = (v: Vector3) => Math.abs(v.x) <= SIZE_X / 2 && Math.abs(v.z) <= SIZE_Z / 2;
    const uvOf = (v: Vector3): [number, number] => [(v.x + SIZE_X / 2) / SIZE_X, (SIZE_Z / 2 - v.z) / SIZE_Z];
    const above = (v: Vector3, max: number) => {
      const [u, w] = uvOf(v);
      return v.y > surfaceHeight(depth, max, u, w);
    };
    api.current = {
      probe: (ndcX, ndcY) => {
        if (depth.head === 0) return null;
        const max = mat.uniforms.uMax!.value as number;
        origin.setFromMatrixPosition(camera.matrixWorld);
        direction.set(ndcX, ndcY, 0.5).unproject(camera).sub(origin).normalize();
        const steps = 900; // ~0.1 world units: finer than a price bin (0.125)
        const far = 90;
        let prevT = 0;
        for (let i = 1; i <= steps; i += 1) {
          const t = (i / steps) * far;
          p.copy(origin).addScaledVector(direction, t);
          if (p.y < -0.05) break;
          if (inside(p) && !above(p, max)) {
            // bisect between the last point above the surface and this one
            let a = prevT;
            let b = t;
            for (let k = 0; k < 10; k += 1) {
              const m = (a + b) / 2;
              p.copy(origin).addScaledVector(direction, m);
              if (above(p, max)) a = m;
              else b = m;
            }
            p.copy(origin).addScaledVector(direction, b);
            const [u, w] = uvOf(p);
            const bin = Math.min(depth.bins - 1, Math.max(0, Math.floor(u * depth.bins)));
            const age = Math.round(Math.min(1, Math.max(0, w)) * (depth.slices - 1));
            const d = depth.at(bin, age);
            if (!Number.isFinite(d)) return null;
            const off = depth.binOffsetBps(bin);
            const mid = useStore.getState().book?.mid ?? 0;
            p.y = surfaceHeight(depth, max, u, w);
            return { bin, age, offsetBps: off, price: mid * (1 + off / 10_000), depth: d, ageS: age / FPS, x: 0, y: 0, point: p.clone() };
          }
          prevT = t;
        }
        return null;
      },
      setCrosshair: (hit) => {
        mat.uniforms.uHover!.value = hit ? hit.bin : -1;
        mat.uniforms.uHoverAge!.value = hit ? hit.age : 0;
        crosshair.visible = !!hit;
        if (hit) {
          const { x, y, z } = hit.point;
          const pos = crosshair.geometry.getAttribute("position") as BufferAttribute;
          const seg = [x, y, z, x, 0, z, x, 0, SIZE_Z / 2, x, 0, -SIZE_Z / 2, -SIZE_X / 2, 0, z, SIZE_X / 2, 0, z];
          (pos.array as Float32Array).set(seg);
          pos.needsUpdate = true;
        }
        invalidate();
      },
      invalidate,
    };
    return () => {
      api.current = null;
    };
  }, [api, camera, crosshair, depth, invalidate, mat]);

  // Axis labels are DOM (crisp, themed); project their anchors every frame.
  const size = useThree((s) => s.size);
  const v = useMemo(() => new Vector3(), []);
  useFrame(() => {
    // `anchor`: the label's point that sits on the projected position (centre, or right edge)
    const place = (el: HTMLSpanElement | null | undefined, x: number, y: number, z: number, anchor = "-50%") => {
      if (!el) return;
      v.set(x, y, z).project(camera);
      if (v.z > 1) {
        el.style.visibility = "hidden";
        return;
      }
      el.style.visibility = "";
      el.style.transform = `translate(${((v.x + 1) / 2) * size.width}px, ${((1 - v.y) / 2) * size.height}px) translate(${anchor}, -50%)`;
    };
    const a = axes.current;
    const mid = useStore.getState().book?.mid;
    PRICE_FRACTIONS.forEach((f, i) => {
      const el = a.price[i];
      if (!el) return;
      const text = f === 0 ? (mid ? fmtPrice(mid, 2) : "mid") : `${f > 0 ? "+" : "−"}${(Math.abs(f) * depth.bandBps).toFixed(1)} bps`;
      if (el.textContent !== text) el.textContent = text;
      place(el, f * (SIZE_X / 2), 0, SIZE_Z / 2 + 0.55);
    });
    TIME_TICKS_S.forEach((s, i) => place(a.time[i], SIZE_X / 2 + 0.9, 0, zOfAge(s * FPS, depth.slices)));
    const max = mat.uniforms.uMax!.value as number;
    DEPTH_FRACTIONS.forEach((f, i) => {
      const el = a.depth[i];
      if (!el) return;
      const text = `${fmtQty(max * Math.pow(f, 1 / HEIGHT_GAMMA), 1)} ${unit}`;
      if (el.textContent !== text) el.textContent = text;
      place(el, -SIZE_X / 2 - 0.45, f * HEIGHT, SIZE_Z / 2, "-100%");
    });
  });

  return (
    <>
      <FloorGrid slices={depth.slices} />
      <TerrainMesh depth={depth} mat={mat} segments={segments} />
      <primitive object={crosshair} />
      {particles && <Particles depth={depth} tex={tex} cap={cap} />}
    </>
  );
}

// ── Public component ────────────────────────────────────────────────

export function Terrain({
  height = 360,
  interactive = true,
  particles = true,
  className = "",
}: {
  height?: number;
  interactive?: boolean;
  particles?: boolean;
  className?: string;
}) {
  const host = useRef<HTMLDivElement>(null);
  const visible = useVisible(host);
  const tier = useEffectiveTier();
  const motion = useEffectiveMotion();
  const depth = useStore((s) => s.depth);
  const symbol = useStore((s) => s.connection.symbol);
  const [hover, setHover] = useState<TerrainHover | null>(null);
  const api = useRef<SceneApi | null>(null);
  const axes = useRef<AxisRefs>({ price: [], time: [], depth: [] });

  const segments: [number, number] = tier === "low" ? [64, 48] : [depth.bins, depth.slices];
  const cap = tier === "high" ? 2048 : tier === "mid" ? 1024 : 512;
  const dpr: number | [number, number] = tier === "low" ? 1 : [1, 1.5];

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - r.left;
    const y = e.clientY - r.top;
    const hit = api.current?.probe((x / r.width) * 2 - 1, -((y / r.height) * 2 - 1)) ?? null;
    api.current?.setCrosshair(hit);
    setHover(hit ? { ...hit, x, y } : null);
  };
  const onPointerLeave = () => {
    api.current?.setCrosshair(null);
    setHover(null);
  };

  return (
    <div
      ref={host}
      className={`relative w-full select-none ${className}`}
      style={{ height }}
      onPointerMove={onPointerMove}
      onPointerLeave={onPointerLeave}
    >
      <Canvas
        dpr={dpr}
        frameloop={!visible ? "never" : tier === "low" ? "demand" : "always"}
        camera={{ fov: 38, near: 0.1, far: 200, position: [0, 9, 16] }}
        gl={{ antialias: tier !== "low", alpha: true, powerPreference: "high-performance" }}
        onCreated={({ gl }) => gl.setClearColor(0x000000, 0)}
        style={{ background: "transparent", cursor: interactive ? "grab" : "default" }}
        aria-label="Liquidity terrain: cumulative depth by price over the last 19 seconds"
        role="img"
      >
        <TerrainScene
          depth={depth}
          segments={segments}
          cap={cap}
          particles={particles && motion}
          api={api}
          axes={axes}
          unit={symbol.replace(/USDT$/, "")}
        />
        <CameraRig interactive={interactive} />
        {tier === "low" && visible && <FrameThrottle fps={30} />}
      </Canvas>

      <div className="num pointer-events-none absolute inset-0 text-caption" aria-hidden>
        {PRICE_FRACTIONS.map((f, i) => (
          <span
            key={`p${f}`}
            ref={(n) => {
              axes.current.price[i] = n;
            }}
            className={`absolute left-0 top-0 whitespace-nowrap ${f < 0 ? "text-bid-text" : f > 0 ? "text-ask-text" : "text-mid-text"}`}
          />
        ))}
        {TIME_TICKS_S.map((s, i) => (
          <span
            key={`t${s}`}
            ref={(n) => {
              axes.current.time[i] = n;
            }}
            className="absolute left-0 top-0 whitespace-nowrap text-ink-faint"
          >
            −{s} s
          </span>
        ))}
        {DEPTH_FRACTIONS.map((f, i) => (
          <span
            key={`d${f}`}
            ref={(n) => {
              axes.current.depth[i] = n;
            }}
            className="absolute left-0 top-0 whitespace-nowrap text-ink-faint"
          />
        ))}
      </div>

      {hover && (
        <div
          className="float pointer-events-none absolute z-10 rounded-md px-2 py-1 text-caption whitespace-nowrap"
          style={{ left: Math.min(hover.x + 14, (host.current?.clientWidth ?? 400) - 190), top: Math.max(8, hover.y - 52) }}
        >
          <div className="num">
            <span className="text-ink">{fmtPrice(hover.price, 2)}</span>
            <span className="text-ink-faint">
              {" "}
              · {hover.offsetBps >= 0 ? "+" : "−"}
              {Math.abs(hover.offsetBps).toFixed(2)} bps
            </span>
          </div>
          <div className="num flex items-center gap-1.5 text-ink-muted">
            <span className={`h-1.5 w-1.5 rounded-full ${hover.offsetBps < 0 ? "bg-bid" : "bg-ask"}`} aria-hidden />
            {fmtQty(hover.depth, 2)} cumulative · {hover.ageS === 0 ? "now" : `${hover.ageS.toFixed(1)} s ago`}
          </div>
        </div>
      )}
    </div>
  );
}
