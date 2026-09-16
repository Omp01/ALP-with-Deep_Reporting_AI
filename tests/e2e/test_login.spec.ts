/**
 * E2E test placeholder — Login flow.
 * Will be implemented in Phase 18.
 */
import { test, expect } from "@playwright/test";

test.describe("Login Flow", () => {
  test("should display login page", async ({ page }) => {
    await page.goto("/login");
    await expect(page).toHaveTitle(/Adaptive LMS/);
  });
});
