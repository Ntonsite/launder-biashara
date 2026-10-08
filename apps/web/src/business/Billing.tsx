import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Check, Printer, Sparkles, Store, X } from "lucide-react";
import { api } from "../lib/api";
import type { TFunction } from "i18next";
import { date, dateTime, errorMessage, money } from "../lib/format";
import { Notice } from "../customer/ui";
import { AppFrame, useProfile } from "./shell";
import { SectionHead } from "./ui";

type Quote = {
  list_price: number;
  discount: number;
  price: number;
  terms: string[];
};
type PlanCard = {
  id: string;
  name: string;
  description: string;
  benefits: string[];
  features: string[];
  trial_days: number;
  max_staff: number | null;
  prices: Partial<Record<"MONTHLY" | "ANNUAL", Quote>>;
  rank: number;
};
type Invoice = {
  id: string;
  number: string;
  period_start: string;
  period_end: string;
  amount_due: number;
  amount_paid: number;
  balance: number;
  status: "OPEN" | "PAID" | "VOID";
  issued_at: string;
  due_at: string;
};
type Commission = {
  rate: number;
  minimum: number;
  includes_pickup_fee: boolean;
  discounts_reduce_basis: boolean;
  kind: string;
  until: string | null;
};
type BillingNoticeData = {
  kind: string;
  level: "info" | "warning" | "danger";
  days?: number;
  ends_at?: string;
  plan?: string;
  policy?: string | null;
  number?: string;
  amount?: number;
  due_at?: string;
  at?: string;
  invoice_id?: string;
};
export type BillingView = {
  current: {
    plan: PlanCard;
    source: "DEFAULT" | "TRIAL" | "SUBSCRIPTION" | "COMPLIMENTARY" | "PILOT";
    status: string;
    interval: "MONTHLY" | "ANNUAL" | null;
    price: number;
    renews_at: string | null;
    access_until: string | null;
    terms: string[];
    feature_names: string[];
  };
  subscription: null | {
    status: string;
    cancel_at_period_end: boolean;
    price: number;
  };
  plans: PlanCard[];
  invoices: Invoice[];
  payments: {
    amount: number;
    method: string;
    reference: string | null;
    received_at: string;
  }[];
  notices: BillingNoticeData[];
  payment_instructions: string;
  marketplace: {
    status: string;
    commission: Commission;
    listing_fee: number;
    eligible: boolean;
  };
};
type Preview = Quote & {
  credit: number;
  due_now: number;
  takes_effect: "NOW" | "PERIOD_END";
  effective_at: string;
  trial_days: number;
};

export function BillingNotice({ n }: { n: BillingNoticeData }) {
  const { t } = useTranslation();
  const text = t(`billing.notice.${n.kind}`, {
    days: n.days,
    count: n.days ?? 0,
    plan: n.plan,
    number: n.number,
    amount: n.amount != null ? money(n.amount) : "",
    date: date(n.ends_at ?? n.due_at ?? n.at),
  });
  const after =
    n.kind === "pilot_ending" && n.policy
      ? ` ${t(`billing.after.${n.policy}`)}`
      : "";
  return (
    <div
      className={`billingNotice ${n.level}`}
      role={n.level === "danger" ? "alert" : "status"}
    >
      <span>
        {text}
        {after}
      </span>
      {n.invoice_id && (
        <Link className="textLink" to={`/app/billing/invoices/${n.invoice_id}`}>
          {t("billing.viewInvoice")}
        </Link>
      )}
    </div>
  );
}

export function commissionText(t: TFunction, c: Commission) {
  const parts = [t("billing.commission.base", { rate: c.rate })];
  if (!c.discounts_reduce_basis)
    parts.push(t("billing.commission.beforeDiscounts"));
  if (c.includes_pickup_fee) parts.push(t("billing.commission.includesPickup"));
  if (c.minimum)
    parts.push(t("billing.commission.minimum", { amount: money(c.minimum) }));
  if (c.until)
    parts.push(t("billing.commission.until", { date: date(c.until) }));
  return parts.join(" ");
}

