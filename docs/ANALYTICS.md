# Launder Business — analytics, reports and roles

How every number in the provider workspace is defined and computed. Code: `apps/api/app/services/analytics.py`,
`app/domain/periods.py`, `app/domain/permissions.py`.

## Principles

* Computed in PostgreSQL with aggregate queries scoped to one business; nothing is calculated from raw order
  lists in the browser. Daily buckets use `date(timezone('Africa/Dar_es_Salaam', ts))`.
* Sales, collections and outstanding money are **different numbers** and are never mixed.
* Comparisons are like-for-like and hidden when they would mislead.
* Insights are plain, deterministic statements with minimum-data rules. No AI.

## Definitions

| Term | Definition |
|---|---|
| Sales | Value (`total`, after discount, incl. pickup fee) of orders **created** in the period, excluding cancelled/declined |
| Orders | Count of those orders |
| Average order | Sales ÷ orders (half-up to whole TZS) |
| Collected | Sum of payments whose `paid_at` falls in the period, for any order, any method; part payments count when received |
| Refunded | Payments whose `refunded_at` falls in the period |
| Outstanding (now) | Balance (`total − amount_paid`) of live orders the laundry has accepted (status beyond `NEW`) that are not fully paid |
| Unpaid from period | The same, limited to orders created in the period |
| Discounts | Sum of counter discounts on orders created in the period |
| Due / overdue | Every order has a promised `due_at` (start + slowest service's turnaround, or what the counter set). Overdue = not yet `READY` and `due_at` passed. Due soon = within 4 h |
| Ready on time | Orders that reached `READY` in the period with `ready_at ≤ due_at` ÷ all that reached `READY` |
| Delayed | Orders due in the period that became ready late or are still not ready |
| Average time to ready | Mean of `ready_at − created_at` for orders ready in the period |
| Opening / carried forward | Orders open (not completed/cancelled/declined) at the start / end of the period |
| New customer | First non-cancelled order with *this laundry* falls in the period |
| Returning customer | Ordered in the period and had ordered before it |
| Repeat rate | Returning ÷ customers served in the period |
| Frequent (CRM) | 3+ orders in the last 60 days. *Not seen recently* = last order 45+ days ago. Nobody is labelled "churned" |
| Walk-in guest | One shared record per laundry for customers who leave no details. Its orders count in sales, collections and reports; it is excluded from customer counts and the CRM |
| Marketplace sales | Sales with `source = MARKETPLACE` |
| Commission (accrued) | Ledger entries for Marketplace orders created in the period: earned on completion, at the rule fixed when the order was placed, less any reversals (see [MONETIZATION.md](MONETIZATION.md)) |
| Commission still to come | Estimate for Marketplace orders in the period not yet completed, each at its own rule |
| Net from Marketplace | Marketplace sales − accrued − estimated commission |
| What you paid Launder | Subscription payments received + net commission earned in the period (separate from sales) |

Walk-in, phone and WhatsApp orders are **never** charged commission (`CommissionService` only accepts
`source = MARKETPLACE`; covered by `tests/test_walk_in.py` and `tests/test_monetization.py`). Plan features gate
some reports — see [MONETIZATION.md](MONETIZATION.md#entitlements-enforced-by-the-api).

## Periods and comparisons

`today, yesterday, last_7_days, this_week (Mon–Sun), last_week, this_month, last_month, custom` (≤ 366 days).

| Period | Compared with |
|---|---|
| Today / yesterday | Same weekday last week (laundry demand is weekly) — today up to the same time |
| This / last week | Previous week — this week up to the same point |
| This / last month | Previous calendar month — **month to date vs the same days of last month**, clipped to that month's length (30 Mar is compared with all of February, not with 2 March) |
| Last 7 days, custom | The period of the same length immediately before |

A percentage change is shown only when the comparison period has **at least 5 orders** and a non-zero value.
Colour depends on the metric: more sales is good; more money outstanding or more late orders is not.

## Insights (owner dashboard and monthly report)

| Insight | Shown when |
|---|---|
| Busiest weekday | ≥ 30 orders over the last 8 weeks, ≥ 4 active weeks, and the top day is ≥ 15 % above the average |
| Top service's share of service revenue | ≥ 10 orders this month |
| Marketplace share of orders | ≥ 10 orders this month and any Marketplace orders |
| Average order up/down | ≥ 10 orders in both periods and a change of ≥ 3 % |
| Customers who ordered more than once | ≥ 3 such customers |
| Orders ready later than promised | ≥ 1 |

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /business/dashboard` | Role-aware: attention items (each with a link to a filtered view), today, stage pipeline, and for owners month-to-date performance, 30-day trend, Marketplace, customers, insights; setup checklist when there are no orders |
| `GET /business/reports` | Report kinds the caller may open |
| `GET /business/reports/{kind}?period=&start=&end=` | `daily, weekly, monthly, sales, orders, customers, marketplace, payments` |
| `GET /business/reports/{kind}/export.csv?…&lang=en\|sw` | Same data as CSV with laundry, branch, period and generated time |
| `POST /business/day-close`, `GET /business/day-close` | Close a day with counted cash; history |
| `GET /business/orders?view=&due=&payment=&source=&status=&date_from=&date_to=&q=` | Order views and filters |
| `GET /business/orders/counts` | Counts per view and urgency for the tabs |
| `GET /business/orders/export.csv?…` | Every matching order (up to 10,000) |
| `GET /business/payments?period=` | Payments received in the period + money summary |
| `GET/POST /business/customers`, `GET /business/customers/{id}`, `PUT …/notes` | CRM |
| `POST /business/orders`, `POST /business/orders/{id}/payments`, `POST /business/orders/{id}/collect` | Walk-in order, full/part payment, counter hand-over |

## Roles

Capabilities live in `app/domain/permissions.py`; every endpoint checks them, and the web navigation is driven by
the same list from `GET /business/profile`.

| Role | Sees and does |
|---|---|
| Owner | Everything: money, performance, customers, Marketplace, all reports, team, settings |
| Manager | Operations, orders, payments, customers, services, settings; daily, weekly, orders and payments reports; no performance, monthly, sales, customers or Marketplace reports |
| Cashier | Create orders, find/add customers, take payments, accept/receive/hand over orders; money on the dashboard; no reports |
| Staff | Work queue, items, all processing stages, due times; no money figures, customers or reports |
| Driver | Pickup orders in pickup/delivery stages only; collect, deliver, record cash on delivery |

## End of day: close without locking

Closing a day stores the day's totals, the cash expected, the cash counted and the variance (`day_closes`).
It does **not** lock transactions: a payment recorded after closing still appears in that day's collections and a
re-printed report shows the new figure next to the stored count. Period locking and adjustments are accounting
scope and were deliberately left out of Phase 1.

## Indexes

`orders (business_id, status)`, `(business_id, due_at)`, `(business_id, completed_at)`,
`(business_id, customer_id, created_at)`, existing `(business_id, created_at)`; `payments.paid_at`,
`payments.refunded_at`; `order_status_events (to_status, created_at)`; `order_items.service_id`.
Verified with `EXPLAIN` on the seeded database: overdue and pipeline counts use `ix_orders_business_status`;
period series use the business index. Order lists load customers and items with `selectinload` (no N+1).
