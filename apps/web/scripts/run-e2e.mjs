import { spawn, spawnSync } from "node:child_process";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const server = spawn(process.execPath, [".next/standalone/server.js"], {
  cwd: process.cwd(),
  env: { ...process.env, HOSTNAME: "127.0.0.1", PORT: "3000" },
  stdio: "inherit",
  detached: process.platform !== "win32",
});

async function waitForServer() {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch("http://127.0.0.1:3000", { signal: AbortSignal.timeout(1_000) });
      if (response.ok) return;
    } catch {
      // Server startup is expected to refuse connections briefly.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error("Timed out waiting for the standalone Next.js server");
}

function stopServer() {
  if (!server.pid) return;
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/pid", String(server.pid), "/T", "/F"], {
      stdio: "ignore",
      timeout: 5_000,
    });
  } else {
    try {
      process.kill(-server.pid, "SIGTERM");
    } catch {
      server.kill("SIGKILL");
    }
  }
}

let browser;
let exitCode = 1;
try {
  await waitForServer();
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.setDefaultTimeout(10_000);

  await page.goto("http://127.0.0.1:3000/");
  if (!(await page.getByRole("heading", { name: /See more than whether code is wrong/i }).isVisible())) {
    throw new Error("Landing page heading was not visible");
  }
  if (process.env.CAPTURE_SCREENSHOTS === "1") {
    const output = path.resolve(process.cwd(), "../../docs/images");
    await mkdir(output, { recursive: true });
    await page.screenshot({ path: path.join(output, "landing.png"), fullPage: true });
  }

  if (process.env.EXPECT_API === "1") {
    await page.goto("http://127.0.0.1:3000/assignments/new");
    const approvalButtons = page.getByRole("button", { name: "Mark approved" });
    while (await approvalButtons.count()) await approvalButtons.first().click();
    await page.getByRole("button", { name: "Save assignment" }).click();
    await page.waitForURL(/\/assignments\/(?!new$)[^/]+$/, { timeout: 20_000 });
    if (page.url().endsWith("/assignments/demo")) throw new Error("Assignment setup did not create a persisted assignment ID");
    if (!(await page.getByRole("heading", { name: "Matrix Transformation Assignment" }).isVisible())) {
      throw new Error("Live assignment setup did not reach the saved assignment");
    }
  }

  await page.goto("http://127.0.0.1:3000/assignments/demo/grading");
  if (!(await page.getByRole("heading", { name: /Matrix Transformation Assignment/i }).isVisible())) {
    throw new Error("Grading overview did not load");
  }

  if (process.env.EXPECT_API === "1") {
    const fallbackNotice = page.getByText(/API network unavailable/i);
    if (await fallbackNotice.count()) throw new Error("The live API flow fell back to local fixture data");
    const reviewLink = page.locator('a[href^="/submissions/"]').first();
    const href = await reviewLink.getAttribute("href");
    if (!href || /^\/submissions\/(idea-wrong|correct|runtime|hardcoded|missing)$/.test(href)) {
      throw new Error("The live API flow did not expose a persisted submission ID");
    }
    await reviewLink.click();
    await page.waitForURL(/\/submissions\//);
  } else {
    await page.goto("http://127.0.0.1:3000/submissions/idea-wrong");
  }
  if (!(await page.getByRole("heading", { name: "Primary Evidence" }).isVisible())) {
    throw new Error("Primary Evidence panel was not visible");
  }
  if (!(await page.getByRole("heading", { name: "Derived Analysis" }).isVisible())) {
    throw new Error("Derived Analysis panel was not visible");
  }
  if (!(await page.getByText(/Demo Fixture/).first().isVisible())) {
    throw new Error("Fixture provenance label was not visible");
  }
  if (process.env.CAPTURE_SCREENSHOTS === "1") {
    const output = path.resolve(process.cwd(), "../../docs/images");
    await page.screenshot({ path: path.join(output, "submission-review.png"), fullPage: true });
  }

  exitCode = 0;
  console.log("Playwright E2E passed: landing -> grading -> evidence review.");
} finally {
  if (browser) {
    await Promise.race([
      browser.close(),
      new Promise((resolve) => setTimeout(resolve, 3_000)),
    ]);
  }
  stopServer();
}

process.exit(exitCode);
