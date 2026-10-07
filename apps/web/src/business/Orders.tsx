import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight, Banknote, Check, Minus, Plus } from "lucide-react";
import { api } from "../lib/api";
import { dateTime, errorMessage, money, statusLabel } from "../lib/format";
import { Notice, StatusPill } from "../customer/ui";
import type { OrderDetail, ServiceData } from "../customer/types";
import { AppFrame, Pagination } from "./shell";

export type OrderRow = {
  id: string;
  order_number: string;
  customer_name: string;
  phone: string;
  source: string;
  status: string;
  fulfillment: string;
  payment_status: string;
  total: number;
  created_at: string;
  pickup_window_start: string | null;
};

const FILTERS = [
  "",
  "NEW",
  "ACCEPTED,AWAITING_PICKUP,RECEIVED,WASHING,DRYING,IRONING,QUALITY_CHECK",
  "READY,OUT_FOR_DELIVERY",
  "DELIVERED,COMPLETED",
  "CANCELLED,REJECTED",
];

export function OrderRows({ rows }: { rows: OrderRow[] | null }) {
  const { t } = useTranslation();
  if (!rows) return <div className="tableLoading">{t("common.loading")}</div>;
  if (!rows.length)
    return (
      <div className="empty">
        <p>{t("biz.noOrders")}</p>
      </div>
    );
  return (
    <>
      <div className="tableHead">
        <span>{t("biz.col.order")}</span>
        <span>{t("biz.col.customer")}</span>
        <span>{t("biz.col.source")}</span>
        <span>{t("biz.col.status")}</span>
        <span>{t("biz.col.total")}</span>
      </div>
      {rows.map((r) => (
        <Link to={`/app/orders/${r.id}`} className="order" key={r.id}>
          <b>{r.order_number}</b>
          <span>
            {r.customer_name}
            <small>{r.phone}</small>
          </span>
          <span>{t(`biz.source.${r.source}`)}</span>
          <StatusPill status={r.status} />
          <b>
            {money(r.total)}
            <small className={`pay ${r.payment_status.toLowerCase()}`}>
              {t(`payment.${r.payment_status}`)}
            </small>
          </b>
        </Link>
      ))}
    </>
  );
}

