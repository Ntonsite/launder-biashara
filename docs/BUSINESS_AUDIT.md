# Launder Business (provider web) — audit

Audited 2026-10-08 against the code at `d016118`. The question for every screen was whether it answers one of:
**what needs my attention now, how is my business performing, what should I do next** — and whether the
numbers behind it are real.

## Summary

The Phase 1 work made the business workspace *real* (every screen reads and writes the API), but it was still
organised like an admin template: five equal KPI cards, a source-mix legend, a recent-orders table. Nothing told
an owner what was late, what was due, what money was still out, or how this month compared with the last.
Several figures were also subtly wrong.

## Findings

### Data and backend

| # | Finding | Severity |
|---|---|---|
| B1 | **No due date on orders.** "Due today" and "overdue" could not be computed at all; the only proxy was status. Service turnaround hours existed but were never applied to an order. | High |
| B2 | **"Today" was fragile.** `/business/analytics` compared `created_at` with a local-midnight value; on the SQLite dev database the offset was dropped, so "today" started at 03:00 local. (SQLite has since been removed; all environments use PostgreSQL.) | High |
| B3 | **Revenue meant "paid orders, all time".** Sales, collections and outstanding money were one concept; payments had no `paid_at`, so money collected *today* for an order taken last week could not be reported. | High |
| B4 | **No period analytics.** One endpoint returned all-time totals plus a 7-day count. No date ranges, no comparisons, no trends, no service, customer or marketplace performance. | High |
| B5 | **Outstanding included orders the laundry had not even accepted** (`payment_status != PAID` over every live order, including `NEW` marketplace orders). | Medium |
| B6 | **Roles too coarse.** Only owner, manager and staff; every role (including staff) could call `/business/analytics` and see all revenue. No cashier or driver. Staff could record payments and create orders. | High |
| B7 | **Order list filters were minimal**: one status list and a source; no due, payment, date or "delivery" view; no counts per view. | Medium |
| B8 | **CSV export silently capped at 100 rows** (it re-fetched page 1 with `page_size=100` in the browser). | Medium |
| B9 | **Customers were a name/phone list.** No order count, spend, last order, preferred services, outstanding balance or segment; a business could not add a customer without an order. | Medium |
| B10 | **Payments could only be recorded as cash.** Mobile money paid to the laundry's own till (common in Tanzania) had to be recorded as cash, corrupting the payment mix. | Medium |
| B11 | **No discount field**; counter discounts were impossible to record and therefore to report. | Low |
| B12 | **Missing indexes** for the new query shapes (business + status, business + due, business + completed, event lookups by status). | Medium |

### UX

| # | Finding |
|---|---|
| U1 | Dashboard had no hierarchy: five equal cards, numbers without comparison or context, two dead quick actions (add service, marketplace status) and no "Needs attention". |
| U2 | No KPI was clickable; there was no path from a number to the orders behind it. |
| U3 | A brand-new laundry saw a wall of zeros and an empty table. |
| U4 | No reports area, no end-of-day view, no print, no PDF. |
| U5 | Orders: a select box instead of views; no urgency (due/overdue) on rows; no items on rows, so staff had to open each order to know what it was. |
| U6 | Payments page listed unpaid orders only in late statuses, client-filtered from 50 rows; no totals, no collected vs outstanding. |
| U7 | Order detail: no due time, no way to set a promised time, cash-only payment button. |
| U8 | Navigation identical for every role except Settings. |
| U9 | On a phone the dashboard rendered the desktop grid squeezed into one column; the important numbers were below the fold. |
| U10 | Onboarding is short and real (profile + location, hours, services) — good. Pricing lives with services, which is right for laundries. Kept; the first-run dashboard now continues where onboarding stops (first order, staff, marketplace). |

## Decisions

* **Analytics are computed in SQL**, grouped per local day in the database (`Africa/Dar_es_Salaam`), never by
  fetching orders into React. Definitions are in [ANALYTICS.md](ANALYTICS.md).
* **Sales, collections and outstanding are separate figures** everywhere (see definitions).
* **Comparisons are like-for-like**: a month in progress is compared with the same number of days of the
  previous month; comparisons are hidden when the previous period has too little data.
* **Close day without locking.** A manager reviews the day, enters the cash actually counted and closes the day;
  Launder stores the snapshot and the cash variance. Transactions are not locked — late payments still record
  normally and show in the next day's collections. Formal period locking is accounting scope, not Phase 1.
* **No Kanban.** With up to nine processing stages a board is wide, scrolls sideways on tablets and hides due
  times. Views (New, In progress, Ready, Delivery…) with due-first sorting and a per-stage pipeline on the
  dashboard serve the same need with less movement.
* **No separate "Analytics" page.** Reports *are* the analytics area; the dashboard links into them. Two places
  showing the same charts would disagree.
* **Branch filter deferred.** The schema has a `branches` table but orders are not yet assigned to branches;
  reports show the business location as the branch. Multi-branch is Phase 2.

## Walk-in flow audit (second request)

Already working before this pass: counter orders priced on the server (per item / per kg), customer found or
created by phone, `source = WALK_IN`, commission charged only on `MARKETPLACE` orders, readable order numbers.

| Gap | Resolution |
|---|---|
| A phone number and name were required — no anonymous walk-in | Optional customer: pick an existing one, type a phone to add someone, type just a name (kept on the order for the slip), or nothing. Guests share one per-laundry record that stays out of the CRM and customer metrics |
| Walk-ins started at `ACCEPTED`, although the clothes are already in the shop | Walk-in drop-offs start at `RECEIVED`; phone/WhatsApp orders still wait at `ACCEPTED` |
| Payment was all-or-nothing, cash only at the counter | Pay later, in full or in part, by cash or mobile money (with reference), at creation or any time after; `PARTIAL` status and `amount_paid`; outstanding uses the balance |
| No package pricing | `PACKAGE` pricing model (fixed-price bundles, whole units) |
| Handing over took two status changes and a separate payment | One "collected" action takes the balance and moves `READY → DELIVERED → COMPLETED` (the state machine is unchanged) |
| No slip | Printable order slip (80 mm or A4): laundry, order number, items, total, paid, balance, ready-by time |
| The form needed several typed fields | Service tiles, defaults for everything, sticky total and *Create & print slip*: a normal walk-in is "tap services → Create" |
