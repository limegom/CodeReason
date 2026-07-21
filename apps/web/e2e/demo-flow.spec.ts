import { expect, test } from "@playwright/test";

test("reviewer can navigate the evidence-first demo flow", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /See more than whether code is wrong/i })).toBeVisible();
  await page.getByRole("link", { name: /Try Demo Assignment/i }).click();
  await expect(page.getByRole("heading", { name: /Matrix Transformation Assignment/i })).toBeVisible();
  await page.getByRole("link", { name: /student-02/i }).click();
  await expect(page.getByRole("heading", { name: "Primary Evidence" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Derived Analysis" })).toBeVisible();
  await expect(page.getByText(/Demo Fixture/).first()).toBeVisible();
});