export default function Billing() {
  const { t } = useTranslation();
  const { reload: reloadProfile } = useProfile();
  const [view, setView] = useState<BillingView | null>(null);
  const [interval, setInterval] = useState<"MONTHLY" | "ANNUAL">("MONTHLY");
  const [choice, setChoice] = useState<{
    plan: PlanCard;
    preview: Preview;
  } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api<BillingView>("/api/v1/business/subscription", { auth: "business" })
      .then((v) => {
        setView(v);
        if (v.current.interval) setInterval(v.current.interval);
      })
      .catch((e) => setError(errorMessage(e)));
  }, []);
  useEffect(load, [load]);

  async function choose(plan: PlanCard) {
    setError("");
    try {
      const preview = await api<Preview>(
        `/api/v1/business/subscription/preview?plan_id=${plan.id}&interval=${interval}`,
        { auth: "business" },
      );
      setChoice({ plan, preview });
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function confirm() {
    if (!choice) return;
    setBusy(true);
    setError("");
    try {
      setView(
        await api<BillingView>("/api/v1/business/subscription", {
          auth: "business",
          body: { plan_id: choice.plan.id, interval },
        }),
      );
      setChoice(null);
      reloadProfile();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    if (!window.confirm(t("billing.cancelConfirm"))) return;
    try {
      setView(
        await api<BillingView>("/api/v1/business/subscription/cancel", {
          auth: "business",
          method: "POST",
        }),
      );
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  if (!view)
    return (
      <AppFrame title={t("billing.title")}>
        {error ? (
          <Notice>{error}</Notice>
        ) : (
          <div className="tableLoading">{t("common.loading")}</div>
        )}
      </AppFrame>
    );

  const cur = view.current;
  const currentRank = cur.plan.rank;
  return (
    <AppFrame title={t("billing.title")}>
      {error && <Notice>{error}</Notice>}
      {view.notices.map((n, i) => (
        <BillingNotice key={i} n={n} />
      ))}

      <section className="planHero">
        <div>
          <p className="kicker">{t("billing.yourPlan")}</p>
          <h2>{cur.plan.name}</h2>
          <p className="muted">{cur.plan.description}</p>
          <p className="planState">
            <span className={`pill src-${cur.source.toLowerCase()}`}>
              {t(`billing.source.${cur.source}`)}
            </span>
            {cur.source === "SUBSCRIPTION" && cur.interval && (
              <span>
                {money(cur.price)} {t(`billing.per.${cur.interval}`)}
                {cur.renews_at &&
                  ` · ${t("billing.renews", { date: date(cur.renews_at) })}`}
              </span>
            )}
            {cur.source !== "SUBSCRIPTION" &&
              cur.source !== "DEFAULT" &&
              cur.access_until && (
                <span>
                  {t("billing.until", { date: date(cur.access_until) })}
                </span>
              )}
            {cur.terms.map((x) => (
              <span key={x} className="muted">
                {x}
              </span>
            ))}
          </p>
        </div>
        <ul className="included">
          {cur.feature_names.map((f) => (
            <li key={f}>
              <Check aria-hidden /> {f}
            </li>
          ))}
        </ul>
      </section>

      <section className="panel">
        <SectionHead
          title={t("billing.plans")}
          question={t("billing.plansQ")}
          action={
            <div
              className="segmented small"
              role="group"
              aria-label={t("billing.interval")}
            >
              {(["MONTHLY", "ANNUAL"] as const).map((i) => (
                <button
                  key={i}
                  className={interval === i ? "on" : ""}
                  aria-pressed={interval === i}
                  onClick={() => setInterval(i)}
                >
                  {t(`billing.intervals.${i}`)}
                </button>
              ))}
            </div>
          }
        />
        <div className="planGrid">
          {view.plans.map((p) => {
            const q = p.prices[interval];
            // The plan you are on (for a paid subscription, also in the interval you pay).
            const isCurrent =
              p.id === cur.plan.id &&
              (cur.source !== "SUBSCRIPTION" || cur.interval === interval);
            return (
              <article
                key={p.id}
                className={`planCard ${isCurrent ? "current" : ""} ${p.rank > currentRank ? "up" : ""}`}
              >
                <h3>{p.name}</h3>
                <p className="muted small">{p.description}</p>
                {q && (
                  <p className="planPrice">
                    {q.discount > 0 && <s>{money(q.list_price)}</s>}
                    <strong>
                      {q.price === 0 ? t("billing.free") : money(q.price)}
                    </strong>
                    {q.price > 0 && (
                      <small>{t(`billing.per.${interval}`)}</small>
                    )}
                  </p>
                )}
                {q?.terms.map((x) => (
                  <p key={x} className="specialTerm">
                    <Sparkles aria-hidden /> {x}
                  </p>
                ))}
                {p.trial_days > 0 && q && q.price > 0 && (
                  <p className="muted small">
                    {t("billing.trial", { count: p.trial_days })}
                  </p>
                )}
                <ul>
                  {p.benefits.map((b) => (
                    <li key={b}>
                      <Check aria-hidden /> {b}
                    </li>
                  ))}
                </ul>
                {isCurrent ? (
                  <span className="pill">{t("billing.current")}</span>
                ) : (
                  <button
                    className={p.rank > currentRank ? "primary" : "outlineBtn"}
                    onClick={() => choose(p)}
                  >
                    {t(
                      p.rank > currentRank
                        ? "billing.upgrade"
                        : p.rank < currentRank
                          ? "billing.downgrade"
                          : "billing.switch",
                    )}
                  </button>
                )}
              </article>
            );
          })}
        </div>
        {view.subscription &&
          view.subscription.price > 0 &&
          !view.subscription.cancel_at_period_end && (
            <button className="textBtn danger" onClick={cancel}>
              {t("billing.cancel")}
            </button>
          )}
      </section>

      {choice && (
        <div
          className="modalBackdrop"
          role="dialog"
          aria-modal="true"
          aria-labelledby="planConfirm"
        >
          <div className="modal">
            <button
              className="iconBtn close"
              onClick={() => setChoice(null)}
              aria-label={t("common.close")}
            >
              <X />
            </button>
            <h2 id="planConfirm">
              {t("billing.confirmTitle", { plan: choice.plan.name })}
            </h2>
            <dl className="ledger">
              <div>
                <dt>
                  {t("billing.priceLabel", {
                    interval: t(`billing.intervals.${interval}`),
                  })}
                </dt>
                <dd>{money(choice.preview.price)}</dd>
              </div>
              {choice.preview.credit > 0 &&
                choice.preview.takes_effect === "NOW" &&
                !choice.preview.trial_days && (
                  <div>
                    <dt>{t("billing.credit")}</dt>
                    <dd>−{money(choice.preview.credit)}</dd>
                  </div>
                )}
              <div className="strong">
                <dt>{t("billing.dueNow")}</dt>
                <dd>{money(choice.preview.due_now)}</dd>
              </div>
            </dl>
            <p className="muted">
              {choice.preview.takes_effect === "PERIOD_END"
                ? t("billing.effectiveLater", {
                    date: date(choice.preview.effective_at),
                  })
                : choice.preview.trial_days
                  ? t("billing.trialStarts", {
                      count: choice.preview.trial_days,
                    })
                  : choice.preview.due_now > 0
                    ? t("billing.invoiceNote")
                    : t("billing.effectiveNow")}
            </p>
            <div className="actions">
              <button className="primary" disabled={busy} onClick={confirm}>
                {t("billing.confirm")}
              </button>
              <button className="textBtn" onClick={() => setChoice(null)}>
                {t("common.cancel")}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="opsCols even">
        <section className="panel">
          <h2>
            <Store aria-hidden className="inlineIcon" />{" "}
            {t("billing.marketplace")}
          </h2>
          <p>
            <span className="pill">
              {t(`mp.status.${view.marketplace.status}`)}
            </span>
          </p>
          <p>{commissionText(t, view.marketplace.commission)}</p>
          <p className="muted small">{t("billing.commissionWhen")}</p>
          {view.marketplace.listing_fee > 0 && (
            <p className="muted small">
              {t("billing.listingFee", {
                amount: money(view.marketplace.listing_fee),
              })}
            </p>
          )}
          {!view.marketplace.eligible && (
            <p className="muted small">{t("billing.notEligible")}</p>
          )}
          <Link className="textLink" to="/app/marketplace">
            {t("biz.marketplaceStatus")}
          </Link>
        </section>
        <section className="panel">
          <h2>{t("billing.howToPay")}</h2>
          <p>{view.payment_instructions}</p>
          <p className="muted small">{t("billing.neverCharged")}</p>
        </section>
      </div>

      <section className="panel">
        <h2>{t("billing.invoices")}</h2>
        {view.invoices.length === 0 ? (
          <p className="muted">{t("billing.noInvoices")}</p>
        ) : (
          <table className="reportTable">
            <thead>
              <tr>
                <th>{t("billing.invoice")}</th>
                <th>{t("billing.period")}</th>
                <th>{t("billing.amount")}</th>
                <th>{t("billing.status")}</th>
              </tr>
            </thead>
            <tbody>
              {view.invoices.map((i) => (
                <tr key={i.id}>
                  <td>
                    <Link to={`/app/billing/invoices/${i.id}`}>{i.number}</Link>
                  </td>
                  <td>
                    {date(i.period_start)} – {date(i.period_end)}
                  </td>
                  <td>{money(i.amount_due)}</td>
                  <td>
                    <span className={`pill inv-${i.status.toLowerCase()}`}>
                      {t(`billing.invoiceStatus.${i.status}`)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {view.payments.length > 0 && (
          <>
            <h3>{t("billing.payments")}</h3>
            <ul className="plainList">
              {view.payments.map((p, n) => (
                <li key={n}>
                  {dateTime(p.received_at)} · {money(p.amount)} ·{" "}
                  {t(`billing.method.${p.method}`)}
                  {p.reference && ` · ${p.reference}`}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </AppFrame>
  );
}

type InvoiceDetail = Invoice & {
  subtotal: number;
  discount: number;
  paid_at: string | null;
  void_reason: string | null;
  lines: { kind: string; description: string; amount: number }[];
  payments: {
    amount: number;
    method: string;
    reference: string | null;
    received_at: string;
  }[];
  business: { name: string; address: string; area: string; phone: string };
};

export function InvoicePage() {
  const { id = "" } = useParams();
  const { t } = useTranslation();
  const [inv, setInv] = useState<InvoiceDetail | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api<InvoiceDetail>(`/api/v1/business/invoices/${id}`, { auth: "business" })
      .then(setInv)
      .catch((e) => setError(errorMessage(e)));
  }, [id]);
  return (
    <AppFrame
      title={inv ? inv.number : t("billing.invoice")}
      action={
        <div className="reportActions">
          <Link className="outlineBtn" to="/app/billing">
            <ArrowLeft aria-hidden /> {t("billing.title")}
          </Link>
          <button
            className="primary"
            onClick={() => window.print()}
            disabled={!inv}
          >
            <Printer aria-hidden /> {t("ops.reports.print")}
          </button>
        </div>
      }
    >
      {error && <Notice>{error}</Notice>}
      {inv && (
        <article className="invoiceDoc">
          <div className="spread">
            <div>
              <b>Launder</b>
              <p className="muted small">launder.co.tz</p>
            </div>
            <div className="right">
              <span className={`pill inv-${inv.status.toLowerCase()}`}>
                {t(`billing.invoiceStatus.${inv.status}`)}
              </span>
              <h2>{inv.number}</h2>
            </div>
          </div>
          <dl className="ledger">
            <div>
              <dt>{t("billing.billedTo")}</dt>
              <dd>
                {inv.business.name}
                <small>
                  {[inv.business.address, inv.business.area]
                    .filter(Boolean)
                    .join(", ")}
                </small>
              </dd>
            </div>
            <div>
              <dt>{t("billing.period")}</dt>
              <dd>
                {date(inv.period_start)} – {date(inv.period_end)}
              </dd>
            </div>
            <div>
              <dt>{t("billing.issued")}</dt>
              <dd>{date(inv.issued_at)}</dd>
            </div>
            <div>
              <dt>{t("billing.due")}</dt>
              <dd>{date(inv.due_at)}</dd>
            </div>
          </dl>
          <table className="reportTable">
            <tbody>
              {inv.lines.map((l, n) => (
                <tr key={n}>
                  <td>{l.description}</td>
                  <td>{money(l.amount)}</td>
                </tr>
              ))}
              <tr className="strong">
                <td>{t("billing.total")}</td>
                <td>{money(inv.amount_due)}</td>
              </tr>
              {inv.payments.map((p, n) => (
                <tr key={`p${n}`}>
                  <td>
                    {t("billing.paidOn", { date: date(p.received_at) })} ·{" "}
                    {t(`billing.method.${p.method}`)}
                    {p.reference && ` · ${p.reference}`}
                  </td>
                  <td>−{money(p.amount)}</td>
                </tr>
              ))}
              <tr className="strong">
                <td>{t("billing.balance")}</td>
                <td>{money(inv.balance)}</td>
              </tr>
            </tbody>
          </table>
          {inv.void_reason && (
            <p className="muted">
              {t("billing.voided", { reason: inv.void_reason })}
            </p>
          )}
          {inv.discount > 0 && (
            <p className="muted small">
              {t("billing.discountNote", { amount: money(inv.discount) })}
            </p>
          )}
        </article>
      )}
    </AppFrame>
  );
}
