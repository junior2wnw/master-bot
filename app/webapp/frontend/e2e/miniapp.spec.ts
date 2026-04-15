import { expect, test, type Page } from "@playwright/test";

import { buildSignedMaxInitData, readLaunchUser } from "./support/maxInitData";

function signedEntryPath(): string {
  const token = process.env.MAX_BOT_TOKEN;
  if (!token) {
    throw new Error("MAX_BOT_TOKEN is required for authenticated Mini App E2E checks.");
  }
  const initData = buildSignedMaxInitData(token, readLaunchUser());
  return `/app#initData=${encodeURIComponent(initData)}`;
}

async function attachRuntimeWatchers(page: Page) {
  const issues: string[] = [];
  page.on("pageerror", (error) => issues.push(`pageerror: ${error.message}`));
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      issues.push(`console: ${msg.text()}`);
    }
  });
  return issues;
}

async function holdButton(page: Page, testId: string) {
  const target = page.getByTestId(testId);
  await expect(target).toBeVisible();
  const box = await target.boundingBox();
  if (!box) {
    throw new Error(`Unable to resolve ${testId} bounding box.`);
  }
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.waitForTimeout(450);
  await page.mouse.up();
}

async function countWindowPills(page: Page): Promise<number> {
  return page.locator('[data-testid^="window-pill-"]').count();
}

test("shows a clean launch gate in a normal browser", async ({ page }, testInfo) => {
  const runtimeIssues = await attachRuntimeWatchers(page);

  await page.goto("/app", { waitUntil: "domcontentloaded" });

  await expect(page.getByTestId("launch-gate")).toBeVisible();
  await expect(page.getByTestId("launch-gate").getByRole("button")).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("launch-gate.png"),
    fullPage: true,
  });

  expect(runtimeIssues).toEqual([]);
});

test("builds a live desktop composer and supports focus mode", async ({ page }, testInfo) => {
  test.skip(!process.env.MAX_BOT_TOKEN, "MAX_BOT_TOKEN is not available for authenticated checks.");
  const runtimeIssues = await attachRuntimeWatchers(page);

  await page.goto(signedEntryPath(), { waitUntil: "domcontentloaded" });

  await expect(page.getByTestId("superapp-shell")).toBeVisible();
  await expect(page.getByTestId("spotlight-hero")).toBeVisible();
  await expect(page.getByTestId("window-composer")).toBeVisible();
  await expect(page.getByTestId("window-rail")).toBeVisible();
  await expect(page.getByTestId("workspace-dock")).toBeVisible();

  await page.getByTestId("dock-workbench").click();
  await expect(page.locator(".workspace-intent")).toBeVisible();
  await expect(page.locator(".workspace-intent-actions .btn").first()).toBeVisible();

  const pillsBefore = await countWindowPills(page);
  await holdButton(page, "dock-market");
  await expect.poll(() => countWindowPills(page)).toBeGreaterThanOrEqual(Math.max(3, pillsBefore));

  if (testInfo.project.name === "desktop-chrome") {
    const firstWindowHead = page.locator(".window-card-head").first();
    await firstWindowHead.dblclick();
    await expect(page.getByTestId("window-spotlight-stage")).toBeVisible();
    await page.locator(".window-card-head").first().dblclick();
  }

  const controlButton = page.getByTestId("dock-control");
  if (await controlButton.count()) {
    await controlButton.click();
    await expect(page.getByTestId("control-center-panel")).toBeVisible();
  }

  await page.screenshot({
    path: testInfo.outputPath("desktop-composer.png"),
    fullPage: true,
  });

  expect(runtimeIssues).toEqual([]);
});

test("keeps the compact composer readable on mobile", async ({ page }, testInfo) => {
  test.skip(!process.env.MAX_BOT_TOKEN, "MAX_BOT_TOKEN is not available for authenticated checks.");
  test.skip(testInfo.project.name !== "mobile-chrome", "mobile readability is validated only on the mobile project.");
  const runtimeIssues = await attachRuntimeWatchers(page);

  await page.goto(signedEntryPath(), { waitUntil: "domcontentloaded" });
  await page.getByTestId("dock-workbench").click();

  await expect(page.getByTestId("superapp-shell")).toBeVisible();
  await expect(page.getByTestId("window-composer")).toBeVisible();
  await expect(page.getByTestId("window-composer-compact-stage")).toBeVisible();
  await expect(page.getByTestId("window-rail")).toBeVisible();
  await expect(page.getByTestId("workspace-dock")).toBeVisible();

  const pillsBefore = await countWindowPills(page);
  await holdButton(page, "dock-market");
  await expect.poll(() => countWindowPills(page)).toBeGreaterThanOrEqual(Math.max(3, pillsBefore));

  const railPills = page.locator('[data-testid^="window-pill-"]');
  await railPills.nth(0).click();
  await expect(page.locator(".window-card").first()).toBeVisible();

  await page.screenshot({
    path: testInfo.outputPath("mobile-composer.png"),
    fullPage: true,
  });

  expect(runtimeIssues).toEqual([]);
});
