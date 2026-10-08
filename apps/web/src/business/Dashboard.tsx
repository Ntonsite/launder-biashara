import { useCallback, useEffect, useState } from "react";
import type { TFunction } from "i18next";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  ArrowRight,
  Banknote,
  CheckCircle2,
  Circle,
  Clock,
  Lock,
  PackageCheck,
  Plus,
  Sparkles,
  Store,
  Truck,
  UserPlus,
  Wallet,
} from "lucide-react";
import { api } from "../lib/api";
import type { MarketplaceView } from "./Marketplace";
import {
  dayMonth,
  errorMessage,
  longDate,
  money,
  moneyShort,
  percent,
  statusLabel,
  weekdayName,
} from "../lib/format";
import { Notice } from "../customer/ui";
import { AppFrame, useProfile } from "./shell";
import { Bars, Delta, SectionHead, StatCard, useCan } from "./ui";
import type { Attention, Dashboard as Data, Insight } from "./types";
import { BillingNotice, type BillingView } from "./Billing";

const REFRESH_MS = 120_000;
const ICONS: Record<string, typeof Clock> = {
  overdue: AlertTriangle,
  marketplace_new: Store,
  payments_stuck: Wallet,
  due_today: Clock,
  pickups_today: Truck,
  deliveries: Truck,
  outstanding: Banknote,
  uncollected: PackageCheck,
};

export function linkTo(path: string, query: Record<string, string> = {}) {
  const q = new URLSearchParams(query).toString();
  return q ? `${path}?${q}` : path;
}

export default function Dashboard() {
  const { t } = useTranslation();
  const { profile } = useProfile();
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api<Data>("/api/v1/business/dashboard", { auth: "business" })
      .then((d) => {
        setData(d);
        setError("");
      })
      .catch((e) => setError(errorMessage(e)));
  }, []);
  useEffect(() => {
    load();
    // An operations screen left open on the counter should not go stale.
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") load();
    }, REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

  const hour = new Date().getHours();
  const greeting = t(
    hour < 12 ? "biz.morning" : hour < 17 ? "biz.afternoon" : "biz.evening",
  );
  const name = data?.business.name ?? profile?.name ?? "";

  return (
    <AppFrame
      title={name ? t("ops.dash.greeting", { greeting, name }) : greeting}
      kicker={longDate(new Date())}
    >
      <QuickActions />
      {error && <Notice>{error}</Notice>}
      {!data ? (
        !error && <div className="tableLoading">{t("common.loading")}</div>
      ) : (
        <div className="opsDash">
          <BillingBanner />
          <MarketplaceBanner />
          {data.first_run && <FirstRun steps={data.first_run} />}
          {data.has_orders && <Today data={data} />}
          <NeedsAttention items={data.attention} hasOrders={data.has_orders} />
          {data.has_orders && <Pipeline counts={data.pipeline} />}
          {data.performance && <Performance data={data} />}
          {data.performance_locked && (
            <section className="panel upgradeCard">
              <Lock aria-hidden />
              <div>
                <h2>{t("billing.lockedPerformance")}</h2>
                <p className="muted">{t("billing.lockedPerformanceText")}</p>
              </div>
              <Link className="primary" to="/app/billing">
                {t("billing.seePlans")}
              </Link>
            </section>
          )}
          {(data.marketplace || data.customers) && (
            <div className="opsCols even dashExtra">
              {data.marketplace && <MarketplaceCard data={data} />}
              {data.customers && <CustomersCard data={data} />}
            </div>
          )}
        </div>
      )}
    </AppFrame>
  );
}

/** The one billing message an owner should see on the dashboard (trial/pilot ending, invoice due). */
function BillingBanner() {
  const can = useCan();
  const [top, setTop] = useState<BillingView["notices"][number] | null>(null);
  const allowed = can("billing.manage");
  useEffect(() => {
    if (!allowed) return;
    api<BillingView>("/api/v1/business/subscription", { auth: "business" })
      .then((v) => {
        const order = { danger: 0, warning: 1, info: 2 };
        const urgent = v.notices.filter(
          (n) => n.level !== "info" || n.kind.startsWith("invoice"),
        );
        setTop(
          urgent.sort((a, b) => order[a.level] - order[b.level])[0] ?? null,
        );
      })
      .catch(() => undefined);
  }, [allowed]);
  return top ? (
    <div className="dashBanner">
      <BillingNotice n={top} />
    </div>
  ) : null;
}

