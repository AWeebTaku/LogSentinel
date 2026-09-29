// Browser smoke test of the demo flow against a running API (which serves ui/dist), using the system Chrome.
//   node e2e/smoke.mjs            (API on :8000, Kafka running, a model registered and active)
import { chromium } from "playwright-core";

const BASE = process.env.BASE ?? "http://127.0.0.1:8000";
const CHROME = process.env.CHROME ?? "/usr/bin/google-chrome-stable";
const shot = (page, name) => page.screenshot({ path: `e2e/shots/${name}.png`, fullPage: true });
const problems = [];
const step = (msg) => console.log(`- ${msg}`);
const expect = (cond, msg) => { if (!cond) throw new Error(`FAILED: ${msg}`); };

const browser = await chromium.launch({ executablePath: CHROME, headless: true, args: ["--no-sandbox"] });
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: "dark" })).newPage();
page.on("console", (m) => { if (m.type() === "error") problems.push(`console: ${m.text()}`); });
page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
page.on("requestfailed", (r) => problems.push(`request failed: ${r.url()}`));
page.on("response", (r) => { if (r.status() >= 400) problems.push(`HTTP ${r.status()}: ${r.url()}`); });

try {
  step("open the app (dark theme by system preference)");
  await page.goto(`${BASE}/#/`);
  await page.getByRole("link", { name: "Dashboard" }).first().waitFor();
  const fontOk = await page.evaluate(async () => {
    await document.fonts.ready;
    return [...document.fonts].some((f) => f.family.includes("IBM Plex Sans") && f.status === "loaded");
  });
  expect(fontOk, "an IBM Plex Sans face is loaded (self-hosted, not a system fallback)");
  await shot(page, "01-dashboard-initial");

  step("start a source from the Source page");
  await page.getByRole("link", { name: "Source" }).first().click();
  await page.getByRole("heading", { name: "Start a run" }).waitFor();
  await page.getByLabel("Events per second").fill("2000");
  await page.getByLabel("Sessions to replay").fill("4000");
  await page.getByRole("button", { name: "Start source" }).click();
  await page.getByText("Source started.").waitFor({ timeout: 10000 });
  await page.getByText("running", { exact: true }).first().waitFor({ timeout: 30000 });
  const runId = (await (await page.request.get(`${BASE}/sources/current`)).json()).run.id;
  step(`  run ${runId}`);
  await shot(page, "02-source-started");

  step("live dashboard fills with metrics");
  await page.getByRole("link", { name: "Dashboard" }).first().click();
  await page.getByText("Events per second").first().waitFor();
  await page.waitForFunction(() => {
    const v = [...document.querySelectorAll(".kpi")].find((k) => k.textContent.startsWith("Events per second"))?.querySelector(".value");
    return v && Number(v.textContent.replace(/,/g, "")) > 500;
  }, null, { timeout: 60000 });
  await page.waitForTimeout(4000);
  await shot(page, "03-dashboard-live");

  step("inject an anomaly burst while streaming");
  await page.getByRole("link", { name: "Source" }).first().click();
  const inject = page.getByRole("button", { name: "Inject anomaly burst" });
  await page.waitForFunction(() => !document.querySelector("button")?.disabled || true);
  await inject.waitFor();
  await expect_enabled(inject);
  await inject.click();
  await page.getByText(/Injected \d+ anomalous sessions/).waitFor({ timeout: 15000 });
  await page.getByRole("cell", { name: "100", exact: true }).first().waitFor({ timeout: 15000 });
  await page.waitForTimeout(3000);
  await shot(page, "04-source-injected");

  step("alerts arrive in the inbox; open one and triage it");
  await page.getByRole("link", { name: "Alerts" }).first().click();
  await page.getByRole("heading", { name: "Alerts", exact: true }).waitFor();
  await page.waitForSelector("table[aria-label='Alerts'] tbody tr", { timeout: 20000 });
  await page.locator("table[aria-label='Alerts'] tbody tr").first().click();
  await page.getByRole("heading", { name: /^Alert \d+$/ }).waitFor();
  await page.getByRole("button", { name: "Acknowledge" }).click();
  await page.getByText(/Acknowledged: 1 updated/).waitFor({ timeout: 10000 });
  await page.locator("aside[aria-label='Alert detail']").getByText("Acknowledged", { exact: true }).first().waitFor();
  await page.getByRole("button", { name: "Resolve" }).click();
  await page.getByText(/Resolved: 1 updated/).waitFor({ timeout: 10000 });
  await page.getByText("No triage actions yet.").waitFor({ state: "detached" });
  await shot(page, "05-alerts-triaged");
  await page.waitForFunction(() => document.querySelectorAll("aside[aria-label='Alert detail'] li").length >= 2,
    null, { timeout: 8000 }).catch(() => { throw new Error("FAILED: history lists both triage steps"); });
  await expect_no_action(page, "Acknowledge");           // a resolved alert can only be reopened

  step("batch triage: mark several as false positive");
  await page.locator("table[aria-label='Alerts'] tbody tr td:first-child label").nth(1).click();
  await page.locator("table[aria-label='Alerts'] tbody tr td:first-child label").nth(2).click();
  await page.getByRole("button", { name: "Mark false positive" }).first().click();
  await page.getByText(/False positive: 2 updated/).waitFor({ timeout: 10000 });
  await shot(page, "06-alerts-batch");

  step("run finishes and shows its quality");
  await page.getByRole("link", { name: "Source" }).first().click();
  for (let i = 0; i < 240; i++) {                       // wait for THIS run, not any old row that says "succeeded"
    const cur = (await (await page.request.get(`${BASE}/sources/current`)).json()).run;
    if (cur.id === runId && cur.status !== "running") { expect(cur.status === "succeeded", `run ended ${cur.status}`); break; }
    await page.waitForTimeout(1000);
  }
  const row = page.getByRole("row", { name: new RegExp(runId) });
  await row.getByText("succeeded", { exact: true }).waitFor({ timeout: 20000 });
  await row.getByRole("cell", { name: /\d+ of 100/ }).waitFor({ timeout: 20000 });      // injected sessions alerted
  await shot(page, "07-source-finished");

  step("models page lists the active model");
  await page.getByRole("link", { name: "Models" }).first().click();
  await page.getByRole("heading", { name: "Registry" }).waitFor();
  await page.getByText("active", { exact: true }).first().waitFor();
  await shot(page, "08-models");

  step("experiments: rebuild the report and preview a file");
  await page.getByRole("link", { name: "Experiments" }).first().click();
  await page.getByRole("tab", { name: "Rebuild report" }).click();
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await page.getByText("succeeded", { exact: true }).first().waitFor({ timeout: 120000 });
  await page.getByRole("heading", { name: "Results" }).waitFor({ timeout: 20000 });
  await page.locator("img[alt$='.png']").first().waitFor({ timeout: 20000 });
  await shot(page, "09-experiments");

  step("light theme");
  await page.getByRole("button", { name: /Switch to light theme/ }).click();
  await page.getByRole("link", { name: "Dashboard" }).first().click();
  await page.waitForTimeout(1500);
  await shot(page, "10-dashboard-light");
} finally {
  await browser.close();
}

async function expect_enabled(loc) {
  for (let i = 0; i < 100 && !(await loc.isEnabled()); i++) await new Promise((r) => setTimeout(r, 200));
  expect(await loc.isEnabled(), "inject button becomes enabled while the source streams");
}
async function expect_no_action(pg, name) {
  const n = await pg.locator("aside[aria-label='Alert detail']").getByRole("button", { name }).count();
  expect(n === 0, `no '${name}' action offered for a resolved alert`);
}

const real = problems.filter((p) => !/favicon/.test(p));
console.log(real.length ? `\nBrowser problems (${real.length}):\n${[...new Set(real)].join("\n")}` : "\nNo console errors, page errors or failed requests.");
process.exit(real.length ? 2 : 0);
