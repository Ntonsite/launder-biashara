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
  this laundry's promotion → this laundry's rate → a promotion for all laundries → the default; a Marketplace trial
  never charges more than the laundry's standard rate (see [trials](#commission-and-conflict-resolution)).
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

## Marketplace activation, provider opt-in and trials

Launder Business works on its own; the Marketplace is optional. Laundries opt in (or accept an invitation), Launder
reviews them, and they get a configurable **commission-free trial** — free means no Launder commission, never free
laundry: customers pay the laundry's normal prices. Code: `app/services/marketplace_program.py`.

### Audit (before this work)

| Found | Now |
|---|---|
| One `status` per Marketplace account; approval made a laundry public immediately | Review, commercial terms and listing are separate states; readiness is computed; public ordering is a separate global switch |
| No trials, no invitations, no "request changes", no draft applications | All built, with an agreement history per laundry |
| A laundry promotion always beat the laundry's own rate | Explicit rule for trials (below); other promotions unchanged |
| Marketplace pauses for plan eligibility lived in the billing service | Moved into the Marketplace lifecycle (same timer and lock) |
| Decisions went only to the general audit log | Also a participation history (`marketplace_events`) and, for money, the pricing audit |

### States (`marketplace_accounts`)

| Dimension | Values |
|---|---|
| `review_status` | NOT_ENROLLED · INVITED · DRAFT · PENDING_REVIEW · CHANGES_REQUESTED · APPROVED · REJECTED |
| `commercial_status` | NONE · PENDING (trial agreed, waiting to start) · TRIAL · STANDARD · EXPIRED (trial over, not continued) |
| `listing_status` | HIDDEN · LISTED · SUSPENDED (admin, with reason) · PAUSED_PLAN (plan has no Marketplace) |
| readiness | computed: profile, location, services, every active service priced, opening hours, pickup radius (if pickup is offered), registration/TIN (if required), terms accepted |
| `launch_cohort` | included while the Marketplace runs as a controlled pilot |

`status` is the summary shown to people: NOT_ENROLLED, INVITED, DRAFT, PENDING_REVIEW, CHANGES_REQUESTED, REJECTED,
APPROVED (approved, waiting for readiness, activation or launch), TRIAL_ACTIVE, ACTIVE, TRIAL_EXPIRED, SUSPENDED.
A laundry is **visible and can receive new Marketplace orders** only when it is approved, LISTED, commercially active
(TRIAL running or STANDARD), its business is active, and ordering is open for it (`marketplace_mode` PUBLIC, or
PILOT and in the launch cohort). Discovery, storefronts, checkout and reorder all use this one rule.

### Journeys

* **Provider-initiated:** Business → Marketplace → *Join Marketplace* → readiness checklist (saved as a draft at any
  point) → accept terms (optionally agree now to continue after the trial) → submit → admin approves (or asks for
  changes, or rejects with a reason) → trial agreement → listed and trial started when ordering is open.
  With `approval_required` off, a complete application is approved automatically.
* **Admin-initiated:** Admin → Marketplace → Laundries (filter *Not listed*) → *Invite*, optionally with individual
  trial terms and the launch group → the laundry sees the invitation and terms → *Confirm and join* (readiness and
  terms still required) → approved without a review queue → trial.
* **Admin controls:** approve with default, individual or no trial; request changes; reject; activate (when automatic
  activation is off); suspend with a reason; reactivate; add to / remove from the launch group; grant, extend or end
  a trial. Every action records actor, reason and time.

### Settings (Admin → Monetization → Marketplace settings)

Initial values written by migration `0005`; administrators change them without code. New values apply to new
applications, approvals and trials; agreements already made keep their terms.

| Setting | Initial | Meaning |
|---|---|---|
| `marketplace_mode` | PUBLIC | OFF (closed: nobody sees or orders; onboarding continues), PILOT (launch cohort only), PUBLIC |
| `marketplace_self_enrollment` | on | Laundries can apply themselves (invitations still work when off) |
| `marketplace_invitations` | on | Admins can invite |
| `marketplace_approval_required` | on | Off = complete applications are approved automatically |
| `marketplace_verification_required` | off | Require a registration number or TIN |
| `marketplace_auto_activate` | on | List approved laundries as soon as they are ready; off = an admin activates |
| `marketplace_trial_enabled` | on | Offer the default trial |
| `marketplace_trial_days` | 30 | Default trial length |
| `marketplace_trial_rate` | 0.00 % | Commission during the default trial |
| `marketplace_trial_start` | WHEN_ORDERS_OPEN | The trial clock starts when the laundry can actually receive orders; ON_APPROVAL only by agreement |
| `marketplace_trial_one_per_business` | on | A trial counts once it has started |
| `marketplace_trial_extension_allowed` / `_max_extensions` | on / 1 | Extensions per trial |
| `marketplace_acceptance_required` | on | When a trial ends without acceptance, new Marketplace orders pause (trial expiry behaviour). Off = accepting the terms when joining (which showed the post-trial rate) counts |
| `marketplace_reminder_days` | 7, 2, 0 | Reminders before the end; 0 = the expiry notice |
| `marketplace_suspension_pauses_trial` | on | Suspended days are added back to a running trial; a suspended trial does not expire |

