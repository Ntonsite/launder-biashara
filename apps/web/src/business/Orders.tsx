import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import type { TFunction } from "i18next";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowRight,
  Banknote,
  Check,
  Download,
  PackageCheck,
  Plus,
  Printer,
  Smartphone,
  X,
} from "lucide-react";
import { api, download } from "../lib/api";
import {
  dateTime,
  errorMessage,
  itemsSummary,
  money,
  statusLabel,
  time,
} from "../lib/format";
import { Notice, StatusPill } from "../customer/ui";
import type { OrderDetail, ServiceData } from "../customer/types";
import { AppFrame, Pagination } from "./shell";
import { useCan } from "./ui";

export type OrderRow = {
  id: string;
  order_number: string;
  customer_id: string;
  customer_name: string;
  phone: string;
  source: string;
  status: string;
  fulfillment: string;
  payment_status: string;
  payment_method: string;
  total: number;
  amount_paid: number;
  created_at: string;
  pickup_window_start: string | null;
  pickup_address: string | null;
  due_at: string | null;
  ready_at: string | null;
  due_state: "OVERDUE" | "DUE_SOON" | "DUE_TODAY" | null;
  items: { name: string; quantity: number; pricing_model: string }[];
};

const VIEWS = [
  "all",
  "new",
  "in_progress",
  "ready",
  "delivery",
  "completed",
  "cancelled",
] as const;
const DUE = ["overdue", "today", "uncollected"] as const;
const TERMINAL = ["DELIVERED", "COMPLETED", "CANCELLED", "REJECTED"];

/** How urgent an order is, in words staff use: "3 h late", "Due 4:00 PM", "Ready 3 days". */
export function DueBadge({
  o,
}: {
  o: Pick<OrderRow, "due_at" | "due_state" | "status" | "ready_at">;
}) {
  const { t } = useTranslation();
  if (o.status === "READY" && o.ready_at) {
    const days = Math.floor(
      (Date.now() - new Date(o.ready_at).getTime()) / 86_400_000,
    );
    return days >= 2 ? (
      <span className="due waiting">
        {t("ops.due.readyDays", { count: days })}
      </span>
    ) : null;
  }
  if (!o.due_at || TERMINAL.includes(o.status) || o.status === "READY")
    return null;
  if (o.due_state === "OVERDUE") {
    const hours = Math.max(
      1,
      Math.round((Date.now() - new Date(o.due_at).getTime()) / 3_600_000),
    );
    return (
      <span className="due overdue">
        {hours < 24
          ? t("ops.due.lateHours", { count: hours })
          : t("ops.due.lateDays", { count: Math.round(hours / 24) })}
      </span>
    );
  }
  if (o.due_state === "DUE_SOON" || o.due_state === "DUE_TODAY")
    return (
      <span className={`due ${o.due_state === "DUE_SOON" ? "soon" : "today"}`}>
        {t("ops.due.at", { time: time(o.due_at) })}
      </span>
    );
  return (
    <span className="due later">
      {t("ops.due.on", { date: dateTime(o.due_at) })}
    </span>
  );
}

