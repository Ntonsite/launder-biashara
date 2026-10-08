# Launder — commercial model, subscriptions and pricing

Launder earns in two independent ways:

| Stream | What | Who pays |
|---|---|---|
| **Launder Business (SaaS)** | Monthly or yearly plan | The laundry, by invoice |
| **Launder Marketplace** (optional) | Commission on completed Marketplace orders (+ optional listing fee) | Deducted from the laundry's Marketplace sales |

Every price, rate, entitlement and special term is data that administrators change in **Admin → Monetization**.
Nothing is hardcoded in business logic. The initial values below are written once by migration `0004`.

| Plan | Monthly | Yearly | Trial | Includes |
|---|---|---|---|---|
| Starter (default) | Free | Free | — | Walk-in/counter orders, end-of-day report, 2 team members, Marketplace eligible |
| Pro | TZS 25,000 | TZS 250,000 | 14 days | + customer CRM, all reports, CSV, performance insights, cashier/driver/manager roles, 10 team members |
| Business Plus | TZS 60,000 | TZS 600,000 | 14 days | + 50 team members, 5 branches (stored; multi-branch not built yet) |

Marketplace: standard listing free (listing fee setting = 0), default commission **5 %** of laundry services on
completed Marketplace orders. Walk-in, phone and WhatsApp orders: **0 %, always**.

## Audit (before this work)

| Found | Now |
|---|---|
| One `commission_rate` column per Marketplace account (default from `settings.default_commission_rate`), edited in place | Versioned commission rules with effective dates; the config default is gone; old non-default rates were migrated into laundry rules |
| `commissions`: one row per order, no reversals, rate looked up at completion (a rate change re-priced open orders) | A ledger: `EARNED` and `REVERSED` entries, unique per order and type, with the rule, rate and basis recorded; rate fixed when the order is placed |
| Refunds left commission untouched | Refunding a completed Marketplace order writes a reversal |
| No plans, subscriptions, invoices, entitlements, trials, pilots or pricing audit | All built (below) and reuse the existing auth, RBAC, audit and payment conventions |
| Admin approval accepted an ad-hoc commission rate | Still accepted (finance roles only) and turned into a laundry rule |

## Data model (migration 0004)

`subscription_plans`, `plan_prices` (versioned by `effective_from/effective_to`), `plan_features`,
`business_subscriptions` (one current row per laundry), `subscription_invoices` + `subscription_invoice_lines`,
`subscription_payments`, `marketplace_commission_rules`, `commissions` (now the ledger), `commercial_overrides`,
`pilot_programs`, `pilot_enrollments`, `platform_settings`, `pricing_audit_logs`. Orders gained
`commission_rule_id` and `commission_rate`. Money is whole TZS in integer columns (exact; TZS has no minor unit in
use); rates and percentages are `NUMERIC` with `Decimal` arithmetic and half-up rounding.

## Commission

* **Eligible:** `source = MARKETPLACE` only. Walk-in, phone and WhatsApp orders are never charged.
* **Which rule:** fixed when the order is **placed** (`orders.commission_rule_id`). Precedence:
  this laundry's promotion → this laundry's rate → a promotion for all laundries → the default.
* **Basis:** services subtotal, minus discounts unless the rule says "before discounts", plus the pickup fee only if
  the rule includes it. A minimum commission never exceeds the basis.
  *Example:* services TZS 30,000 at 5 % → commission TZS 1,500, laundry TZS 28,500.
* **Earned:** when the order is **completed** (which already requires full payment). One `EARNED` ledger entry.
* **Refund:** refunding the order's payment writes one `REVERSED` entry for the full earned amount. Partial refunds
  are not supported anywhere in Phase 1.
* **Cancellation:** nothing is earned before completion; completed orders cannot be cancelled.
* **Duplicates:** `(order_id, entry_type)` is unique; retries and concurrent requests cannot double count.
* **Changing rates:** a new rule starts now or later (never in the past), closes the previous one at that moment
  and cannot overlap another rule of the same scope. Historical orders keep their rule.

## Subscriptions and billing

| Event | Result |
|---|---|
| Laundry on the default plan | No subscription row needed; nothing invoiced |
| Choose a paid plan | First time on that plan and not already paying: trial for the plan's trial days. Otherwise ACTIVE with an invoice |
| Trial ends | First invoice for the next period |
| Period ends | Next period and its invoice (unique per subscription and period) |
| Invoice unpaid | Due after the payment terms (setting, default 7 days) → PAST_DUE; after the plan's grace days → EXPIRED, invoice voided, default plan applies |
| Upgrade | Immediate; unpaid time already paid for is credited on the new invoice |
| Downgrade / cancel | At the end of the paid period |
| Special terms | Applied when each invoice is issued, shown as lines: free access, special monthly price, or % discount (never stacked; the best one applies) |