The **standard** rate after a trial is the commission rules (default 5 %, laundry rates, promotions for everyone) —
the same versioned rules as before, changed under *Marketplace pricing*.

### Agreements (`marketplace_agreements`)

One row per version of a laundry's terms: TRIAL (rate, days, starts/ends, extensions, source DEFAULT_POLICY /
CUSTOM / INVITATION) or STANDARD (accepted at, by). Status OFFERED → PENDING_START → ACTIVE → ENDED (EXPIRED,
ENDED_EARLY, SUPERSEDED) or CANCELLED. A partial unique index allows only one open agreement per laundry. The terms
the provider was shown are stored with the agreement. Existing Marketplace laundries were migrated onto a STANDARD
agreement (they had accepted the terms when they joined).

A running trial is implemented as a commission rule for that laundry tied to the agreement (`agreement_id`). Its rate
never changes; an extension moves its end later (audited), ending early closes it at that moment. The trial's rule
cannot be ended as an ordinary rule, and no other promotion for that laundry may overlap its dates.

### Commission and conflict resolution

Precedence is unchanged (laundry promotion › laundry rate › promotion for all › default) with one explicit rule for
trials: **a trial never makes a laundry pay more than it would without it.** While a trial runs, the lower of the
trial rate and the laundry's standard rate applies. So a special laundry rate never takes away a promised trial
(trial 0 %, special 3 % → 0 %), and a trial never takes away a better special rate (trial 2 %, special 1 % → 1 %).

Each Marketplace order stores the rule and rate applied, the standard rate it would otherwise have paid
(`commission_standard_rate`) and the agreement version in force (`marketplace_agreement_id`). The ledger entry stores
`waived_amount` = standard rate on the same basis − commission charged (negated on a refund reversal). Orders are
never re-priced: an order placed during the trial is charged the trial rate even if it completes after the trial ends.
Walk-in, phone and WhatsApp orders remain exempt.

### Lifecycle (scheduled, idempotent)

`MarketplaceProgram.run()` runs inside the billing cycle (every `BILLING_INTERVAL_SECONDS`, Postgres advisory lock),
after every Marketplace settings change, and on demand (*Run trial lifecycle now*). It rows-locks accounts
(`FOR UPDATE SKIP LOCKED`) and:

1. starts waiting trials when ordering opens for the laundry (and lists ready laundries) — a blocked start (an
   overlapping promotion) is skipped and the owner is told, without failing the run;
2. sends the most urgent due reminder once per trial and extension (late runs never send a backlog);
3. ends trials at their end time: standard terms if accepted (or acceptance not required), otherwise EXPIRED —
   new Marketplace orders stop, orders in progress continue, Launder Business and history are untouched;
4. pauses/restores listings with plan eligibility (never lifting an admin suspension).

Running it twice changes nothing the second time.

### Reporting

* **Admin → Marketplace → Overview:** applications to review, invited, approved, waiting to start, active trials,
  laundries taking orders, expired, suspended, trial → paid conversion (ended trials followed by a STANDARD agreement
  ÷ ended trials), trials ending in 30 days (with whether the laundry will continue), Marketplace GMV, commission net,
  standard vs trial commission and commission waived — all from orders and the commission ledger for the period, with
  the earned − reversed = net reconciliation line. *Trials* lists running, ending, waiting, converted and expired trials
  with each trial's orders, sales and savings.
* **Laundry:** the Marketplace page shows the trial dashboard (dates, days left, current and post-trial rate, orders,
  sales, commission saved — settled plus still to come — and new customers whose first order with the laundry came
  through the Marketplace during the trial). Reports add orders placed in the trial, trial vs standard commission and
  commission waived next to walk-in vs Marketplace sales.

### Permissions

| Action | Who |
|---|---|
| Review, approve (default trial), request changes, reject, invite (default terms), activate, suspend, reactivate, launch group | Any admin |
| Individual trial terms, approval without a trial, grant / extend / end trials, Marketplace settings, lifecycle run | SUPER_ADMIN, FINANCE_ADMIN |
| Join, save draft, accept terms | Laundry owner (own laundry only) |
| View Marketplace status | Owner and manager |

### API

Provider: `GET /business/marketplace`, `PUT /business/marketplace/application` (draft),
`POST /business/marketplace/application` (submit or confirm an invitation), `POST /business/marketplace/accept-terms`.
Admin (`/admin/marketplace`): `overview`, `providers` (+ `/{business_id}`, `/{business_id}/{approve|reject|
request-changes|activate|suspend|reactivate}`, `/invite`, `/cohort`, `/trial/grant|extend|end`), `trials?bucket=`,
`settings` (GET/PUT), `lifecycle/run`. The older `/admin/marketplace-applications` endpoints still work.

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
* Marketplace reminders and decisions reach laundries in the app (page, dashboard banner, notification rows); SMS /
  e-mail delivery is not connected.
* "Commission waived" is the standard rate on the trial order's basis; if the standard rule has a minimum per order,
  the minimum is not included in the waived figure.
* The launch cohort is per laundry; there is no geographic rollout (by area) yet.
