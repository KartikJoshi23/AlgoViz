interface Probe {
  webgl2: boolean;
  software: boolean;
}

let cached: Probe | null = null;

const SOFTWARE_RENDERER = /swiftshader|llvmpipe|softpipe|software|microsoft basic render|mesa offscreen/i;

/** One WebGL probe per page: WebGL2 support and whether the renderer runs on the CPU. */
function probe(): Probe {
  if (cached) return cached;
  if (typeof document === "undefined") return { webgl2: false, software: false };
  try {
    const c = document.createElement("canvas");
    const gl2 = c.getContext("webgl2", { failIfMajorPerformanceCaveat: false });
    const gl = gl2 ?? c.getContext("webgl");
    if (!gl) {
      cached = { webgl2: false, software: true };
    } else {
      const ext = gl.getExtension("WEBGL_debug_renderer_info");
      const renderer = String(ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER));
      cached = { webgl2: !!gl2, software: SOFTWARE_RENDERER.test(renderer) };
      gl.getExtension("WEBGL_lose_context")?.loseContext();
    }
  } catch {
    cached = { webgl2: false, software: false };
  }
  return cached;
}

/** WebGL2 capability (WebGL1 is not enough for float textures without extensions). */
export function hasWebGL(): boolean {
  return probe().webgl2;
}

/**
 * True for CPU renderers (VMs, remote desktops, CI). They compile shaders on the
 * CPU: the terrain's program alone blocks the main thread for 20–30 s there.
 */
export function isSoftwareRenderer(): boolean {
  return probe().software;
}
