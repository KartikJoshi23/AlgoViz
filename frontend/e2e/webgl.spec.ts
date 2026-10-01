import { expect, test } from "@playwright/test";

import { panel, trackErrors } from "./helpers";

// Forced "mid": on a software renderer the detected tier is "low", which keeps the hero 2D.
const PREFS = {
  state: { prefs: { perfTier: "mid", motion: "reduced", accentIntensity: 1, bookSubscribed: true, symbol: null } },
  version: 0,
};

test("the 3D terrain renders on a forced mid tier", async ({ page }) => {
  await page.addInitScript((prefs) => window.localStorage.setItem("algoviz.prefs", JSON.stringify(prefs)), PREFS);
  const errors = trackErrors(page);
  await page.goto("/book");
  const hero = panel(page, "Liquidity");
  await hero.getByRole("tab", { name: "Terrain" }).click();

  const canvas = hero.locator("canvas").first();
  await expect(canvas).toBeVisible({ timeout: 60_000 });
  const context = await canvas.evaluate((c: HTMLCanvasElement) => {
    const gl = c.getContext("webgl2") ?? c.getContext("webgl");
    return { alive: !!gl && !gl.isContextLost(), size: [c.width, c.height] };
  });
  expect(context.alive).toBe(true);
  expect(context.size[0]).toBeGreaterThan(0);

  // the render loop places the DOM price axis once the camera has fitted: frames are being drawn
  await expect(hero.locator('div.num[aria-hidden="true"] > span').first()).toHaveText(/\d/, { timeout: 60_000 });
  expect(errors()).toEqual([]);
});
