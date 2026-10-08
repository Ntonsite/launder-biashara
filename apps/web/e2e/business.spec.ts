import { expect, test, type Page } from "@playwright/test";

// Runs against the real API and database (docker compose up api) with the FreshWash demo history seeded.
const shots = process.env.E2E_SCREENSHOTS;
const snap = async (page: Page, name: string) => {
  if (shots)
    await page.screenshot({ path: `${shots}/${name}.png`, fullPage: true });
};

async function signIn(page: Page, email: string, password = "Demo123!") {
  // Printing opens a native dialog; record calls instead so the flow can continue.
  await page.addInitScript(() => {
    (window as unknown as { printed: number }).printed = 0;
    window.print = () => {
      (window as unknown as { printed: number }).printed += 1;
    };
  });
  await page.goto("/business/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/app/dashboard");
}

test("walk-in guest: counter order with part payment, slip, processing, collection, and it shows in the day report", async ({
  page,
}) => {
  await signIn(page, "owner@freshwash.co.tz");
  await expect(
    page.getByRole("heading", { name: "Needs attention" }),
  ).toBeVisible();
  await snap(page, "biz-dashboard");

  const before = await page.request
    .get("/api/v1/business/reports/daily", {
      headers: {
        Authorization: `Bearer ${await page.evaluate(() => JSON.parse(localStorage.getItem("launder-session-business")!).access_token)}`,
      },
    })
    .then((r) => r.json());
  const walkInsBefore = before.sources.find(
    (s: { source: string }) => s.source === "WALK_IN",
  ).orders;

  await page.getByRole("link", { name: "New walk-in order" }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "New walk-in order" }),
  ).toBeVisible();
  // The normal walk-in: tap services. Customer details are optional; a name is enough for the slip.
  for (let i = 0; i < 3; i++)
    await page
      .getByRole("button", { name: "Add Shirt", exact: true })
      .first()
      .click();
  await page
    .getByRole("button", { name: "Add Trouser", exact: true })
    .first()
    .click();
  await expect(page.locator(".wiBar")).toContainText("TZS 9,000");
  await page.getByPlaceholder(/Search phone or name/).fill("Mama Asha E2E");
  await expect(page.getByText(/walk-in guest/)).toBeVisible();
  await page.getByRole("button", { name: "Part paid" }).click();
  await page.getByLabel("Amount received now (TZS)").fill("4000");
  await expect(page.locator(".wiBar")).toContainText(
    "Balance TZS 5,000 on collection",
  );
  await snap(page, "biz-walk-in");
  await page.getByRole("button", { name: "Create & print slip" }).click();

  await page.waitForURL(/\/app\/orders\/.+\/slip\?print=1/);
  const slip = page.locator(".slip");
  await expect(slip).toContainText("Mama Asha E2E");
  await expect(slip).toContainText("Balance due");
  await expect(slip).toContainText("TZS 5,000");
  const number = (await slip.locator(".slipNumber strong").textContent())!;
  expect(number).toMatch(/^LN-[A-Z0-9]{6}$/);
  await expect
    .poll(() =>
      page.evaluate(() => (window as unknown as { printed: number }).printed),
    )
    .toBeGreaterThan(0);
  await snap(page, "biz-slip");

  await page.getByRole("link", { name: "Back to order" }).click();
  await expect(page.locator(".workspaceCard .pill").first()).toHaveText(
    "Clothes received",
  );
  for (const status of [
    "Washing",
    "Drying",
    "Ironing",
    "Quality check",
    "Ready",
  ]) {
    await page
      .getByRole("button", { name: `Mark as ${status}`, exact: true })
      .click();
    await expect(page.locator(".workspaceCard .pill").first()).toHaveText(
      status,
    );
  }
  await page
    .getByRole("button", { name: "Take TZS 5,000 & hand over" })
    .click();
  await expect(page.locator(".workspaceCard .pill").first()).toHaveText(
    "Completed",
  );

  // Same order in the end-of-day report: walk-in source, cash collected, nothing owed for it.
  await page.goto("/app/reports/daily");
  await expect(
    page.getByRole("heading", { name: "Where orders came from" }),
  ).toBeVisible();
  const after = page.locator(".shares li", { hasText: "Walk-in" });
  // Other tests may add walk-ins in parallel, so: at least this one more. The exact order is checked below.
  await expect
    .poll(async () => Number(await after.locator("b").textContent()))
    .toBeGreaterThan(walkInsBefore);
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "CSV" }).click();
  expect((await download).suggestedFilename()).toMatch(
    /^launder-daily-\d{4}-\d{2}-\d{2}\.csv$/,
  );
  await snap(page, "biz-daily-report");

  await page.goto(`/app/orders?q=${number}`);
  await expect(page.locator(".orderRow")).toHaveCount(1);
  await expect(page.locator(".orderRow")).toContainText("Mama Asha E2E");
});

test("dashboard figures click through to the matching filtered orders", async ({
  page,
}) => {
  await signIn(page, "owner@freshwash.co.tz");
  const overdue = page.locator(".attn.critical");
  await expect(overdue).toContainText(/orders? (is|are) overdue/);
  const count = Number(
    (await overdue.locator("b").textContent())!.match(/\d+/)![0],
  );
  await overdue.click();
  await expect(page).toHaveURL(/due=overdue/);
  await expect(page.locator(".orderRow")).toHaveCount(Math.min(count, 20));
  await expect(page.locator(".orderRow .due.overdue").first()).toContainText(
    "late",
  );
  await snap(page, "biz-orders-overdue");

  await page.goto("/app/dashboard");
  await page.locator(".pipeline a", { hasText: "Washing" }).click();
  await expect(page).toHaveURL(/status=WASHING/);
  await expect(page.locator(".activeFilters")).toContainText("Washing");

  await page.goto("/app/reports/monthly?period=last_month");
  await expect(page.getByRole("heading", { name: "Services" })).toBeVisible();
  await expect(page.locator(".reportHeader")).toContainText(
    "FreshWash Laundry",
  );
  await snap(page, "biz-monthly-report");
});

test("laundry staff see the work, not the books", async ({ page }) => {
  await signIn(page, "staff@freshwash.co.tz");
  const nav = page.locator("aside.side");
  await expect(nav.getByRole("link", { name: "Orders" })).toBeVisible();
  for (const hidden of ["Reports", "Payments", "Customers", "Settings"])
    await expect(nav.getByRole("link", { name: hidden })).toHaveCount(0);
  await expect(page.getByText("Sales today")).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Today's operations" }),
  ).toBeVisible();
  await page.goto("/app/reports/daily");
  await expect(page.getByRole("alert")).toBeVisible();
});

test("owner dashboard on a phone puts attention first and fits the screen @mobile", async ({
  page,
}) => {
  test.skip(page.viewportSize()!.width > 600, "phone layout only");
  await signIn(page, "owner@freshwash.co.tz");
  await page.evaluate(() => localStorage.setItem("launder-language", "sw"));
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Zinahitaji umakini" }),
  ).toBeVisible();
  const attentionTop = await page.locator(".attention").boundingBox();
  const todayTop = await page.locator(".todayGrid").boundingBox();
  expect(attentionTop!.y).toBeLessThan(todayTop!.y);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
  await snap(page, "biz-dashboard-mobile-sw");
});
