import { expect, test, type Page } from "@playwright/test";

// Against the real API and database (docker compose up api), with the commercial demo seed.
const shots = process.env.E2E_SCREENSHOTS;
const snap = async (page: Page, name: string) => {
  if (shots) await page.screenshot({ path: `${shots}/${name}.png`, fullPage: true });
};

async function adminSignIn(page: Page, email: string) {
  await page.goto("/admin/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("Admin123!");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/admin");
  await page.getByRole("button", { name: "Monetization" }).click();
}

test("finance admin sees revenue, checks commission and gives a laundry special terms, all audited", async ({ page }) => {
  await adminSignIn(page, "finance@launder.co.tz");
  await expect(page.getByText("Monthly recurring revenue")).toBeVisible();
  await expect(page.getByText(/Reconciled/)).toBeVisible();
  await snap(page, "admin-revenue");

  await page.getByRole("button", { name: "Subscription plans" }).click();
  await expect(page.locator(".planAdmin", { hasText: "Business Plus" })).toContainText("TZS 60,000");
  await snap(page, "admin-plans");

  await page.getByRole("button", { name: "Marketplace pricing" }).click();
  await expect(page.locator(".bigRate")).toContainText("5%");
  const calc = page.locator("section.panel", { has: page.getByRole("heading", { name: "Commission calculator" }) });
  await calc.locator("select").selectOption({ label: "Safi Laundry" });
  await expect(calc).toContainText("TZS 900");
  await expect(calc).toContainText("TZS 29,100");
  await snap(page, "admin-marketplace-pricing");

  await page.getByRole("button", { name: "Business terms" }).click();
  const form = page.locator("form", { hasText: "New special terms" });
  await form.getByLabel("Laundry").selectOption({ label: "T-Laundry" });
  await form.getByLabel("Plan").selectOption({ label: "Pro" });
  await form.getByLabel("For how many days").fill("30");
  await form.getByLabel(/Reason/).fill("E2E: launch partner");
  page.once("dialog", (d) => d.accept());
  await form.getByRole("button", { name: "Create" }).click();
  const row = page.locator(".ruleRow", { hasText: "E2E: launch partner" }).first();
  await expect(row).toContainText("T-Laundry");
  await expect(row).toContainText("In force");
  await snap(page, "admin-terms");
  // Clean up: revoke with a reason.
  page.once("dialog", (d) => d.accept("E2E cleanup"));
  await row.getByRole("button", { name: "Revoke" }).click();
  await expect(page.locator(".ruleRow", { hasText: "E2E: launch partner" })).toHaveCount(0);

  await page.getByRole("button", { name: "Audit history" }).click();
  await expect(page.locator(".auditList li", { hasText: "E2E cleanup" }).first()).toContainText("finance@launder.co.tz");
});

test("operations admin can look but not change prices", async ({ page }) => {
  await adminSignIn(page, "support@launder.co.tz");
  await expect(page.getByText(/View only/)).toBeVisible();
  await page.getByRole("button", { name: "Subscription plans" }).click();
  await expect(page.locator(".planAdmin").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "New plan" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Change price" })).toHaveCount(0);
});

test("a new laundry on the free plan sees what is locked, starts a Pro trial, and gets the features", async ({ page, request }) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const email = `trial-${suffix}@example.co.tz`;
  const r = await request.post("/api/v1/auth/business/register", {
    data: { full_name: "Halima Juma", business_name: `Mbezi Fresh ${suffix}`, phone: `0716${Math.floor(100000 + Math.random() * 899999)}`,
            email, password: "Secure123!" },
  });
  expect(r.ok()).toBeTruthy();
  await page.goto("/business/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("Secure123!");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL(/\/(app\/dashboard|business\/onboarding)/);

  await page.goto("/app/reports");
  await expect(page.locator(".reportCard.locked", { hasText: "Monthly business report" })).toBeVisible();
  await page.goto("/app/billing");
  await expect(page.locator(".planHero")).toContainText("Starter");
  await expect(page.locator(".planHero")).toContainText("Free plan");
  await expect(page.getByText(/Commission: 5% of the laundry services/)).toBeVisible();
  await snap(page, "billing-starter");

  await page.locator(".planCard", { hasText: "Pro" }).first().getByRole("button", { name: "Upgrade" }).click();
  const modal = page.getByRole("dialog");
  await expect(modal).toContainText("To pay now");
  await expect(modal).toContainText("TZS 0");
  await expect(modal).toContainText("14-day free trial starts now");
  await snap(page, "billing-confirm");
  await modal.getByRole("button", { name: "Confirm change" }).click();
  await expect(page.locator(".planHero")).toContainText("Pro");
  await expect(page.locator(".planHero")).toContainText("Free trial");
  await expect(page.locator(".billingNotice")).toContainText("free trial of Pro ends in 14 days");

  await page.goto("/app/reports");
  await expect(page.locator(".reportCard.locked")).toHaveCount(0);
});

test("pilot laundry sees its pilot terms; plan page fits a phone @mobile", async ({ page }) => {
  await page.goto("/business/login");
  await page.getByLabel("Email").fill("owner@freshwash.co.tz");
  await page.getByLabel("Password").fill("Demo123!");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/app/dashboard");
  await page.goto("/app/billing");
  await expect(page.locator(".planHero")).toContainText("Pilot");
  await expect(page.locator(".billingNotice").first()).toContainText("pilot access to Pro ends in");
  await expect(page.locator(".billingNotice").first()).toContainText("nothing is charged");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await snap(page, "billing-pilot");
});
