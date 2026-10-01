import { expect, test } from "@playwright/test";

/*
 * Performance budgets on the routes without WebGL — what Lighthouse budgets
 * check, measured with the browser's own observers so they run in the same
 * job, locally and in CI. Hard budgets: script bytes transferred and
 * Cumulative Layout Shift, both deterministic. Largest Contentful Paint is
 * recorded in the report but only guarded against a hang: CI renders on
 * SwiftShader, where the same build measured 3.2 s and 7.8 s on /strategies
 * in consecutive runs, so a tight timing budget would only flake.
 */
// measured 2026-09-30: 325 KB of script, CLS ≤ 0.034 (0.1 is "good"), LCP 0.2–7.8 s on SwiftShader
const BUDGETS = { scriptKB: 400, cls: 0.1, lcpHangMs: 15_000 };
const ROUTES = ["/strategies", "/alerts", "/settings"] as const;

declare global {
  interface Window {
    __budget: { lcp: number; cls: number };
  }
}

for (const route of ROUTES) {
  test(`${route} stays within its performance budget`, async ({ page }) => {
    const scripts: Promise<number>[] = [];
    page.on("response", (r) => {
      if (r.request().resourceType() === "script")
        scripts.push(
          r
            .request()
            .sizes()
            .then((s) => s.responseBodySize),
        );
    });
    await page.addInitScript(() => {
      window.__budget = { lcp: 0, cls: 0 };
      new PerformanceObserver((list) => {
        for (const e of list.getEntries()) window.__budget.lcp = e.startTime;
      }).observe({ type: "largest-contentful-paint", buffered: true });
      new PerformanceObserver((list) => {
        for (const e of list.getEntries() as (PerformanceEntry & { value: number; hadRecentInput: boolean })[]) {
          if (!e.hadRecentInput) window.__budget.cls += e.value;
        }
      }).observe({ type: "layout-shift", buffered: true });
    });
    await page.goto(route, { waitUntil: "load" });
    await expect(page.locator("main h1")).toBeVisible();
    await page.waitForTimeout(3_000); // late shifts count too

    const scriptKB = (await Promise.all(scripts)).reduce((a, b) => a + b, 0) / 1024;
    const { lcp, cls } = await page.evaluate(() => window.__budget);
    test.info().annotations.push({
      type: "budget",
      description: `script ${scriptKB.toFixed(0)} KB · LCP ${lcp.toFixed(0)} ms · CLS ${cls.toFixed(3)}`,
    });
    console.log(`${route}: script ${scriptKB.toFixed(0)} KB, LCP ${lcp.toFixed(0)} ms, CLS ${cls.toFixed(3)}`);
    expect(scriptKB, "script KB transferred").toBeLessThan(BUDGETS.scriptKB);
    expect(lcp, "Largest Contentful Paint (ms), hang guard only").toBeLessThan(BUDGETS.lcpHangMs);
    expect(cls, "Cumulative Layout Shift").toBeLessThan(BUDGETS.cls);
  });
}