**Nothing is ever charged automatically.** A payment exists only when a finance administrator records money Launder
actually received (cash, bank transfer or mobile money to Launder's account), with an optional reference (unique) and
an `Idempotency-Key`. Live mobile-money collection for subscriptions needs a payment gateway and is not connected.

The billing cycle (`BillingService.run`) is idempotent. The API runs it every `BILLING_INTERVAL_SECONDS` (900) under
a Postgres advisory lock; finance admins can also run it. Access decisions do not wait for it: entitlements are
resolved from timestamps, so trials, grace periods and special terms end on time.

## Entitlements (enforced by the API)

| Feature key | Gates |
|---|---|
| `walk_in_orders` | Creating counter / walk-in orders |
| `customer_crm` | Customer profiles, notes, segments, spend ranking |
| `advanced_reports` | Weekly, monthly, sales, orders, customers, Marketplace, payments reports (end of day is always available) |
| `data_export` | CSV exports |
| `team_roles` | Adding managers, cashiers, drivers (staff always allowed); plus the plan's team limit |
| `performance_insights` | Owner dashboard performance, trends and insights |
| `marketplace_eligible` | Applying to / staying on the Marketplace |

Missing features return `402 PLAN_UPGRADE_REQUIRED` with the plans that include it; limits return
`402 PLAN_LIMIT_REACHED`. Effective plan = the higher of an active complimentary grant (admin or pilot) and the
current subscription (while trialling, paid up or within grace); otherwise the default plan.

**Marketplace and plans.** By default every plan is Marketplace-eligible, so no paid plan is required. If an admin
removes `marketplace_eligible` from a plan, the billing cycle pauses listings of laundries on that plan (reason
"Your current plan does not include a Marketplace listing") and restores them automatically when they are eligible
again. Suspensions an administrator decided are never lifted automatically. Approval and reinstatement also check
eligibility.

## Pilots

A pilot programme gives its laundries a plan for N days (a complimentary grant per enrolment). It never lists a
laundry on the Marketplace and never charges anyone. Laundries are reminded `trial_reminder_days` before the end
(page notice + in-app notification). At the end the programme's policy applies:

* `DOWNGRADE` — the grant expires; the laundry is on the default plan (or its own subscription).
* `INVOICE` — the laundry is offered the plan: a subscription with an open invoice; access continues through the
  payment terms and grace; unpaid → default plan. Nothing is charged unless the laundry pays.

The seed puts FreshWash in "Provider pilot 2026" (Pro, 90 days, then the free plan).

## Who can do what

| Role | Monetization |
|---|---|
| `SUPER_ADMIN`, `FINANCE_ADMIN` | Everything: plans, prices, features, commission rules, settings, special terms, pilots, assign plans, record payments, void invoices, run billing |
| `ADMIN` (operations) | View only |
| Laundry owner | Own plan, upgrade/downgrade/cancel, own invoices and payments, own commission terms |
| Other laundry roles | None |

Every change is written to `pricing_audit_logs` with actor, reason, and previous and new values.

## Reporting

* **Admin → Revenue:** MRR (current paying subscriptions, yearly ÷ 12), paying / trialling / complimentary /
  past-due / expired, invoiced, subscription money received, unpaid invoices, Marketplace GMV, commission earned,
  reversed and net, by laundry, and a reconciliation check (invoice balances = payments recorded).
  Platform revenue = subscription money received + net commission — two separate streams, never double counted.
* **Laundry reports** (monthly, Marketplace): walk-in vs Marketplace sales (sources), commission, net Marketplace
  amount, and "what you paid Launder" (subscription payments + net commission) separate from sales.

## API

Provider: `GET /business/subscription`, `GET /business/subscription/preview`, `POST /business/subscription`,
`POST /business/subscription/cancel`, `GET /business/invoices/{id}`.
Admin (`/admin/monetization`): `revenue`, `features`, `plans` (+ `/{id}`, `/{id}/prices`, `/{id}/features`),
`commission/rules` (+ `/{id}/end`), `commission/preview`, `settings`, `overrides` (+ `/{id}/revoke`),
`pilots` (+ enrolments, remove, close), `businesses` (+ `/{id}/subscription`), `invoices` (+ `/{id}/payments`,
`/{id}/void`), `billing/run`, `audit`.

## Limitations

* Subscription payments are recorded manually; no mobile-money or card gateway for subscriptions yet.
* No VAT/TRA EFD receipts on invoices; amounts are VAT-inclusive as entered.
* No proration on downgrades (they wait for the period end) and no partial refunds.
* Branch limits are stored and shown, but multi-branch is not built, so they cannot be enforced yet.
* Notifications to laundries are in-app (page notices + notification rows); SMS/e-mail delivery is not connected.
* Marketplace Plus (premium listing) is not built; the listing fee setting is the hook for Marketplace charges.
