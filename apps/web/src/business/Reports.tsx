import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowRight,
  CalendarDays,
  CalendarRange,
  ClipboardCheck,
  Download,
  LineChart,
  Lock,
  Printer,
  ShoppingBag,
  Store,
  Users,
  Wallet,
} from "lucide-react";
import { api, download } from "../lib/api";
import {
  dateTime,
  dayMonth,
  errorMessage,
  longDate,
  money,
  percent,
  weekdayName,
} from "../lib/format";
import i18n from "../i18n";
import { Notice } from "../customer/ui";
import { AppFrame } from "./shell";
import { insightText } from "./Dashboard";
import {
  Bars,
  Delta,
  PeriodPicker,
  SectionHead,
  ShareBar,
  StatCard,
  periodQuery,
  type PeriodValue,
} from "./ui";
import type { DayCloseView, Report } from "./types";

const ICONS: Record<string, typeof Wallet> = {
  daily: ClipboardCheck,
  weekly: CalendarRange,
  monthly: CalendarDays,
  sales: LineChart,
  orders: ShoppingBag,
  customers: Users,
  marketplace: Store,
  payments: Wallet,
};

export function ReportsIndex() {
  const { t } = useTranslation();
  const [kinds, setKinds] = useState<
    { kind: string; locked: boolean }[] | null
  >(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api<{ reports: { kind: string; locked: boolean }[] }>(
      "/api/v1/business/reports",
      {
        auth: "business",
      },
    )
      .then((r) => setKinds(r.reports))
      .catch((e) => setError(errorMessage(e)));
  }, []);
  return (
    <AppFrame title={t("biz.nav.reports")}>
      <p className="dashSub">{t("ops.reports.intro")}</p>
      {error && <Notice>{error}</Notice>}
      <div className="reportCards">
        {kinds?.map(({ kind: k, locked }) => {
          const Icon = ICONS[k];
          return (
            <Link
              key={k}
              to={locked ? "/app/billing" : `/app/reports/${k}`}
              className={`reportCard ${locked ? "locked" : ""}`}
            >
              <Icon aria-hidden />
              <b>{t(`ops.reports.kind.${k}`)}</b>
              <p>{t(`ops.reports.about.${k}`)}</p>
              {locked ? (
                <span className="lockTag">
                  <Lock aria-hidden /> {t("billing.upgradeToUnlock")}
                </span>
              ) : (
                <ArrowRight aria-hidden />
              )}
            </Link>
          );
        })}
      </div>
    </AppFrame>
  );
}

const DEFAULT: Record<string, string> = {
  daily: "today",
  weekly: "this_week",
  monthly: "this_month",
};

