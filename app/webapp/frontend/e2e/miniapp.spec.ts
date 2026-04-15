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

async function readPaneGeometry(page: Page) {
  return page.evaluate(() => {
    const group = document.querySelector('[data-testid="workspace-frame"] > *');
    const pick = (selector: string) => {
      const node = document.querySelector(selector);
      if (!node) {
        return null;
      }
      const rect = node.getBoundingClientRect();
      return {
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height,
      };
    };

    return {
      viewport: {
        width: window.innerWidth,
        height: window.innerHeight,
      },
      groupFlow: group instanceof HTMLElement ? group.style.flexFlow : "",
      top: pick('[data-testid="pane-surface-top"]'),
      bottom: pick('[data-testid="pane-surface-bottom"]'),
      dock: pick('[data-testid="workspace-dock"]'),
    };
  });
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

test("loads the authenticated desktop shell and opens operations", async ({ page }, testInfo) => {
  test.skip(!process.env.MAX_BOT_TOKEN, "MAX_BOT_TOKEN is not available for authenticated checks.");
  const runtimeIssues = await attachRuntimeWatchers(page);

  await page.goto(signedEntryPath(), { waitUntil: "domcontentloaded" });

  await expect(page.getByTestId("superapp-shell")).toBeVisible();
  await expect(page.getByTestId("spotlight-hero")).toBeVisible();
  await expect(page.getByTestId("workspace-dock")).toBeVisible();
  await page.getByTestId("dock-market").click();

  const geometry = await readPaneGeometry(page);
  expect(geometry.dock).not.toBeNull();

  if (geometry.viewport.width >= 1040) {
    await expect(page.getByTestId("board-panel")).toBeVisible();
    const bottomPane = page.getByTestId("pane-surface-bottom");
    await bottomPane.locator(".pane-head select").selectOption("network-directory");
    await expect(page.getByTestId("network-panel")).toBeVisible();
    expect(geometry.top).not.toBeNull();
    expect(geometry.bottom).not.toBeNull();
    expect(geometry.groupFlow).toContain("row");
    expect(geometry.bottom!.x).toBeGreaterThan(geometry.top!.x + 24);
  } else {
    await expect(page.getByTestId("mobile-pane-switcher")).toBeVisible();
    await expect(page.getByTestId("pane-surface-top")).toBeVisible();
    await expect(page.getByTestId("board-panel")).toBeVisible();
    await page.getByTestId("mobile-pane-tab-bottom").click();
    await expect(page.getByTestId("pane-surface-bottom")).toBeVisible();
    expect(geometry.dock!.y).toBeLessThanOrEqual(geometry.viewport.height);
  }

  const roleButton = page.getByTestId("hero-open-role-mode");
  if (await roleButton.count()) {
    await roleButton.click();
    const roleDrawer = page.getByTestId("role-mode-drawer");
    await expect(roleDrawer).toBeVisible();
    await roleDrawer.locator(".btn").click();
    await expect(roleDrawer).toBeHidden();
  }

  const controlButton = page.getByTestId("dock-control");
  if (await controlButton.count()) {
    await controlButton.click();
    await expect(page.getByTestId("control-center-panel")).toBeVisible();
  }

  await page.screenshot({
    path: testInfo.outputPath("desktop-shell.png"),
    fullPage: true,
  });

  expect(runtimeIssues).toEqual([]);
});

test("keeps the mobile shell readable and dock-first", async ({ page }, testInfo) => {
  test.skip(!process.env.MAX_BOT_TOKEN, "MAX_BOT_TOKEN is not available for authenticated checks.");
  test.skip(testInfo.project.name !== "mobile-chrome", "mobile readability is validated only on the mobile project.");
  const runtimeIssues = await attachRuntimeWatchers(page);

  await page.goto(signedEntryPath(), { waitUntil: "domcontentloaded" });
  await page.getByTestId("dock-market").click();

  await expect(page.getByTestId("superapp-shell")).toBeVisible();
  await expect(page.getByTestId("spotlight-hero")).toBeVisible();
  await expect(page.getByTestId("mobile-pane-switcher")).toBeVisible();
  await expect(page.getByTestId("pane-surface-top")).toBeVisible();
  await expect(page.getByTestId("board-panel")).toBeVisible();
  await expect(page.getByTestId("workspace-dock")).toBeVisible();

  const geometry = await readPaneGeometry(page);
  expect(geometry.viewport.width).toBeLessThan(1040);
  expect(geometry.top).not.toBeNull();
  expect(geometry.dock).not.toBeNull();
  await page.getByTestId("mobile-pane-tab-bottom").click();
  await expect(page.getByTestId("pane-surface-bottom")).toBeVisible();
  expect(geometry.dock!.y).toBeLessThanOrEqual(geometry.viewport.height);

  await page.screenshot({
    path: testInfo.outputPath("mobile-shell.png"),
    fullPage: true,
  });

  expect(runtimeIssues).toEqual([]);
});