export function Orders() {
  const { t } = useTranslation();
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("");
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState<OrderRow[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const pageSize = 20;

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
      });
      if (q) params.set("q", q);
      if (filter) params.set("status", filter);
      setRows(null);
      api<{ items: OrderRow[]; total: number }>(
        `/api/v1/business/orders?${params}`,
        { auth: "business", signal: controller.signal },
      )
        .then((d) => {
          setRows(d.items);
          setTotal(d.total);
        })
        .catch(
          (err) => err.name !== "AbortError" && setError(errorMessage(err)),
        );
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [q, filter, page]);

  async function exportCsv() {
    const params = new URLSearchParams({ page: "1", page_size: "100" });
    if (q) params.set("q", q);
    if (filter) params.set("status", filter);
    const d = await api<{ items: OrderRow[] }>(
      `/api/v1/business/orders?${params}`,
      { auth: "business" },
    );
    const header = [
      "Order",
      "Customer",
      "Phone",
      "Source",
      "Status",
      "Payment",
      "Total TZS",
      "Created",
    ];
    const csv = [
      header,
      ...d.items.map((x) => [
        x.order_number,
        x.customer_name,
        x.phone,
        x.source,
        x.status,
        x.payment_status,
        x.total,
        x.created_at,
      ]),
    ]
      .map((row) =>
        row.map((v) => `"${String(v).replaceAll('"', '""')}"`).join(","),
      )
      .join("\n");
    const url = URL.createObjectURL(
      new Blob([csv], { type: "text/csv;charset=utf-8" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `orders-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <AppFrame
      title={t("biz.nav.orders")}
      action={
        <Link className="primary" to="/app/orders/new">
          <Plus /> {t("biz.newOrder")}
        </Link>
      }
    >
      <div className="toolbar">
        <input
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
          placeholder={t("biz.searchOrders")}
          aria-label={t("biz.searchOrders")}
        />
        <select
          value={filter}
          onChange={(e) => {
            setFilter(e.target.value);
            setPage(1);
          }}
          aria-label={t("biz.col.status")}
        >
          {FILTERS.map((f, i) => (
            <option key={f} value={f}>
              {t(`biz.filters.${i}`)}
            </option>
          ))}
        </select>
        <button className="outlineBtn exportBtn" onClick={exportCsv}>
          {t("biz.exportCsv")}
        </button>
      </div>
      {error && <Notice>{error}</Notice>}
      <section className="orders">
        <OrderRows rows={rows} />
        <Pagination
          page={page}
          pages={Math.max(1, Math.ceil(total / pageSize))}
          total={total}
          pageSize={pageSize}
          onPage={setPage}
        />
      </section>
    </AppFrame>
  );
}

export function NewOrder() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const [services, setServices] = useState<ServiceData[]>([]);
  const [qty, setQty] = useState<Record<string, number>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<(ServiceData & { active: boolean })[]>("/api/v1/business/services", {
      auth: "business",
    }).then((s) => setServices(s.filter((x) => x.active)));
  }, []);

  const total = services.reduce(
    (sum, s) => sum + Math.round((qty[s.id] ?? 0) * s.price),
    0,
  );
  const step = (s: ServiceData) => (s.pricing_model === "PER_KG" ? 0.5 : 1);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    const fd = new FormData(e.currentTarget);
    setBusy(true);
    setError("");
    try {
      const order = await api<{ id: string }>("/api/v1/business/orders", {
        auth: "business",
        body: {
          customer_name: fd.get("customer_name"),
          phone: fd.get("phone"),
          source: fd.get("source"),
          payment_method: "CASH",
          notes: fd.get("notes"),
          items: Object.entries(qty)
            .filter(([, n]) => n > 0)
            .map(([service_id, quantity]) => ({ service_id, quantity })),
        },
      });
      nav(`/app/orders/${order.id}`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppFrame title={t("biz.newOrder")}>
      <form className="workspaceForm" onSubmit={submit}>
        <h2>{t("biz.col.customer")}</h2>
        <div className="twoFields">
          <label>
            {t("checkout.name")}
            <input name="customer_name" required minLength={2} />
          </label>
          <label>
            {t("checkout.phone")}
            <input
              name="phone"
              type="tel"
              required
              placeholder="+255 7xx xxx xxx"
            />
          </label>
        </div>
        <label>
          {t("biz.col.source")}
          <select name="source" defaultValue="WALK_IN">
            {["WALK_IN", "PHONE", "WHATSAPP"].map((s) => (
              <option key={s} value={s}>
                {t(`biz.source.${s}`)}
              </option>
            ))}
          </select>
        </label>
        <h2>{t("biz.nav.services")}</h2>
        {services.map((s) => (
          <div className="selectService" key={s.id}>
            <span>
              <b>{s.name}</b>
              <small>
                {money(s.price)}
                {s.pricing_model === "PER_KG" && t("common.perKg")}
              </small>
            </span>
            <div className="counter">
              <button
                type="button"
                aria-label={t("store.remove", { name: s.name })}
                onClick={() =>
                  setQty({
                    ...qty,
                    [s.id]: Math.max(0, (qty[s.id] ?? 0) - step(s)),
                  })
                }
              >
                <Minus />
              </button>
              <b>{qty[s.id] ?? 0}</b>
              <button
                type="button"
                aria-label={t("store.add", { name: s.name })}
                onClick={() =>
                  setQty({ ...qty, [s.id]: (qty[s.id] ?? 0) + step(s) })
                }
              >
                <Plus />
              </button>
            </div>
          </div>
        ))}
        <label>
          {t("biz.notes")}
          <textarea
            name="notes"
            maxLength={500}
            placeholder={t("biz.notesHint")}
          />
        </label>
        <div className="formTotal">
          <span>{t("common.total")}</span>
          <b>{money(total)}</b>
        </div>
        {error && <Notice>{error}</Notice>}
        <button className="primary" disabled={busy || total === 0}>
          {t("biz.createOrder")} <ArrowRight />
        </button>
      </form>
    </AppFrame>
  );
}

type BusinessOrder = OrderDetail & {
  customer: { name: string; phone: string };
  allowed_next: string[];
  source: string;
  notes: string;
};

export function OrderDetailPage() {
  const { id = "" } = useParams();
  const { t } = useTranslation();
  const [order, setOrder] = useState<BusinessOrder | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

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
    } catch (err) {
      setError(errorMessage(err));
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

  return (
    <AppFrame title={t("biz.orderTitle", { number: order.order_number })}>
      {error && <Notice>{error}</Notice>}
      <div className="detailGrid">
        <section className="workspaceCard">
          <div className="spread">
            <div>
              <p className="kicker">
                {order.customer.name} · {t(`biz.source.${order.source}`)}
              </p>
              <h2>
                {order.items
                  .map(
                    (i) =>
                      `${i.quantity}${i.pricing_model === "PER_KG" ? " kg" : "×"} ${i.name}`,
                  )
                  .join(", ") || money(order.total)}
              </h2>
              <p className="muted">
                {order.customer.phone} ·{" "}
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
          {order.payment_status !== "PAID" &&
            order.payment_status !== "REFUNDED" &&
            order.payment_status !== "PROCESSING" &&
            !["CANCELLED", "REJECTED"].includes(order.status) && (
              <button
                className="outlineBtn full"
                disabled={busy}
                onClick={() =>
                  run(() =>
                    api(`/api/v1/business/orders/${id}/payments/cash`, {
                      auth: "business",
                      method: "POST",
                    }),
                  )
                }
              >
                <Banknote />{" "}
                {t("biz.recordCash", { amount: money(order.total) })}
              </button>
            )}
        </aside>
      </div>
    </AppFrame>
  );
}