export function ReportPage() {
  const { kind = "daily" } = useParams();
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const period: PeriodValue = {
    period: params.get("period") ?? DEFAULT[kind] ?? "this_month",
    start: params.get("start") ?? undefined,
    end: params.get("end") ?? undefined,
  };
  const [data, setData] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const query = periodQuery(period).toString();

  const load = useCallback(() => {
    setData(null);
    setError("");
    api<Report>(`/api/v1/business/reports/${kind}?${query}`, {
      auth: "business",
    })
      .then(setData)
      .catch((e) => setError(errorMessage(e)));
  }, [kind, query]);
  useEffect(load, [load]);

  const options =
    kind === "daily"
      ? ["today", "yesterday", "custom"]
      : kind === "weekly"
        ? ["this_week", "last_week", "last_7_days", "custom"]
        : kind === "monthly"
          ? ["this_month", "last_month", "custom"]
          : undefined;

  async function csv() {
    try {
      await download(
        `/api/v1/business/reports/${kind}/export.csv?${query}&lang=${i18n.language}`,
        "business",
        `launder-${kind}.csv`,
      );
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <AppFrame
      title={t(`ops.reports.kind.${kind}`)}
      action={
        <div className="reportActions">
          <PeriodPicker
            value={period}
            options={options}
            onChange={(p) =>
              setParams(Object.fromEntries(periodQuery(p)), { replace: true })
            }
          />
          <button
            className="outlineBtn"
            onClick={() => window.print()}
            disabled={!data}
          >
            <Printer aria-hidden /> {t("ops.reports.print")}
          </button>
          <button className="outlineBtn" onClick={csv} disabled={!data}>
            <Download aria-hidden /> CSV
          </button>
        </div>
      }
    >
      {error && <Notice>{error}</Notice>}
      {!data && !error && (
        <div className="tableLoading">{t("common.loading")}</div>
      )}
      {data && <ReportBody data={data} onClosed={load} />}
    </AppFrame>
  );
}

function periodTitle(d: Report) {
  const { start_date, end_date } = d.period;
  return start_date === end_date
    ? longDate(start_date)
    : `${dayMonth(start_date)} – ${dayMonth(end_date)} ${end_date.slice(0, 4)}`;
}

function ReportBody({
  data,
  onClosed,
}: {
  data: Report;
  onClosed: () => void;
}) {
  const { t } = useTranslation();
  const has = (s: string) => data.sections.includes(s);
  const sum = data.summary;
  const cmp = {
    compareTo: data.period.compare_to,
    inProgress: data.period.in_progress,
  };
  return (
    <article className="report">
      <div className="reportHeader">
        <div>
          <p className="kicker">{t(`ops.reports.kind.${data.kind}`)}</p>
          <h2>{periodTitle(data)}</h2>
          {data.period.in_progress && (
            <p className="muted small">{t("ops.reports.inProgress")}</p>
          )}
        </div>
        <dl>
          <div>
            <dt>{t("ops.reports.laundry")}</dt>
            <dd>{data.business.name}</dd>
          </div>
          <div>
            <dt>{t("ops.reports.branch")}</dt>
            <dd>{data.business.branch || "—"}</dd>
          </div>
          <div>
            <dt>{t("ops.reports.generated")}</dt>
            <dd>{dateTime(data.generated_at)}</dd>
          </div>
        </dl>
      </div>

      <section className="reportSection">
        <div className="todayGrid">
          <StatCard
            label={t("ops.money.sales")}
            value={money(sum.sales.value)}
            metric={sum.sales}
            {...cmp}
          />
          <StatCard
            label={t("ops.metric.orders")}
            value={sum.orders.value}
            metric={sum.orders}
            {...cmp}
          />
          <StatCard
            label={t("ops.metric.averageOrder")}
            value={money(sum.average_order.value)}
            metric={sum.average_order}
            {...cmp}
          />
          <StatCard
            label={t("ops.money.collected")}
            value={money(sum.collected.value)}
            metric={sum.collected}
            {...cmp}
          />
          {(has("customers") || data.kind === "weekly") && (
            <>
              <StatCard
                label={t("ops.cust.new")}
                value={sum.new_customers.value}
                metric={sum.new_customers}
                {...cmp}
              />
              <StatCard
                label={t("ops.cust.repeatRate")}
                value={percent(sum.repeat_rate.value)}
                metric={sum.repeat_rate}
                goodWhen="neutral"
                {...cmp}
              />
            </>
          )}
          {(data.kind === "weekly" || data.kind === "monthly") && (
            <>
              <StatCard
                label={t("ops.mp.sales")}
                value={money(sum.marketplace_sales.value)}
                metric={sum.marketplace_sales}
                {...cmp}
              />
              <StatCard
                label={t("ops.ops.onTime")}
                value={percent(sum.on_time_rate)}
              />
            </>
          )}
        </div>
        {!sum.comparable && (
          <p className="muted small">{t("ops.compare.notEnoughLong")}</p>
        )}
      </section>

      {has("day_book") && data.day_book && (
        <section className="reportSection">
          <SectionHead title={t("ops.book.title")} question={t("ops.book.q")} />
          <dl className="ledger">
            {(
              [
                "opening",
                "new",
                "completed",
                "cancelled",
                "carried_forward",
              ] as const
            ).map((k) => (
              <div key={k}>
                <dt>{t(`ops.book.${k}`)}</dt>
                <dd>{data.day_book![k]}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {has("money") && (
        <section className="reportSection">
          <SectionHead
            title={t("ops.money.title")}
            question={t("ops.money.q")}
          />
          <dl className="ledger">
            <div>
              <dt>
                {t("ops.money.sales")}
                <small>{t("ops.money.salesHint")}</small>
              </dt>
              <dd>{money(data.money.sales)}</dd>
            </div>
            <div>
              <dt>{t("ops.money.discounts")}</dt>
              <dd>{money(data.money.discounts)}</dd>
            </div>
            <div>
              <dt>
                {t("ops.money.collected")}
                <small>{t("ops.money.collectedHint")}</small>
              </dt>
              <dd>{money(data.money.collected)}</dd>
            </div>
            <div>
              <dt>{t("ops.money.refunded")}</dt>
              <dd>{money(data.money.refunded)}</dd>
            </div>
            <div>
              <dt>
                {t("ops.money.unpaidFromPeriod")}
                <small>
                  {t("ops.dash.ordersCount", {
                    count: data.money.unpaid_from_period.count,
                  })}
                </small>
              </dt>
              <dd>{money(data.money.unpaid_from_period.amount)}</dd>
            </div>
            <div className="strong">
              <dt>
                {t("ops.money.outstanding")}
                <small>{t("ops.money.outstandingHint")}</small>
              </dt>
              <dd>{money(data.money.outstanding_now.amount)}</dd>
            </div>
          </dl>
        </section>
      )}

      {has("payments") && (
        <section className="reportSection">
          <SectionHead title={t("ops.pay.mix")} question={t("ops.pay.mixQ")} />
          <ul className="shares">
            {Object.entries(data.payments).map(([method, v]) => (
              <li key={method}>
                <span>
                  {method === "CASH"
                    ? t("checkout.cash")
                    : t("checkout.mobile")}
                </span>
                <ShareBar
                  share={
                    data.money.collected
                      ? (v.amount * 100) / data.money.collected
                      : 0
                  }
                />
                <b>{money(v.amount)}</b>
                <small>{t("ops.pay.payments", { count: v.count })}</small>
              </li>
            ))}
          </ul>
        </section>
      )}

      {has("sources") && (
        <section className="reportSection">
          <SectionHead title={t("ops.src.title")} question={t("ops.src.q")} />
          <ul className="shares">
            {data.sources.map((s) => (
              <li key={s.source}>
                <span>{t(`biz.source.${s.source}`)}</span>
                <ShareBar share={s.share_orders} />
                <b>{s.orders}</b>
                <small>
                  {percent(s.share_orders)} · {money(s.sales)}
                </small>
              </li>
            ))}
          </ul>
        </section>
      )}

      {has("operations") && (
        <section className="reportSection">
          <SectionHead title={t("ops.ops.title")} question={t("ops.ops.q")} />
          <dl className="ledger cols">
            {(
              [
                "received",
                "washing",
                "ironing",
                "ready",
                "delivered",
                "completed",
              ] as const
            ).map((k) => (
              <div key={k}>
                <dt>{t(`ops.ops.${k}`)}</dt>
                <dd>{data.operations[k]}</dd>
              </div>
            ))}
            <div>
              <dt>{t("ops.ops.onTime")}</dt>
              <dd>
                {percent(data.operations.on_time_rate)}
                <small>
                  {t("ops.ops.onTimeOf", {
                    late: data.operations.ready_late,
                    total:
                      data.operations.ready_on_time +
                      data.operations.ready_late,
                  })}
                </small>
              </dd>
            </div>
            <div>
              <dt>{t("ops.ops.turnaround")}</dt>
              <dd>
                {data.operations.average_turnaround_hours == null
                  ? "—"
                  : t("ops.ops.hours", {
                      count: data.operations.average_turnaround_hours,
                    })}
              </dd>
            </div>
            <div className={data.operations.overdue_now ? "alert" : ""}>
              <dt>{t("ops.ops.overdueNow")}</dt>
              <dd>
                {data.operations.overdue_now > 0 ? (
                  <Link to="/app/orders?due=overdue">
                    {data.operations.overdue_now}
                  </Link>
                ) : (
                  0
                )}
              </dd>
            </div>
            <div>
              <dt>{t("ops.ops.cancellation")}</dt>
              <dd>{percent(data.operations.cancellation_rate)}</dd>
            </div>
          </dl>
        </section>
      )}

      {has("customers") && (
        <section className="reportSection">
          <SectionHead
            title={t("ops.dash.customers")}
            question={t("ops.dash.customersQ")}
          />
          <dl className="ledger cols">
            <div>
              <dt>{t("ops.cust.unique")}</dt>
              <dd>{data.customers.unique}</dd>
            </div>
            <div>
              <dt>{t("ops.cust.new")}</dt>
              <dd>{data.customers.new}</dd>
            </div>
            <div>
              <dt>{t("ops.cust.returning")}</dt>
              <dd>{data.customers.returning}</dd>
            </div>
            <div>
              <dt>{t("ops.cust.repeatRate")}</dt>
              <dd>{percent(data.customers.repeat_rate)}</dd>
            </div>
            <div>
              <dt>{t("ops.cust.multi")}</dt>
              <dd>{data.customers.multi_order}</dd>
            </div>
            <div>
              <dt>{t("ops.cust.fromMarketplace")}</dt>
              <dd>{data.customers.new_from_marketplace}</dd>
            </div>
          </dl>
          <p className="muted small">{t("ops.cust.definitions")}</p>
        </section>
      )}

      {has("marketplace") && <MarketplaceSection data={data} />}

      {has("services") && (
        <section className="reportSection">
          <SectionHead title={t("ops.svc.title")} question={t("ops.svc.q")} />
          <div className="opsCols even">
            <div>
              <h3>{t("ops.svc.byRevenue")}</h3>
              <ul className="shares">
                {data.services.by_revenue.map((s) => (
                  <li key={s.name}>
                    <span>{s.name}</span>
                    <ShareBar share={s.share_revenue} />
                    <b>{money(s.revenue)}</b>
                    <small>{percent(s.share_revenue)}</small>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3>{t("ops.svc.byOrders")}</h3>
              <ul className="shares">
                {data.services.by_orders.map((s) => (
                  <li key={s.name}>
                    <span>{s.name}</span>
                    <ShareBar
                      share={
                        data.summary.orders.value
                          ? (s.orders * 100) / data.summary.orders.value
                          : 0
                      }
                    />
                    <b>{t("ops.svc.orders", { count: s.orders })}</b>
                    <small>
                      {s.pricing_model === "PER_KG"
                        ? `${s.quantity} kg`
                        : `${s.quantity}×`}
                    </small>
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <p className="muted small">{t("ops.svc.note")}</p>
        </section>
      )}

      {has("top_customers") && !!data.top_customers?.length && (
        <section className="reportSection">
          <SectionHead
            title={t("ops.cust.top")}
            question={t("ops.cust.topQ")}
          />
          <table className="reportTable">
            <thead>
              <tr>
                <th>{t("biz.col.customer")}</th>
                <th>{t("ops.cust.orders")}</th>
                <th>{t("ops.cust.spend")}</th>
              </tr>
            </thead>
            <tbody>
              {data.top_customers.map((c) => (
                <tr key={c.id}>
                  <td>
                    <Link to={`/app/customers/${c.id}`}>{c.name}</Link>{" "}
                    <small>{c.phone}</small>
                  </td>
                  <td>{c.orders}</td>
                  <td>{money(c.spend)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {has("daily") && data.daily && data.daily.length > 1 && (
        <section className="reportSection">
          <SectionHead
            title={t("ops.daily.title")}
            question={t("ops.daily.q")}
          />
          <div className="opsCols even">
            <Bars
              label={t("ops.dash.trend_sales")}
              valueLabel={money}
              points={data.daily.map((d) => ({
                key: d.date,
                label: dayMonth(d.date),
                value: d.sales,
              }))}
            />
            <Bars
              label={t("ops.dash.trend_orders")}
              valueLabel={String}
              points={data.daily.map((d) => ({
                key: d.date,
                label: dayMonth(d.date),
                value: d.orders,
              }))}
            />
          </div>
          <details className="dailyTable" open={data.daily.length <= 7}>
            <summary>{t("ops.daily.table")}</summary>
            <table className="reportTable">
              <thead>
                <tr>
                  <th>{t("ops.daily.date")}</th>
                  <th>{t("ops.metric.orders")}</th>
                  <th>{t("ops.money.sales")}</th>
                  <th>{t("ops.money.collected")}</th>
                </tr>
              </thead>
              <tbody>
                {data.daily.map((d) => (
                  <tr key={d.date}>
                    <td>
                      {weekdayName(d.weekday, "short")} {dayMonth(d.date)}
                    </td>
                    <td>{d.orders}</td>
                    <td>{money(d.sales)}</td>
                    <td>{money(d.collected)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </section>
      )}

      {has("weekdays") && data.weekdays && (
        <section className="reportSection">
          <SectionHead
            title={t("ops.week.title")}
            question={t("ops.week.q", { weeks: data.weekdays.weeks })}
          />
          <Bars
            label={t("ops.week.title")}
            valueLabel={(v) => t("ops.week.avg", { count: v })}
            points={data.weekdays.average.map((v, i) => ({
              key: String(i),
              label: weekdayName(i, "short"),
              value: v,
            }))}
          />
        </section>
      )}

      {has("insights") && !!data.insights?.length && (
        <section className="reportSection">
          <SectionHead
            title={t("ops.dash.insights")}
            question={t("ops.dash.insightsNote")}
          />
          <ul className="insightList">
            {data.insights.map((i) => (
              <li key={i.key}>{insightText(t, i)}</li>
            ))}
          </ul>
        </section>
      )}

      {has("day_close") && data.day_close && (
        <CloseDay view={data.day_close} onClosed={onClosed} />
      )}
    </article>
  );
}

function MarketplaceSection({ data }: { data: Report }) {
  const { t } = useTranslation();
  const m = data.marketplace;
  const cmp = {
    compareTo: data.period.compare_to,
    inProgress: data.period.in_progress,
  };
  return (
    <section className="reportSection">
      <SectionHead
        title={t("ops.dash.marketplace")}
        question={t("ops.dash.marketplaceQ")}
      />
      {m.status === "NOT_ENROLLED" && !m.orders ? (
        <p className="muted">
          {t("ops.mp.notEnrolled")}{" "}
          <Link to="/app/marketplace">{t("biz.marketplaceStatus")}</Link>
        </p>
      ) : (
        <>
          <dl className="ledger cols">
            <div>
              <dt>{t("ops.mp.orders")}</dt>
              <dd>
                {m.orders}
                <Delta metric={data.summary.marketplace_orders} {...cmp} />
              </dd>
            </div>
            <div>
              <dt>{t("ops.mp.sales")}</dt>
              <dd>
                {money(m.sales)}
                <Delta metric={data.summary.marketplace_sales} {...cmp} />
              </dd>
            </div>
            <div>
              <dt>{t("ops.mp.average")}</dt>
              <dd>{money(m.average_order)}</dd>
            </div>
            <div>
              <dt>{t("ops.mp.customers")}</dt>
              <dd>
                {m.customers}
                <small>
                  {t("ops.mp.newCustomers", {
                    count: data.customers.new_from_marketplace,
                  })}
                </small>
              </dd>
            </div>
            <div>
              <dt>{t("ops.mp.share")}</dt>
              <dd>
                <span>
                  {percent(m.share_orders)}{" "}
                  <small>{t("ops.mp.ofOrders")}</small>
                </span>
                <span>
                  {percent(m.share_sales)} <small>{t("ops.mp.ofSales")}</small>
                </span>
              </dd>
            </div>
            <div>
              <dt>{t("ops.mp.rating")}</dt>
              <dd>
                {m.review_count
                  ? `${m.rating.toFixed(1)} ★ (${m.review_count})`
                  : "—"}
              </dd>
            </div>
          </dl>
          <dl className="ledger statement">
            <div>
              <dt>{t("ops.mp.gmv")}</dt>
              <dd>{money(m.sales)}</dd>
            </div>
            <div>
              <dt>
                {t("ops.mp.commissionAccrued", { rate: m.commission_rate })}
                <small>{t("ops.mp.accruedHint")}</small>
              </dt>
              <dd>−{money(m.commission_accrued)}</dd>
            </div>
            <div>
              <dt>
                {t("ops.mp.commissionPending")}
                <small>{t("ops.mp.pendingHint")}</small>
              </dt>
              <dd>−{money(m.commission_pending)}</dd>
            </div>
            <div className="strong">
              <dt>{t("ops.mp.net")}</dt>
              <dd>{money(m.net)}</dd>
            </div>
          </dl>
          <p className="muted small">
            {t("ops.mp.how", { rate: m.commission_rate })}
          </p>
        </>
      )}
    </section>
  );
}

function CloseDay({
  view,
  onClosed,
}: {
  view: DayCloseView;
  onClosed: () => void;
}) {
  const { t } = useTranslation();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const counted = String(fd.get("counted") ?? "").trim();
    setBusy(true);
    setError("");
    try {
      await api("/api/v1/business/day-close", {
        auth: "business",
        body: {
          date: view.date,
          counted_cash: counted === "" ? null : Number(counted),
          note: fd.get("note"),
        },
      });
      onClosed();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  const c = view.closed;
  return (
    <section className="reportSection closeDay">
      <SectionHead title={t("ops.close.title")} question={t("ops.close.q")} />
      <dl className="ledger">
        <div>
          <dt>{t("ops.close.expectedCash")}</dt>
          <dd>{money(view.expected_cash)}</dd>
        </div>
        <div>
          <dt>{t("ops.close.expectedMobile")}</dt>
          <dd>{money(view.expected_mobile_money)}</dd>
        </div>
        <div className="strong">
          <dt>{t("ops.close.expectedTotal")}</dt>
          <dd>{money(view.expected_total)}</dd>
        </div>
        <div>
          <dt>{t("ops.money.outstanding")}</dt>
          <dd>{money(view.outstanding_now.amount)}</dd>
        </div>
        <div>
          <dt>{t("ops.book.carried_forward")}</dt>
          <dd>{view.carried_forward}</dd>
        </div>
      </dl>
      {c ? (
        <div className="closedNote" role="status">
          <b>
            {t("ops.close.closedBy", {
              name: c.closed_by ?? "—",
              time: dateTime(c.closed_at),
            })}
          </b>
          {c.counted_cash != null && (
            <p>
              {t("ops.close.counted", { amount: money(c.counted_cash) })} ·{" "}
              <span className={c.variance === 0 ? "" : "variance"}>
                {c.variance === 0
                  ? t("ops.close.balanced")
                  : t("ops.close.variance", { amount: money(c.variance ?? 0) })}
              </span>
            </p>
          )}
          {c.note && <p>“{c.note}”</p>}
        </div>
      ) : view.can_close ? (
        <form className="closeForm noPrint" onSubmit={submit}>
          <label>
            {t("ops.close.countedLabel")}
            <input
              name="counted"
              type="number"
              min={0}
              step={100}
              inputMode="numeric"
              placeholder={String(view.expected_cash)}
            />
          </label>
          <label>
            {t("ops.close.note")}
            <input name="note" maxLength={500} />
          </label>
          {error && <Notice>{error}</Notice>}
          <button className="primary" disabled={busy}>
            <ClipboardCheck aria-hidden /> {t("ops.close.submit")}
          </button>
          <small className="muted">{t("ops.close.noLock")}</small>
        </form>
      ) : null}
    </section>
  );
}
