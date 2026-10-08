import { expect, test, type Page } from "@playwright/test";

const shots = process.env.E2E_SCREENSHOTS;
const snap = async (page: Page, name: string) => {
  if (shots)
    await page.screenshot({ path: `${shots}/${name}.png`, fullPage: true });
};
const phone = () =>
  "7" + String(Math.floor(10_000_000 + Math.random() * 89_999_999));

test("customer orders on the web, FreshWash processes it, customer reviews and reorders", async ({
  browser,
}) => {
  const customer = await browser.newPage();
  await customer.goto("/laundries");
  await customer.getByLabel("Choose an area").selectOption("Mikocheni");
  const first = customer.locator(".laundryCard").first();
  await expect(first).toContainText("FreshWash Laundry");
  await snap(customer, "web-marketplace");
  await first.click();

  await expect(
    customer.getByRole("heading", { level: 1, name: "FreshWash Laundry" }),
  ).toBeVisible();
  for (let i = 0; i < 5; i++)
    await customer
      .getByRole("button", { name: "Add Shirt", exact: true })
      .click();
  for (let i = 0; i < 2; i++)
    await customer
      .getByRole("button", { name: "Add Trouser", exact: true })
      .click();
  await expect(customer.locator(".stickyCart")).toContainText("7 items");
  await snap(customer, "web-storefront");
  await customer.getByRole("button", { name: "View cart" }).click();

  await expect(customer.locator(".totalRow")).toContainText("16,000");
  await customer.getByRole("button", { name: "Continue" }).click();

  // Phone + OTP. In development the API returns the code and the UI shows it in a labelled notice.
  await customer.locator('input[name="phone"]').fill(phone());
  await customer.getByRole("button", { name: "Send code" }).click();
  const devNotice = await customer
    .getByText(/Development mode: your code is/)
    .textContent();
  await customer
    .locator('input[name="code"]')
    .fill(devNotice!.match(/\d{6}/)![0]);
  await customer.getByRole("button", { name: "Verify" }).click();
  await customer.locator('input[name="name"]').fill("Neema Mushi");
  await customer.getByRole("button", { name: "Continue" }).click();

  await customer.getByRole("radio", { name: /Pickup/ }).click();
  await customer.getByRole("button", { name: "Continue" }).click();
  await customer
    .getByPlaceholder("House, street or nearby landmark")
    .fill("Plot 12, Old Bagamoyo Rd");
  await customer.getByPlaceholder("Mikocheni").fill("Mikocheni");
  await customer.getByRole("button", { name: "Continue" }).click();
  await customer.locator(".slot").first().click();
  await customer.getByRole("button", { name: "Continue" }).click();
  await customer.getByRole("radio", { name: /Cash/ }).click();
  await customer.getByRole("button", { name: "Continue" }).click();
  await expect(customer.locator(".totalRow")).toContainText("18,000"); // 16,000 + 2,000 pickup fee
  await snap(customer, "web-checkout-review");
  await customer.getByRole("button", { name: "Place order" }).click();

  await expect(
    customer.getByRole("heading", { name: "Order confirmed" }),
  ).toBeVisible();
  const header = await customer
    .locator(".trackCard small")
    .first()
    .textContent();
  const orderNumber = header!.match(/LN-[A-Z0-9]+/)![0];
  await snap(customer, "web-tracking-new");

  // FreshWash staff receive the same order in the business workspace.
  const staff = await browser.newPage();
  await staff.goto("/business/login");
  await staff.getByLabel("Email").fill("owner@freshwash.co.tz");
  await staff.getByLabel("Password").fill("Demo123!");
  await staff.getByRole("button", { name: "Sign in" }).click();
  await staff.waitForURL("**/app/dashboard");
  await staff.goto("/app/orders");
  await staff
    .getByPlaceholder("Search order number, name or phone")
    .fill(orderNumber);
  await staff.getByRole("link", { name: new RegExp(orderNumber) }).click();
  const pill = staff.locator(".workspaceCard .pill").first();
  for (const status of [
    "Accepted",
    "Pickup scheduled",
    "Clothes received",
    "Washing",
    "Ironing",
    "Quality check",
    "Ready",
    "Out for delivery",
    "Delivered",
  ]) {
    await staff
      .getByRole("button", { name: `Mark as ${status}`, exact: true })
      .click();
    await expect(pill).toHaveText(status);
  }
  // Cash is the default method; the button records the balance.
  await staff.getByRole("button", { name: /^Record TZS/ }).click();
  await expect(staff.getByText("Cash · Paid")).toBeVisible();
  await staff
    .getByRole("button", { name: "Mark as Completed", exact: true })
    .click();
  await expect(pill).toHaveText("Completed");
  await snap(staff, "web-business-order");

  // Customer sees the same progression, reviews, and orders again at current prices.
  await customer.reload();
  await expect(customer.locator(".trackCard .pill").first()).toHaveText(
    "Completed",
  );
  await customer
    .getByPlaceholder(/Tell others/)
    .fill("Shirts came back perfect.");
  await customer.getByRole("button", { name: "Submit review" }).click();
  await expect(customer.getByText("Thanks for your review.")).toBeVisible();
  await customer.getByRole("button", { name: "Order again" }).click();
  await customer.waitForURL("**/cart");
  await expect(customer.locator(".cartLine")).toHaveCount(2);

  const store = await customer.request.get(
    "/api/v1/marketplace/laundries/freshwash-laundry-mikocheni",
  );
  const body = await store.json();
  expect(
    body.reviews.some(
      (r: { comment: string }) => r.comment === "Shirts came back perfect.",
    ),
  ).toBeTruthy();
});

test("Swahili is a full switch and persists @mobile", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "SW" }).first().click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Siku ya kufua, kwa urahisi.",
  );
  await page.reload();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Siku ya kufua, kwa urahisi.",
  );
  await page.goto("/laundries");
  await expect(
    page.getByRole("heading", { name: "Tafuta laundry" }),
  ).toBeVisible();
  await snap(page, `sw-marketplace-${test.info().project.name}`);
  await page.getByRole("button", { name: "EN" }).first().click();
});

test("pending marketplace business is not public and admin can review it", async ({
  page,
}) => {
  const r = await page.request.get(
    "/api/v1/marketplace/laundries/t-laundry-mikocheni",
  );
  expect(r.status()).toBe(404);
  await page.goto("/admin/login");
  await page.getByLabel("Email").fill("admin@launder.co.tz");
  await page.getByLabel("Password").fill("Admin123!");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/admin");
  await page.getByRole("button", { name: "Marketplace applications" }).click();
  const row = page.locator(".adminRow", { hasText: "T-Laundry" });
  await expect(row).toContainText("Under review");
  await row.getByRole("button", { name: "Review" }).click();
  await expect(
    page.getByText("Business name, phone and description"),
  ).toBeVisible();
  await snap(page, "web-admin-application");
});
