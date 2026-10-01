import { expect, type Page } from "@playwright/test";

/** Collect page errors and console errors so specs can assert a clean run. */
export function trackErrors(page: Page): () => string[] {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(`console: ${m.text()}`);
  });
  return () => errors.filter((e) => !/favicon|net::ERR_ABORTED|Download the React DevTools/i.test(e));
}

/** The dashboard is live once the mid KPI shows a number instead of the placeholder. */
export async function waitForLiveData(page: Page): Promise<void> {
  const mid = page.locator('section[aria-label="Key metrics"] .stat-value').first();
  await expect(mid).not.toHaveText(/^—$/, { timeout: 30_000 });
  await expect(mid).toHaveText(/\d/);
}

/** A panel by its exact title (panels also mention other panels' names in prose). */
export function panel(page: Page, title: string) {
  return page
    .locator(".panel")
    .filter({ has: page.locator(".panel-title", { hasText: new RegExp(`^${title}$`, "i") }) })
    .first();
}

export const ROUTES = ["/", "/book", "/intelligence", "/strategies", "/alerts", "/settings"] as const;
