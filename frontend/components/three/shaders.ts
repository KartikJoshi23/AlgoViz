/**
 * GLSL for the terrain. Kept as plain strings so they ship in the same chunk
 * as the component and need no loader configuration.
 */

// Height mapping shared with the CPU surface probe (Terrain.tsx): depth is
// normalised by the smoothed maximum, clamped, and eased with a mild power so
// the near-mid steps stay readable without flattening the far ramp.
export const HEIGHT_GAMMA = 0.8;
export const HEIGHT_CLAMP = 1.35;

// ── Terrain ─────────────────────────────────────────────────────────
// Height field displaced in the vertex shader from an R32F texture holding
// the depth ring (width = price bins, height = time slices). `uHead` is the
// number of rows written; the newest row sits at v = 0 (front edge).

export const TERRAIN_VERT = /* glsl */ `
uniform sampler2D uDepth;
uniform float uHead;
uniform float uSlices;
uniform float uBins;
uniform float uMax;
uniform float uHeight;
uniform vec2 uSize; // plane width (price), depth (time)

varying vec2 vUv;
varying float vH;
varying vec3 vNormal;

float depthAt(vec2 uv) {
  float age = clamp(uv.y, 0.0, 1.0) * (uSlices - 1.0); // 0 = newest
  float row = mod(uHead - 1.0 - age + uSlices * 8.0, uSlices);
  float v = (row + 0.5) / uSlices;
  float d = texture2D(uDepth, vec2(clamp(uv.x, 0.0, 1.0), v)).r;
  float valid = step(age + 0.5, uHead); // rows not yet written stay flat
  return pow(clamp(d / max(uMax, 1e-6), 0.0, ${HEIGHT_CLAMP.toFixed(2)}), ${HEIGHT_GAMMA.toFixed(2)}) * valid;
}

void main() {
  vUv = uv;
  float h = depthAt(uv);
  vec3 p = position;
  p.z = h * uHeight;

  // normal from finite differences (in local plane units)
  vec2 du = vec2(1.0 / uBins, 0.0);
  vec2 dv = vec2(0.0, 1.0 / uSlices);
  float hx = (depthAt(uv + du) - depthAt(uv - du)) * uHeight;
  float hy = (depthAt(uv + dv) - depthAt(uv - dv)) * uHeight;
  float sx = 2.0 * uSize.x / uBins;
  float sy = 2.0 * uSize.y / uSlices;
  vec3 n = normalize(vec3(-hx / sx, -hy / sy, 1.0));
  vNormal = normalize(normalMatrix * n);
  vH = h;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
}
`;

// Colour grades with depth on the side's hue — dim at the floor, the full
// side colour mid-height, a light tint on the tallest walls — and the surface
// fades out with age instead of darkening into a slab.
export const TERRAIN_FRAG = /* glsl */ `
precision highp float;
uniform vec3 uBid;
uniform vec3 uAsk;
uniform vec3 uMid;
uniform float uBins;
uniform float uSlices;
uniform float uHover; // bin index under the crosshair, -1 when none
uniform float uHoverAge;

varying vec2 vUv;
varying float vH;
varying vec3 vNormal;

void main() {
  float side = step(0.5, vUv.x);
  vec3 base = mix(uBid, uAsk, side);

  vec3 col = mix(base * 0.16, base, smoothstep(0.0, 0.65, vH));
  col = mix(col, mix(base, vec3(1.0), 0.4), smoothstep(0.7, 1.25, vH));

  vec3 N = normalize(vNormal);
  vec3 L = normalize(vec3(-0.4, 0.35, 0.85)); // low, front-left: slopes catch the light
  col *= 0.55 + 0.45 * max(dot(N, L), 0.0);

  // topographic contours every 1/8 of the normalised height
  float c = abs(fract(vH * 8.0 + 0.5) - 0.5);
  col += (1.0 - smoothstep(0.03, 0.08, c)) * step(0.02, vH) * base * 0.12;

  // mid seam
  float midLine = 1.0 - smoothstep(0.0, 0.8 / uBins, abs(vUv.x - 0.5));
  col = mix(col, uMid, midLine * 0.8);

  // crosshair column + row
  if (uHover >= 0.0) {
    float hb = 1.0 - smoothstep(0.5 / uBins, 1.2 / uBins, abs(vUv.x - (uHover + 0.5) / uBins));
    float hr = 1.0 - smoothstep(0.6 / uSlices, 1.6 / uSlices, abs(vUv.y - uHoverAge / max(uSlices - 1.0, 1.0)));
    col = mix(col, vec3(1.0), hb * 0.3 + hr * 0.15);
  }

  float alpha = 1.0 - 0.9 * smoothstep(0.5, 1.0, vUv.y);
  gl_FragColor = vec4(col, alpha);
}
`;