export function OrderRows({
  rows,
  empty,
}: {
  rows: OrderRow[] | null;
  empty?: string;
}) {
  const { t } = useTranslation();
  if (!rows) return <div className="tableLoading">{t("common.loading")}</div>;
  if (!rows.length)
    return (
      <div className="empty">
        <p>{empty ?? t("biz.noOrders")}</p>
      </div>
    );
  return (
    <div className="orderTable">
      <div className="orderHead" aria-hidden="true">
        <span>{t("biz.col.order")}</span>
        <span>{t("biz.col.customer")}</span>
        <span>{t("ops.col.items")}</span>
        <span>{t("ops.col.due")}</span>
        <span>{t("biz.col.status")}</span>
        <span>{t("biz.col.total")}</span>
      </div>
      {rows.map((r) => (
        <Link
          to={`/app/orders/${r.id}`}
          className={`orderRow ${r.due_state === "OVERDUE" ? "isOverdue" : ""}`}
          key={r.id}
        >
          <span className="num">
            <b>{r.order_number}</b>
            <small>
              {dateTime(r.created_at)} · {t(`biz.source.${r.source}`)}
            </small>
          </span>
          <span>
            {r.customer_name}
            <small>{r.phone}</small>
          </span>
          <span className="itemsCell">
            {itemsSummary(r.items) || "—"}
            {r.fulfillment === "PICKUP" && (
              <small>{t("checkout.pickup")}</small>
            )}
          </span>
          <span>
            <DueBadge o={r} />
          </span>
          <span>
            <StatusPill status={r.status} />
          </span>
          <span className="amount">
            <b>{money(r.total)}</b>
            <small className={`pay ${r.payment_status.toLowerCase()}`}>
              {t(`payment.${r.payment_status}`)}
            </small>
          </span>
        </Link>
      ))}
    </div>
  );
}

const FILTER_KEYS = [
  "q",
  "status",
  "source",
  "due",
  "payment",
  "date_from",
  "date_to",
  "customer_id",
];