/** Owners only: the Marketplace trial is about to end, or has ended and new Marketplace orders are paused. */
function MarketplaceBanner() {
  const { t } = useTranslation();
  const can = useCan();
  const [view, setView] = useState<MarketplaceView | null>(null);
  const allowed = can("marketplace.manage");
  useEffect(() => {
    if (!allowed) return;
    api<MarketplaceView>("/api/v1/business/marketplace", { auth: "business" })
      .then(setView)
      .catch(() => undefined);
  }, [allowed]);
  if (!view) return null;
  const a = view.agreement;
  const ending =
    view.status === "TRIAL_ACTIVE" &&
    a?.days_left != null &&
    a.days_left <= 7 &&
    !view.post_trial_accepted_at &&
    view.acceptance_required;
  if (!ending && view.status !== "TRIAL_EXPIRED") return null;
  return (
    <div className="dashBanner">
      <div className={`billingNotice ${ending ? "warning" : "danger"}`}>
        <span>
          {ending
            ? t("mpx.banner.ending", { count: a!.days_left ?? 0 })
            : t("mpx.banner.expired")}
        </span>
        <Link className="textLink" to="/app/marketplace">
          {t("mpx.banner.action")}
        </Link>
      </div>
    </div>
  );
}

function QuickActions() {
  const { t } = useTranslation();
  const can = useCan();
  const actions = [
    can("orders.create") && [
      "/app/orders/new",
      Plus,
      "ops.quick.newOrder",
      true,
    ],
    can("customers.view") && [
      "/app/customers?add=1",
      UserPlus,
      "ops.quick.addCustomer",
      false,
    ],
    can("money.view") && [
      "/app/payments",
      Banknote,
      "ops.quick.receivePayment",
      false,
    ],
    can("orders.deliveries_only")
      ? ["/app/orders?view=delivery", Truck, "ops.quick.deliveries", true]
      : [
          "/app/orders?view=ready",
          PackageCheck,
          "ops.quick.readyOrders",
          false,
        ],
  ].filter(Boolean) as [string, typeof Plus, string, boolean][];
  return (
    <nav className="quickActions" aria-label={t("biz.quickActions")}>
      {actions.map(([to, Icon, key, primary]) => (
        <Link key={key} to={to} className={primary ? "primary" : "outlineBtn"}>
          <Icon aria-hidden /> {t(key)}
        </Link>
      ))}
    </nav>
  );
}