// ── Trade particles ─────────────────────────────────────────────────
// Each particle's trajectory is a closed-form function of its spawn
// attributes, so the CPU only writes on spawn. Buys rise off the surface at
// the mid seam, sells fall onto it.

export const PARTICLE_VERT = /* glsl */ `
attribute float aBirth;
attribute float aSide;
attribute float aSize;
attribute float aX;
attribute float aSeed;

uniform float uTime;
uniform float uLife;
uniform vec2 uSize;
uniform float uHeight;
uniform sampler2D uDepth;
uniform float uHead;
uniform float uSlices;
uniform float uMax;
uniform float uPixelRatio;

varying float vAlpha;
varying float vSide;

void main() {
  float t = uTime - aBirth;
  float life = uLife * (0.75 + 0.5 * aSeed);
  if (aBirth <= 0.0 || t < 0.0 || t > life) {
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
    gl_PointSize = 0.0;
    vAlpha = 0.0;
    vSide = aSide;
    return;
  }
  float k = t / life;
  // trades print at the touch: scatter them a little across the seam
  float jitter = (fract(aSeed * 7.31) - 0.5) * 1.2;
  float x = aX * uSize.x * 0.5 + jitter;
  float u = clamp(aX * 0.5 + 0.5 + jitter / uSize.x, 0.0, 1.0);
  float row = mod(uHead - 1.0 + uSlices * 8.0, uSlices);
  float d = texture2D(uDepth, vec2(u, (row + 0.5) / uSlices)).r;
  float surf = pow(clamp(d / max(uMax, 1e-6), 0.0, ${HEIGHT_CLAMP.toFixed(2)}), ${HEIGHT_GAMMA.toFixed(2)}) * uHeight * step(0.5, uHead);
  float z = uSize.y * 0.5 - 0.2 - aSeed * 0.3; // along the newest row
  float rise = 1.8 + 1.6 * aSeed;
  float y = aSide > 0.0
    ? surf + 0.08 + (1.0 - (1.0 - k) * (1.0 - k)) * rise // buys lift off, decelerating
    : surf + 0.08 + (1.0 - k) * (1.0 - k) * rise;        // sells drop in, accelerating
  vec4 mv = modelViewMatrix * vec4(x, y, z, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = aSize * uPixelRatio * (40.0 / max(-mv.z, 1.0));
  vAlpha = smoothstep(0.0, 0.08, k) * (1.0 - smoothstep(0.7, 1.0, k));
  vSide = aSide;
}
`;

// Crisp discs: an antialiased edge one pixel wide and a darker rim that
// separates overlapping prints, with normal (not additive) blending.
export const PARTICLE_FRAG = /* glsl */ `
precision highp float;
uniform vec3 uBid;
uniform vec3 uAsk;
uniform vec3 uRim;
varying float vAlpha;
varying float vSide;
void main() {
  if (vAlpha <= 0.0) discard;
  float r = length(gl_PointCoord - 0.5) * 2.0;
  float fw = fwidth(r);
  float a = 1.0 - smoothstep(1.0 - fw, 1.0, r);
  if (a <= 0.0) discard;
  vec3 c = vSide > 0.0 ? uBid : uAsk;
  c = mix(c, uRim, smoothstep(0.62 - fw, 0.62 + fw, r) * 0.7);
  gl_FragColor = vec4(c, a * vAlpha);
}
`;
