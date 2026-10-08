import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

// Against the real API and database (docker compose up api) with the Marketplace demo seed (seed_marketplace.py).
const shots = process.env.E2E_SCREENSHOTS;
const snap = async (page: Page, name: string) => {
  if (shots)
    await page.screenshot({ path: `${shots}/${name}.png`, fullPage: true });
};

async function businessSignIn(
  page: Page,
  email: string,
  password = "Demo123!",
) {
  await page.goto("/business/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL(/\/(app\/dashboard|business\/onboarding)/);
}

async function adminSignIn(page: Page, email: string) {
  await page.goto("/admin/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("Admin123!");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/admin");
}

/** A laundry that uses Launder Business with its setup complete, not on the Marketplace. */
async function readyLaundry(request: APIRequestContext) {
  const suffix = Math.random().toString(36).slice(2, 8);
  const email = `mp-${suffix}@example.co.tz`;
  const name = `Tegeta Clean ${suffix}`;
  const r = await request.post("/api/v1/auth/business/register", {
    data: {
      full_name: "Zuhura Ally",
      business_name: name,
      phone: `0716${Math.floor(100000 + Math.random() * 899999)}`,
      email,
      password: "Secure123!",
    },
  });
  expect(r.ok()).toBeTruthy();
  const headers = { Authorization: `Bearer ${(await r.json()).access_token}` };
  await request.put("/api/v1/business/profile", {
    headers,
    data: {
      description: "Neighbourhood laundry in Tegeta.",
      address: "Bagamoyo Rd, Tegeta",
      area: "Tegeta",
      latitude: -6.664,
      longitude: 39.205,
    },
  });
  await request.put("/api/v1/business/hours", {
    headers,
    data: {
      days: [0, 1, 2, 3, 4, 5].map((d) => ({
        weekday: d,
        opens_at: "08:00",
        closes_at: "19:00",
      })),
    },
  });
  for (const [service, price] of [
    ["Shirt", 1800],
    ["Suit", 11000],
  ] as const)
    await request.post("/api/v1/business/services", {
      headers,
      data: { name: service, price },
    });
  return { email, name };
}

test("a laundry joins the Marketplace, Launder approves it and its commission-free trial starts", async ({
  page,
  request,
  browser,
}) => {
  const laundry = await readyLaundry(request);
  await businessSignIn(page, laundry.email, "Secure123!");
  await page.goto("/app/marketplace");
  await expect(
    page.getByRole("heading", {
      name: "Grow your laundry business with Launder Marketplace",
    }),
  ).toBeVisible();
  await expect(page.locator(".mpOffer")).toContainText(
    "30 days commission-free",
  );
  await expect(page.locator(".mpOffer")).toContainText(
    "Then 5% on completed Marketplace orders",
  );
  await snap(page, "mp-pitch");

  await page.getByRole("button", { name: "Join Marketplace" }).click();
  await expect(page.getByText("5 of 5 ready")).toBeVisible();
  await page.getByLabel("Contact person").fill("Zuhura Ally");
  await page.getByLabel("I accept the Marketplace terms.").check();
  await snap(page, "mp-apply");
  await page.getByRole("button", { name: "Submit for review" }).click();
  await expect(page.locator(".marketStatus")).toContainText("Under review");

  // Operations admin reviews and approves with the default trial.
  const adminPage = await browser.newPage();
  await adminSignIn(adminPage, "support@launder.co.tz");
  await adminPage
    .getByRole("button", { name: "Marketplace", exact: true })
    .click();
  await adminPage.getByRole("button", { name: "Laundries" }).click();
  await adminPage.getByRole("searchbox").fill(laundry.name);
  await adminPage.locator(".mpaList button", { hasText: laundry.name }).click();
  await expect(adminPage.locator(".mpaDetail")).toContainText(
    "Waiting for review",
  );
  await snap(adminPage, "mpa-review");
  await adminPage
    .locator(".mpaActions")
    .getByRole("button", { name: "Approve" })
    .click();
  await adminPage
    .locator("form.monForm")
    .getByRole("button", { name: "Approve" })
    .click();
  await expect(adminPage.locator(".mpaDetail .status").first()).toHaveText(
    "Free trial",
  );
  await expect(adminPage.locator(".mpaDetail")).toContainText("Trial at 0%");
  await snap(adminPage, "mpa-approved");

  await page.reload();
  await expect(page.locator(".mpTrial")).toContainText("30 days left");
  await expect(page.locator(".mpTrial")).toContainText("After the trial");
  await expect(page.locator(".mpTrial")).toContainText("5%");
  await expect(
    page.getByRole("link", { name: "View your public storefront" }),
  ).toBeVisible();
  await snap(page, "mp-trial-new");
});

test("a laundry partway through its trial sees results and the reminder on its dashboard @mobile", async ({
  page,
}) => {
  await businessSignIn(page, "owner@mwengewash.co.tz");
  await expect(
    page.locator(".dashBanner", { hasText: "Marketplace trial ends in" }),
  ).toBeVisible();
  await page.goto("/app/marketplace");
  await expect(page.locator(".mpTrial")).toContainText("days left");
  await expect(page.locator(".mpStats")).toContainText("Commission saved");
  await expect(page.locator(".mpStats .stat").first()).toContainText("7");
  await expect(
    page.getByRole("button", { name: /Continue after the trial at 5%/ }),
  ).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
  await snap(page, "mp-trial-dashboard");
});

test("an expired trial pauses new orders and offers the standard terms", async ({
  page,
}) => {
  await businessSignIn(page, "owner@kariakooquick.co.tz");
  await page.goto("/app/marketplace");
  await expect(page.locator(".marketStatus")).toContainText("Trial ended");
  await expect(
    page.getByText(
      "New Marketplace orders are paused and your storefront is hidden.",
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Accept 5% and reopen my storefront" }),
  ).toBeVisible();
  await snap(page, "mp-expired");
});

test("an invited laundry sees its individual terms", async ({ page }) => {
  await businessSignIn(page, "owner@kawefresh.co.tz");
  await page.goto("/app/marketplace");
  await expect(page.locator(".mpInvite")).toContainText("You're invited");
  await expect(page.locator(".mpTerms")).toContainText(
    "45 days commission-free",
  );
  await expect(
    page.getByRole("button", { name: "Confirm and join" }),
  ).toBeVisible();
  await snap(page, "mp-invited");
});

test("finance admin sees the rollout, trials and Marketplace settings", async ({
  page,
}) => {
  await adminSignIn(page, "finance@launder.co.tz");
  await page.getByRole("button", { name: "Marketplace", exact: true }).click();
  await expect(page.locator(".mpaLaunch")).toContainText("Marketplace open");
  await expect(
    page.locator(".stat", { hasText: "Active trials" }),
  ).toBeVisible();
  await expect(
    page.locator(".stat", { hasText: "Commission waived in trials" }),
  ).toBeVisible();
  await expect(
    page.locator(".ruleRow", { hasText: "Mwenge Wash Hub" }),
  ).toBeVisible();
  await snap(page, "mpa-overview");

  await page.getByRole("button", { name: "Trials" }).click();
  await expect(page.locator(".reportTable")).toContainText("Mwenge Wash Hub");
  await page.getByRole("tab", { name: "Ended, not continued" }).click();
  await expect(page.locator(".reportTable")).toContainText(
    "Kariakoo Quick Wash",
  );
  await snap(page, "mpa-trials");

  await page.getByRole("button", { name: "Monetization" }).click();
  await page.getByRole("button", { name: "Marketplace settings" }).click();
  await expect(page.getByLabel("Trial length (days)")).toHaveValue("30");
  await expect(page.getByLabel("Commission during the trial (%)")).toHaveValue(
    "0.00",
  );
  await expect(page.getByRole("radio", { name: /^Open/ })).toBeChecked();
  await expect(
    page.getByRole("radio", { name: /When the laundry can receive orders/ }),
  ).toBeChecked();
  await snap(page, "mpa-settings");
});

test("operations admin can review but not change Marketplace settings", async ({
  page,
}) => {
  await adminSignIn(page, "support@launder.co.tz");
  await page.getByRole("button", { name: "Monetization" }).click();
  await page.getByRole("button", { name: "Marketplace settings" }).click();
  await expect(page.getByLabel("Trial length (days)")).toBeDisabled();
  await expect(page.getByRole("button", { name: "Save settings" })).toHaveCount(
    0,
  );
});