function FirstRun({ steps }: { steps: NonNullable<Data["first_run"]> }) {
  const { t } = useTranslation();
  const done = steps.filter((s) => s.done).length;
  return (
    <section className="firstRun">
      <div>
        <p className="kicker">{t("ops.first.kicker")}</p>
        <h2>{t("ops.first.title")}</h2>
        <p>{t("ops.first.text")}</p>
        <div
          className="progress"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={steps.length}
          aria-valuenow={done}
          aria-label={t("ops.first.progress", { done, total: steps.length })}
        >
          <i style={{ width: `${(done / steps.length) * 100}%` }} />
        </div>
        <small>{t("ops.first.progress", { done, total: steps.length })}</small>
      </div>
      <ol>
        {steps.map((s) => (
          <li key={s.key} className={s.done ? "done" : ""}>
            {s.done ? <CheckCircle2 aria-hidden /> : <Circle aria-hidden />}
            {s.done ? (
              <span>{t(`ops.first.steps.${s.key}`)}</span>
            ) : (
              <Link to={s.path}>
                {t(`ops.first.steps.${s.key}`)} <ArrowRight aria-hidden />
              </Link>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}

function Today({ data }: { data: Data }) {
  const { t } = useTranslation();
  const can = useCan();
  const d = data.today;
  const day = data.local_date;
  const ordersToday = `/app/orders?date_from=${day}&date_to=${day}`;
  if (can("orders.deliveries_only"))
    return (
      <section className="todayGrid" aria-label={t("ops.dash.today")}>
        <StatCard
          label={t("ops.dash.pickups")}
          value={d.pickups}
          to="/app/orders?view=delivery"
        />
        <StatCard
          label={t("ops.dash.deliveries")}
          value={d.deliveries}
          to="/app/orders?view=delivery"
        />
      </section>
    );
  if (!d.sales)
    return (
      <section className="todayGrid" aria-label={t("ops.dash.today")}>
        <StatCard
          label={t("ops.dash.ordersToday")}
          value={d.orders.value}
          to={ordersToday}
        />
        <StatCard
          label={t("ops.dash.processing")}
          value={d.processing}
          to="/app/orders?view=in_progress"
        />
        <StatCard
          label={t("ops.dash.dueToday")}
          value={d.due_today}
          sub={
            d.overdue
              ? t("ops.dash.overdueSub", { count: d.overdue })
              : undefined
          }
          tone={d.overdue ? "alert" : undefined}
          to="/app/orders?due=today"
        />
        <StatCard
          label={t("ops.dash.ready")}
          value={d.ready}
          to="/app/orders?view=ready"
        />
      </section>
    );
  return (
    <section className="todayGrid" aria-label={t("ops.dash.today")}>
      <StatCard
        label={t("ops.dash.ordersToday")}
        value={d.orders.value}
        metric={d.orders}
        compareTo={d.compare_to}
        inProgress
        sub={t("ops.dash.processingSub", { count: d.processing })}
        to={ordersToday}
      />
      <StatCard
        label={t("ops.dash.salesToday")}
        value={moneyShort(d.sales.value)}
        metric={d.sales}
        compareTo={d.compare_to}
        inProgress
        sub={t("ops.dash.collectedSub", { amount: money(d.collected ?? 0) })}
        to={can("reports.operational") ? "/app/reports/daily" : undefined}
      />
      <StatCard
        label={t("ops.dash.ready")}
        value={d.ready}
        sub={
          d.ready_unpaid
            ? t("ops.dash.readyUnpaidSub", { count: d.ready_unpaid })
            : undefined
        }
        to="/app/orders?view=ready"
      />
      <StatCard
        label={t("ops.dash.outstanding")}
        value={moneyShort(d.outstanding?.amount ?? 0)}
        sub={t("ops.dash.ordersCount", { count: d.outstanding?.count ?? 0 })}
        to="/app/payments"
      />
    </section>
  );
}

function NeedsAttention({
  items,
  hasOrders,
}: {
  items: Attention[];
  hasOrders: boolean;
}) {
  const { t } = useTranslation();
  return (
    <section className="panel attention">
      <SectionHead
        title={t("ops.dash.attention")}
        question={t("ops.dash.attentionQ")}
      />
      {items.length === 0 ? (
        <div className="allClear">
          <CheckCircle2 aria-hidden />
          <div>
            <b>{t("ops.dash.allClear")}</b>
            <p>
              {t(hasOrders ? "ops.dash.allClearSub" : "ops.dash.allClearNew")}
            </p>
          </div>
        </div>
      ) : (
        <ul>
          {items.map((a) => {
            const Icon = ICONS[a.key] ?? AlertTriangle;
            return (
              <li key={a.key}>
                <Link
                  to={linkTo(a.path, a.query)}
                  className={`attn ${a.severity}`}
                >
                  <Icon aria-hidden />
                  <span>
                    <b>
                      {t(`ops.attention.${a.key}`, {
                        count: a.count,
                        amount: money(a.amount ?? 0),
                        hours: a.hours,
                        minutes: a.minutes,
                      })}
                    </b>
                    {a.key === "due_today" && !!a.soon && (
                      <small>
                        {t("ops.attention.dueSoon", {
                          count: a.soon,
                          hours: a.hours,
                        })}
                      </small>
                    )}
                  </span>
                  <em>
                    {t(`ops.attention.cta.${a.key}`)} <ArrowRight aria-hidden />
                  </em>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

const STAGES = [
  "NEW",
  "ACCEPTED",
  "AWAITING_PICKUP",
  "RECEIVED",
  "WASHING",
  "DRYING",
  "IRONING",
  "QUALITY_CHECK",
  "READY",
  "OUT_FOR_DELIVERY",
  "DELIVERED",
];

function Pipeline({ counts }: { counts: Record<string, number> }) {
  const { t } = useTranslation();
  const max = Math.max(1, ...Object.values(counts));
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  // Pickup legs only matter to laundries that do pickups.
  const stages = STAGES.filter(
    (s) => counts[s] || !["AWAITING_PICKUP", "OUT_FOR_DELIVERY"].includes(s),
  );
  return (
    <section className="panel pipelinePanel">
      <SectionHead
        title={t("ops.dash.operations")}
        question={t("ops.dash.operationsQ", { count: total })}
      />
      <ul className="pipeline">
        {stages.map((s) => (
          <li key={s} className={counts[s] ? "" : "zero"}>
            <Link to={`/app/orders?status=${s}`}>
              <span>{statusLabel(s)}</span>
              <i aria-hidden>
                <b style={{ width: `${((counts[s] ?? 0) / max) * 100}%` }} />
              </i>
              <strong>{counts[s] ?? 0}</strong>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Performance({ data }: { data: Data }) {
  const { t } = useTranslation();
  const p = data.performance!;
  const [series, setSeries] = useState<"sales" | "orders">("sales");
  const last = p.trend.length - 1;
  return (
    <section className="panel performance">
      <SectionHead
        title={t("ops.dash.performance")}
        question={t("ops.dash.performanceQ")}
        action={
          <Link className="textLink" to="/app/reports/monthly">
            {t("ops.dash.openMonthly")} <ArrowRight aria-hidden />
          </Link>
        }
      />
      <div className="perfStats">
        <StatCard
          label={t("ops.metric.salesMtd")}
          value={moneyShort(p.sales.value)}
          metric={p.sales}
          compareTo={p.period.compare_to}
          inProgress={p.period.in_progress}
          sub={
            p.sales.change_pct == null ? t("ops.compare.notEnough") : undefined
          }
        />
        <StatCard
          label={t("ops.metric.orders")}
          value={p.orders.value}
          metric={p.orders}
          compareTo={p.period.compare_to}
          inProgress={p.period.in_progress}
        />
        <StatCard
          label={t("ops.metric.averageOrder")}
          value={money(p.average_order.value)}
          metric={p.average_order}
          sub={
            p.average_order.previous != null
              ? t("ops.metric.fromPrevious", {
                  amount: money(p.average_order.previous),
                })
              : undefined
          }
        />
        <StatCard
          label={t("ops.metric.collected")}
          value={moneyShort(p.collected.value)}
          metric={p.collected}
          compareTo={p.period.compare_to}
          inProgress={p.period.in_progress}
        />
      </div>
      <div className="perfBody">
        <div className="trend">
          <div
            className="segmented"
            role="group"
            aria-label={t("ops.dash.trend")}
          >
            {(["sales", "orders"] as const).map((k) => (
              <button
                key={k}
                className={series === k ? "on" : ""}
                aria-pressed={series === k}
                onClick={() => setSeries(k)}
              >
                {t(`ops.dash.trend_${k}`)}
              </button>
            ))}
          </div>
          <Bars
            label={t(`ops.dash.trend_${series}`)}
            valueLabel={series === "sales" ? money : String}
            points={p.trend.map((d, i) => ({
              key: d.date,
              label: dayMonth(d.date),
              value: d[series],
              muted: i === last,
            }))}
          />
          <small className="muted">{t("ops.dash.trendNote")}</small>
        </div>
        {!!data.insights?.length && <Insights items={data.insights} />}
      </div>
    </section>
  );
}

export function insightText(t: TFunction, i: Insight) {
  return t(`ops.insight.${i.key}`, {
    ...i,
    weekday: typeof i.weekday === "number" ? weekdayName(i.weekday) : "",
    share: percent(i.share as number),
    change: percent(i.change as number),
    value: typeof i.value === "number" ? money(i.value) : "",
    previous: typeof i.previous === "number" ? money(i.previous) : "",
  });
}

export function Insights({ items }: { items: Insight[] }) {
  const { t } = useTranslation();
  return (
    <aside className="insights">
      <h3>
        <Sparkles aria-hidden /> {t("ops.dash.insights")}
      </h3>
      <ul>
        {items.map((i) => (
          <li key={i.key}>{insightText(t, i)}</li>
        ))}
      </ul>
      <small>{t("ops.dash.insightsNote")}</small>
    </aside>
  );
}

function MarketplaceCard({ data }: { data: Data }) {
  const { t } = useTranslation();
  const m = data.marketplace!;
  const inProgress = data.performance?.period.in_progress;
  const compareTo = data.performance?.period.compare_to;
  return (
    <section className="panel">
      <SectionHead
        title={t("ops.dash.marketplace")}
        question={t("ops.dash.marketplaceQ")}
        action={
          <Link className="textLink" to="/app/reports/marketplace">
            {t("ops.dash.details")} <ArrowRight aria-hidden />
          </Link>
        }
      />
      <dl className="figures">
        <div>
          <dt>{t("ops.mp.orders")}</dt>
          <dd>
            {m.orders}
            <Delta
              metric={m.orders_metric}
              compareTo={compareTo}
              inProgress={inProgress}
            />
          </dd>
        </div>
        <div>
          <dt>{t("ops.mp.sales")}</dt>
          <dd>
            {moneyShort(m.sales)}
            <Delta
              metric={m.sales_metric}
              compareTo={compareTo}
              inProgress={inProgress}
            />
          </dd>
        </div>
        <div>
          <dt>{t("ops.mp.commission", { rate: m.commission_rate })}</dt>
          <dd>{money(m.commission_accrued + m.commission_pending)}</dd>
        </div>
        <div>
          <dt>{t("ops.mp.share")}</dt>
          <dd>
            <span>
              {percent(m.share_orders)} <small>{t("ops.mp.ofOrders")}</small>
            </span>
            <span>
              {percent(m.share_sales)} <small>{t("ops.mp.ofSales")}</small>
            </span>
          </dd>
        </div>
      </dl>
      {m.status !== "ACTIVE" && (
        <p className="muted small">{t(`mp.status.${m.status}`)}</p>
      )}
    </section>
  );
}

function CustomersCard({ data }: { data: Data }) {
  const { t } = useTranslation();
  const c = data.customers!;
  const p = data.performance?.period;
  return (
    <section className="panel">
      <SectionHead
        title={t("ops.dash.customers")}
        question={t("ops.dash.customersQ")}
        action={
          <Link className="textLink" to="/app/customers?segment=inactive">
            {t("ops.dash.notSeen")} <ArrowRight aria-hidden />
          </Link>
        }
      />
      <dl className="figures">
        <div>
          <dt>{t("ops.cust.unique")}</dt>
          <dd>{c.unique}</dd>
        </div>
        <div>
          <dt>{t("ops.cust.new")}</dt>
          <dd>
            {c.new}
            <Delta
              metric={c.new_metric}
              compareTo={p?.compare_to}
              inProgress={p?.in_progress}
            />
          </dd>
        </div>
        <div>
          <dt>{t("ops.cust.returning")}</dt>
          <dd>{c.returning}</dd>
        </div>
        <div>
          <dt>{t("ops.cust.repeatRate")}</dt>
          <dd>{percent(c.repeat_rate)}</dd>
        </div>
      </dl>
      {c.multi_order > 0 && (
        <p className="muted small">
          {t("ops.cust.multiOrder", { count: c.multi_order })}
        </p>
      )}
    </section>
  );
}