export function Orders() {
  const { t } = useTranslation();
  const can = useCan();
  const [params, setParams] = useSearchParams();
  const view = params.get("view") ?? "all";
  const page = Number(params.get("page") ?? 1);
  const [q, setQ] = useState(params.get("q") ?? "");
  const [rows, setRows] = useState<OrderRow[] | null>(null);
  const [total, setTotal] = useState(0);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [error, setError] = useState("");
  const pageSize = 20;

  const update = useCallback(
    (changes: Record<string, string | null>) => {
      const next = new URLSearchParams(params);
      for (const [k, v] of Object.entries(changes)) {
        if (v) next.set(k, v);
        else next.delete(k);
      }
      if (!("page" in changes)) next.delete("page");
      setParams(next, { replace: "q" in changes });
    },
    [params, setParams],
  );

  // Debounced search writes into the URL so it survives back/forward and can be shared.
  useEffect(() => {
    const timer = setTimeout(() => {
      if ((params.get("q") ?? "") !== q) update({ q: q || null });
    }, 300);
    return () => clearTimeout(timer);
  }, [q]);

  const query = useMemo(() => {
    const p = new URLSearchParams({
      view,
      page: String(page),
      page_size: String(pageSize),
    });
    for (const k of FILTER_KEYS) {
      const v = params.get(k);
      if (v) p.set(k, v);
    }
    return p;
  }, [params, view, page]);

  useEffect(() => {
    const controller = new AbortController();
    setRows(null);
    setError("");
    api<{ items: OrderRow[]; total: number }>(
      `/api/v1/business/orders?${query}`,
      {
        auth: "business",
        signal: controller.signal,
      },
    )
      .then((d) => {
        setRows(d.items);
        setTotal(d.total);
      })
      .catch((err) => err.name !== "AbortError" && setError(errorMessage(err)));
    api<Record<string, number>>("/api/v1/business/orders/counts", {
      auth: "business",
      signal: controller.signal,
    })
      .then(setCounts)
      .catch(() => undefined);
    return () => controller.abort();
  }, [query]);

  async function exportCsv() {
    const p = new URLSearchParams(query);
    p.delete("page");
    p.delete("page_size");
    try {
      await download(
        `/api/v1/business/orders/export.csv?${p}`,
        "business",
        "orders.csv",
      );
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  const views = can("orders.deliveries_only")
    ? (["all", "delivery"] as const)
    : VIEWS;
  const active = FILTER_KEYS.filter((k) => k !== "q" && params.get(k));

  return (
    <AppFrame
      title={t("biz.nav.orders")}
      action={
        can("orders.create") && (
          <Link className="primary" to="/app/orders/new">
            <Plus aria-hidden /> {t("biz.newOrder")}
          </Link>
        )
      }
    >
      <nav className="viewTabs" aria-label={t("ops.orders.views")}>
        {views.map((v) => (
          <button
            key={v}
            className={view === v ? "on" : ""}
            aria-current={view === v ? "page" : undefined}
            onClick={() => update({ view: v === "all" ? null : v })}
          >
            {t(`ops.view.${v}`)}
            {counts[v] != null && <span>{counts[v]}</span>}
          </button>
        ))}
      </nav>
      {!can("orders.deliveries_only") && (
        <div
          className="urgency"
          role="group"
          aria-label={t("ops.orders.urgency")}
        >
          {DUE.map((d) => (
            <button
              key={d}
              className={`chip ${d} ${params.get("due") === d ? "on" : ""}`}
              aria-pressed={params.get("due") === d}
              onClick={() =>
                update({ due: params.get("due") === d ? null : d })
              }
            >
              {t(`ops.dueFilter.${d}`)} <b>{counts[`due_${d}`] ?? 0}</b>
            </button>
          ))}
        </div>
      )}
      <div className="toolbar filters">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t("biz.searchOrders")}
          aria-label={t("biz.searchOrders")}
          type="search"
        />
        <label className="inline">
          <span>{t("ops.orders.from")}</span>
          <input
            type="date"
            value={params.get("date_from") ?? ""}
            onChange={(e) => update({ date_from: e.target.value || null })}
          />
        </label>
        <label className="inline">
          <span>{t("ops.orders.to")}</span>
          <input
            type="date"
            value={params.get("date_to") ?? ""}
            onChange={(e) => update({ date_to: e.target.value || null })}
          />
        </label>
        <select
          value={params.get("source") ?? ""}
          onChange={(e) => update({ source: e.target.value || null })}
          aria-label={t("biz.col.source")}
        >
          <option value="">{t("ops.orders.anySource")}</option>
          {["WALK_IN", "MARKETPLACE", "PHONE", "WHATSAPP"].map((s) => (
            <option key={s} value={s}>
              {t(`biz.source.${s}`)}
            </option>
          ))}
        </select>
        <select
          value={params.get("payment") ?? ""}
          onChange={(e) => update({ payment: e.target.value || null })}
          aria-label={t("checkout.payment")}
        >
          <option value="">{t("ops.orders.anyPayment")}</option>
          {["outstanding", "unpaid", "paid", "processing"].map((s) => (
            <option key={s} value={s}>
              {t(`ops.paymentFilter.${s}`)}
            </option>
          ))}
        </select>
        {can("reports.operational") && (
          <button className="outlineBtn" onClick={exportCsv}>
            <Download aria-hidden /> {t("biz.exportCsv")}
          </button>
        )}
      </div>
      {active.length > 0 && (
        <div className="activeFilters">
          {active.map((k) => (
            <button
              key={k}
              className="chip on"
              onClick={() => update({ [k]: null })}
            >
              {filterLabel(t, k, params.get(k)!)}{" "}
              <X aria-label={t("ops.orders.remove")} />
            </button>
          ))}
          <button
            className="textBtn"
            onClick={() => setParams(view === "all" ? {} : { view })}
          >
            {t("ops.orders.clear")}
          </button>
        </div>
      )}
      {error && <Notice>{error}</Notice>}
      <section className="orders">
        <OrderRows
          rows={rows}
          empty={active.length || q ? t("ops.orders.noMatch") : undefined}
        />
        <Pagination
          page={page}
          pages={Math.max(1, Math.ceil(total / pageSize))}
          total={total}
          pageSize={pageSize}
          onPage={(p) => update({ page: String(p) })}
        />
      </section>
    </AppFrame>
  );
}

function filterLabel(t: TFunction, key: string, value: string) {
  switch (key) {
    case "status":
      return value.split(",").map(statusLabel).join(", ");
    case "source":
      return t(`biz.source.${value}`);
    case "due":
      return t(`ops.dueFilter.${value}`);
    case "payment":
      return t(`ops.paymentFilter.${value}`);
    case "date_from":
      return `${t("ops.orders.from")} ${value}`;
    case "date_to":
      return `${t("ops.orders.to")} ${value}`;
    default:
      return t("ops.orders.oneCustomer");
  }
}

export function localInput(d: Date) {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

type BusinessOrder = OrderDetail & {
  customer: {
    id: string;
    name: string;
    phone: string | null;
    is_guest: boolean;
  };
  amount_paid: number;
  balance: number;
  payments: {
    method: string;
    amount: number;
    status: string;
    reference: string | null;
    paid_at: string;
  }[];
  can_collect: boolean;
  allowed_next: string[];
  source: string;
  notes: string;
  discount: number;
  due_at: string | null;
  ready_at: string | null;
  due_state: OrderRow["due_state"];
  can_edit_due: boolean;
  can_record_payment: boolean;
};

export function OrderDetailPage() {
  const { id = "" } = useParams();
  const { t } = useTranslation();
  const can = useCan();
  const [order, setOrder] = useState<BusinessOrder | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [editDue, setEditDue] = useState<string | null>(null);
  const [payMethod, setPayMethod] = useState<"CASH" | "MOBILE_MONEY">("CASH");
  const [payAmount, setPayAmount] = useState(0);
  const [payRef, setPayRef] = useState("");

  const load = useCallback(() => {
    api<BusinessOrder>(`/api/v1/business/orders/${id}`, { auth: "business" })
      .then(setOrder)
      .catch((e) => setError(errorMessage(e)));
  }, [id]);
  useEffect(load, [load]);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await fn();
      load();
      return true;
    } catch (err) {
      setError(errorMessage(err));
      return false;
    } finally {
      setBusy(false);
    }
  }

  function move(status: string) {
    let note = "";
    if (status === "REJECTED" || status === "CANCELLED") {
      note = window.prompt(t("biz.reasonPrompt")) ?? "";
      if (!note.trim()) return;
    }
    run(() =>
      api(`/api/v1/business/orders/${id}/status`, {
        auth: "business",
        body: { status, note },
      }),
    );
  }

  const payment = () => ({
    method: payMethod,
    amount:
      payAmount && order && payAmount < order.balance ? payAmount : undefined,
    reference: payMethod === "MOBILE_MONEY" ? payRef.trim() : "",
  });
  const pay = () =>
    run(() =>
      api(`/api/v1/business/orders/${id}/payments`, {
        auth: "business",
        body: payment(),
      }),
    ).then((ok) => ok && (setPayAmount(0), setPayRef("")));
  const collect = () =>
    run(() =>
      api(`/api/v1/business/orders/${id}/collect`, {
        auth: "business",
        body:
          order && order.balance > 0
            ? { payment: { ...payment(), amount: undefined } }
            : {},
      }),
    );

  if (!order)
    return (
      <AppFrame title={t("biz.nav.orders")}>
        {error ? (
          <Notice>{error}</Notice>
        ) : (
          <div className="tableLoading">{t("common.loading")}</div>
        )}
      </AppFrame>
    );

  const forward = order.allowed_next.filter(
    (s) => s !== "CANCELLED" && s !== "REJECTED",
  );
  const stop = order.allowed_next.filter(
    (s) => s === "CANCELLED" || s === "REJECTED",
  );
  const reached = new Set(order.events.map((e) => e.status));
  const unpaid =
    order.payment_status !== "PAID" &&
    order.payment_status !== "REFUNDED" &&
    order.payment_status !== "PROCESSING" &&
    !["CANCELLED", "REJECTED"].includes(order.status);

  return (
    <AppFrame title={t("biz.orderTitle", { number: order.order_number })}>
      {error && <Notice>{error}</Notice>}
      <div className="detailGrid">
        <section className="workspaceCard">
          <div className="spread">
            <div>
              <p className="kicker">
                {can("customers.view") && !order.customer.is_guest ? (
                  <Link to={`/app/customers/${order.customer.id}`}>
                    {order.customer.name}
                  </Link>
                ) : (
                  order.customer.name
                )}{" "}
                · {t(`biz.source.${order.source}`)}
              </p>
              <h2>{itemsSummary(order.items) || money(order.total)}</h2>
              <p className="muted">
                {order.customer.phone && (
                  <>
                    <a href={`tel:${order.customer.phone}`}>
                      {order.customer.phone}
                    </a>{" "}
                    ·{" "}
                  </>
                )}
                {order.fulfillment === "PICKUP"
                  ? t("checkout.pickup")
                  : t("checkout.dropOff")}
                {order.pickup_window_start &&
                  ` · ${dateTime(order.pickup_window_start)}`}
              </p>
              {order.pickup_address && (
                <p className="muted">{order.pickup_address}</p>
              )}
              {order.notes && <p className="muted">“{order.notes}”</p>}
            </div>
            <StatusPill status={order.status} />
          </div>
          <div className="dueLine">
            <span>
              {order.ready_at
                ? t("ops.detail.readyAt", { time: dateTime(order.ready_at) })
                : order.due_at
                  ? t("ops.detail.promised", { time: dateTime(order.due_at) })
                  : t("ops.detail.noPromise")}
            </span>
            <DueBadge o={order} />
            {order.can_edit_due && editDue === null && (
              <button
                className="textBtn"
                onClick={() =>
                  setEditDue(
                    order.due_at ? localInput(new Date(order.due_at)) : "",
                  )
                }
              >
                {t("ops.detail.changePromise")}
              </button>
            )}
          </div>
          {editDue !== null && (
            <form
              className="inlineForm"
              onSubmit={(e) => {
                e.preventDefault();
                run(() =>
                  api(`/api/v1/business/orders/${id}`, {
                    auth: "business",
                    method: "PATCH",
                    body: { due_at: new Date(editDue).toISOString() },
                  }),
                ).then((ok) => ok && setEditDue(null));
              }}
            >
              <input
                type="datetime-local"
                required
                value={editDue}
                onChange={(e) => setEditDue(e.target.value)}
                aria-label={t("ops.newOrder.promised")}
              />
              <button className="outlineBtn" disabled={busy}>
                {t("biz.save")}
              </button>
              <button
                type="button"
                className="textBtn"
                onClick={() => setEditDue(null)}
              >
                {t("common.cancel")}
              </button>
            </form>
          )}
          <div className="orderTimeline">
            {order.stages.map((s, i) => {
              const current = order.stages.indexOf(order.status);
              const state = reached.has(s)
                ? "done"
                : i < current
                  ? "skipped"
                  : "";
              return (
                <div key={s} className={state}>
                  <i>{state === "done" ? <Check /> : i + 1}</i>
                  <span>{statusLabel(s)}</span>
                </div>
              );
            })}
          </div>
          {forward.length > 0 && (
            <div className="actions">
              {forward.map((s, i) => (
                <button
                  key={s}
                  className={i === 0 ? "primary" : "outlineBtn"}
                  disabled={busy}
                  onClick={() => move(s)}
                >
                  {t("biz.moveTo", { status: statusLabel(s) })}
                </button>
              ))}
            </div>
          )}
          {stop.length > 0 && (
            <div className="actions">
              {stop.map((s) => (
                <button
                  key={s}
                  className="textBtn danger"
                  disabled={busy}
                  onClick={() => move(s)}
                >
                  {t(s === "REJECTED" ? "biz.reject" : "biz.cancelOrder")}
                </button>
              ))}
            </div>
          )}
        </section>
        <aside className="workspaceCard">
          <h3>{t("track.summary")}</h3>
          {order.items.map((i) => (
            <p className="spread" key={i.name}>
              <span>
                {i.quantity}
                {i.pricing_model === "PER_KG" ? " kg" : "×"} {i.name}
              </span>
              <b>{money(i.line_total)}</b>
            </p>
          ))}
          {order.delivery_fee > 0 && (
            <p className="spread">
              <span>{t("checkout.pickupFee")}</span>
              <b>{money(order.delivery_fee)}</b>
            </p>
          )}
          {order.discount > 0 && (
            <p className="spread">
              <span>{t("ops.newOrder.discount")}</span>
              <b>−{money(order.discount)}</b>
            </p>
          )}
          <hr />
          <p className="spread">
            <b>{t("common.total")}</b>
            <strong>{money(order.total)}</strong>
          </p>
          <p className="spread">
            <span>{t("checkout.payment")}</span>
            <b className={`pay ${order.payment_status.toLowerCase()}`}>
              {order.payment_method === "CASH"
                ? t("checkout.cash")
                : t("checkout.mobile")}{" "}
              · {t(`payment.${order.payment_status}`)}
            </b>
          </p>
          {order.payments.map((p, n) => (
            <p className="spread muted" key={n}>
              <span>
                {t("walkin.paid")} ·{" "}
                {p.method === "CASH"
                  ? t("checkout.cash")
                  : t("ops.pay.mobileShort")}
                {p.reference && ` · ${p.reference}`}
              </span>
              <span>{money(p.amount)}</span>
            </p>
          ))}
          {order.balance > 0 && order.amount_paid > 0 && (
            <p className="spread">
              <b>{t("walkin.balanceDue")}</b>
              <strong>{money(order.balance)}</strong>
            </p>
          )}
          {unpaid && order.can_record_payment && (
            <div className="payActions">
              <div
                className="segmented small"
                role="group"
                aria-label={t("checkout.payment")}
              >
                {(["CASH", "MOBILE_MONEY"] as const).map((m) => (
                  <button
                    key={m}
                    className={payMethod === m ? "on" : ""}
                    aria-pressed={payMethod === m}
                    onClick={() => setPayMethod(m)}
                  >
                    {m === "CASH"
                      ? t("checkout.cash")
                      : t("ops.pay.mobileShort")}
                  </button>
                ))}
              </div>
              <label>
                {t("walkin.amountNow")}
                <input
                  type="number"
                  min={100}
                  max={order.balance}
                  step={100}
                  placeholder={String(order.balance)}
                  value={payAmount || ""}
                  onChange={(e) =>
                    setPayAmount(Math.max(0, Number(e.target.value) || 0))
                  }
                />
              </label>
              {payMethod === "MOBILE_MONEY" && (
                <input
                  value={payRef}
                  onChange={(e) => setPayRef(e.target.value)}
                  placeholder={t("ops.pay.reference")}
                  aria-label={t("ops.pay.reference")}
                  maxLength={60}
                />
              )}
              {!order.can_collect && (
                <button
                  className="outlineBtn full"
                  disabled={busy}
                  onClick={pay}
                >
                  {payMethod === "CASH" ? (
                    <Banknote aria-hidden />
                  ) : (
                    <Smartphone aria-hidden />
                  )}{" "}
                  {t("ops.pay.confirm", {
                    amount: money(
                      payAmount && payAmount < order.balance
                        ? payAmount
                        : order.balance,
                    ),
                  })}
                </button>
              )}
            </div>
          )}
          {order.can_collect && (
            <button className="primary full" disabled={busy} onClick={collect}>
              <PackageCheck aria-hidden />{" "}
              {order.balance > 0
                ? t("walkin.collectAndPay", { amount: money(order.balance) })
                : t("walkin.collected")}
            </button>
          )}
          <Link className="textLink" to={`/app/orders/${order.id}/slip`}>
            <Printer aria-hidden /> {t("walkin.printSlip")}
          </Link>
        </aside>
      </div>
    </AppFrame>
  );
}
