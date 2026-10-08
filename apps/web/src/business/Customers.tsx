import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Banknote,
  MessageCircle,
  Phone,
  Plus,
  Smartphone,
  UserPlus,
  X,
} from "lucide-react";
import { api } from "../lib/api";
import { date, dateTime, errorMessage, money, moneyShort } from "../lib/format";
import { Notice } from "../customer/ui";
import { AppFrame, Pagination } from "./shell";
import { OrderRows, type OrderRow } from "./Orders";
import {
  PeriodPicker,
  StatCard,
  type PeriodValue,
  periodQuery,
  useCan,
} from "./ui";

type CustomerRow = {
  id: string;
  name: string;
  phone: string;
  email: string | null;
  has_app: boolean;
  orders: number;
  spend: number;
  average_order: number;
  last_order_at: string | null;
  first_order_at: string | null;
  outstanding: number;
  segment: "NEW" | "RETURNING" | "FREQUENT";
  notes: string;
};

type CustomerDetail = CustomerRow & {
  preferred_services: { name: string; orders: number; quantity: number }[];
  recent_orders: OrderRow[];
};

const SEGMENTS = [
  "",
  "new",
  "returning",
  "frequent",
  "inactive",
  "outstanding",
] as const;
const SORTS = ["recent", "spend", "orders", "name"] as const;

const daysSince = (iso: string | null) =>
  iso ? Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000) : null;

function AddCustomer({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const nav = useNavigate();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    setBusy(true);
    setError("");
    try {
      const c = await api<CustomerRow>("/api/v1/business/customers", {
        auth: "business",
        body: {
          name: fd.get("name"),
          phone: fd.get("phone"),
          notes: fd.get("notes"),
        },
      });
      nav(`/app/customers/${c.id}`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form
      className="workspaceCard addCustomer"
      onSubmit={submit}
      aria-label={t("ops.cust.add")}
    >
      <div className="spread">
        <h2>{t("ops.cust.add")}</h2>
        <button
          type="button"
          className="iconBtn"
          onClick={onClose}
          aria-label={t("common.close")}
        >
          <X />
        </button>
      </div>
      <div className="twoFields">
        <label>
          {t("checkout.name")}
          <input name="name" required minLength={2} autoFocus />
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
        {t("ops.cust.notes")}
        <input
          name="notes"
          maxLength={500}
          placeholder={t("ops.cust.notesHint")}
        />
      </label>
      {error && <Notice>{error}</Notice>}
      <button className="primary" disabled={busy}>
        <UserPlus aria-hidden /> {t("ops.cust.save")}
      </button>
    </form>
  );
}

export function Customers() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState("");
  const segment = params.get("segment") ?? "";
  const sort = params.get("sort") ?? "recent";
  const [page, setPage] = useState(1);
  const [data, setData] = useState<{
    items: CustomerRow[];
    total: number;
  } | null>(null);
  const [error, setError] = useState("");
  const adding = params.get("add") === "1";

  const set = (k: string, v: string | null) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    setParams(next, { replace: true });
    setPage(1);
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      const p = new URLSearchParams({
        page: String(page),
        page_size: "20",
        sort,
      });
      if (q) p.set("q", q);
      if (segment) p.set("segment", segment);
      api<{ items: CustomerRow[]; total: number }>(
        `/api/v1/business/customers?${p}`,
        { auth: "business" },
      )
        .then(setData)
        .catch((e) => setError(errorMessage(e)));
    }, 250);
    return () => clearTimeout(timer);
  }, [q, page, segment, sort]);

  return (
    <AppFrame
      title={t("biz.nav.customers")}
      action={
        !adding && (
          <button className="primary" onClick={() => set("add", "1")}>
            <Plus aria-hidden /> {t("ops.cust.add")}
          </button>
        )
      }
    >
      {adding && <AddCustomer onClose={() => set("add", null)} />}
      <nav className="viewTabs" aria-label={t("ops.cust.segments")}>
        {SEGMENTS.map((s) => (
          <button
            key={s || "all"}
            className={segment === s ? "on" : ""}
            onClick={() => set("segment", s || null)}
          >
            {t(`ops.segment.${s || "all"}`)}
          </button>
        ))}
      </nav>
      <div className="toolbar">
        <input
          type="search"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
          placeholder={t("biz.searchCustomers")}
          aria-label={t("biz.searchCustomers")}
        />
        <select
          value={sort}
          onChange={(e) => set("sort", e.target.value)}
          aria-label={t("ops.cust.sort")}
        >
          {SORTS.map((s) => (
            <option key={s} value={s}>
              {t(`ops.cust.sortBy.${s}`)}
            </option>
          ))}
        </select>
      </div>
      {segment === "inactive" && (
        <p className="dashSub">{t("ops.cust.inactiveHint")}</p>
      )}
      {error && <Notice>{error}</Notice>}
      <section className="orders">
        <div className="custHead">
          <span>{t("biz.col.customer")}</span>
          <span>{t("ops.cust.orders")}</span>
          <span>{t("ops.cust.spend")}</span>
          <span>{t("ops.cust.lastOrder")}</span>
          <span />
        </div>
        {!data && <div className="tableLoading">{t("common.loading")}</div>}
        {data && !data.items.length && (
          <div className="empty">
            <p>{t("ops.cust.none")}</p>
          </div>
        )}
        {data?.items.map((c) => (
          <button
            className="custRow"
            key={c.id}
            onClick={() => nav(`/app/customers/${c.id}`)}
          >
            <span>
              <b>{c.name}</b>
              <small>
                {c.phone}
                {c.has_app && ` · ${t("biz.usesApp")}`}
              </small>
            </span>
            <span>{c.orders}</span>
            <span>
              {money(c.spend)}
              {c.outstanding > 0 && (
                <small className="pay pending">
                  {t("ops.cust.owes", { amount: money(c.outstanding) })}
                </small>
              )}
            </span>
            <span>
              {c.last_order_at ? date(c.last_order_at) : "—"}
              {(daysSince(c.last_order_at) ?? 0) >= 45 && (
                <small>
                  {t("ops.cust.daysAgo", {
                    count: daysSince(c.last_order_at)!,
                  })}
                </small>
              )}
            </span>
            <span>
              <span className={`segment ${c.segment.toLowerCase()}`}>
                {t(`ops.segment.${c.segment.toLowerCase()}`)}
              </span>
            </span>
          </button>
        ))}
        {data && data.total > 20 && (
          <Pagination
            page={page}
            pages={Math.ceil(data.total / 20)}
            total={data.total}
            pageSize={20}
            onPage={setPage}
          />
        )}
      </section>
    </AppFrame>
  );
}

export function CustomerProfile() {
  const { id = "" } = useParams();
  const { t } = useTranslation();
  const can = useCan();
  const [c, setC] = useState<CustomerDetail | null>(null);
  const [notes, setNotes] = useState<string | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    api<CustomerDetail>(`/api/v1/business/customers/${id}`, {
      auth: "business",
    })
      .then((d) => {
        setC(d);
        setNotes(null);
      })
      .catch((e) => setError(errorMessage(e)));
  }, [id]);
  useEffect(load, [load]);

  if (!c)
    return (
      <AppFrame title={t("biz.nav.customers")}>
        {error ? (
          <Notice>{error}</Notice>
        ) : (
          <div className="tableLoading">{t("common.loading")}</div>
        )}
      </AppFrame>
    );
  const since = daysSince(c.last_order_at);
  const wa = c.phone.replace(/\D/g, "");
  return (
    <AppFrame
      title={c.name}
      kicker={`${t(`ops.segment.${c.segment.toLowerCase()}`)} · ${c.phone}`}
      action={
        can("orders.create") && (
          <Link className="primary" to={`/app/orders/new?customer=${c.id}`}>
            <Plus aria-hidden /> {t("ops.cust.newOrderFor")}
          </Link>
        )
      }
    >
      <div className="contactBar">
        <a className="outlineBtn" href={`tel:${c.phone}`}>
          <Phone aria-hidden /> {t("ops.cust.call")}
        </a>
        <a
          className="outlineBtn"
          href={`https://wa.me/${wa}`}
          target="_blank"
          rel="noreferrer"
        >
          <MessageCircle aria-hidden /> WhatsApp
        </a>
        {c.has_app && <span className="pill">{t("biz.usesApp")}</span>}
      </div>
      <section className="todayGrid">
        <StatCard
          label={t("ops.cust.orders")}
          value={c.orders}
          sub={
            c.first_order_at
              ? t("ops.cust.since", { date: date(c.first_order_at) })
              : undefined
          }
        />
        <StatCard
          label={t("ops.cust.lifetime")}
          value={moneyShort(c.spend)}
          sub={t("ops.cust.average", { amount: money(c.average_order) })}
        />
        <StatCard
          label={t("ops.cust.lastOrder")}
          value={c.last_order_at ? date(c.last_order_at) : "—"}
          sub={
            since != null ? t("ops.cust.daysAgo", { count: since }) : undefined
          }
        />
        <StatCard
          label={t("ops.cust.outstanding")}
          value={money(c.outstanding)}
          tone={c.outstanding > 0 ? "alert" : undefined}
          to={
            c.outstanding > 0
              ? `/app/orders?customer_id=${c.id}&payment=outstanding`
              : undefined
          }
        />
      </section>
      <div className="opsCols">
        <section className="panel">
          <h2>{t("ops.cust.recentOrders")}</h2>
          <OrderRows rows={c.recent_orders} />
          {c.orders > 10 && (
            <Link className="textLink" to={`/app/orders?customer_id=${c.id}`}>
              {t("biz.viewAll")}
            </Link>
          )}
        </section>
        <section className="panel">
          <h2>{t("ops.cust.preferred")}</h2>
          {c.preferred_services.length ? (
            <ol className="plainList">
              {c.preferred_services.map((s) => (
                <li key={s.name}>
                  <b>{s.name}</b>{" "}
                  <small>{t("ops.cust.inOrders", { count: s.orders })}</small>
                </li>
              ))}
            </ol>
          ) : (
            <p className="muted">{t("ops.cust.noServices")}</p>
          )}
          <h2>{t("ops.cust.notes")}</h2>
          {notes === null ? (
            <>
              <p className={c.notes ? "" : "muted"}>
                {c.notes || t("ops.cust.noNotes")}
              </p>
              <button className="textBtn" onClick={() => setNotes(c.notes)}>
                {t("biz.edit")}
              </button>
            </>
          ) : (
            <form
              className="inlineForm"
              onSubmit={(e) => {
                e.preventDefault();
                api(`/api/v1/business/customers/${c.id}/notes`, {
                  auth: "business",
                  method: "PUT",
                  body: { notes },
                })
                  .then(load)
                  .catch((err) => setError(errorMessage(err)));
              }}
            >
              <input
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                maxLength={500}
                aria-label={t("ops.cust.notes")}
              />
              <button className="outlineBtn">{t("biz.save")}</button>
            </form>
          )}
        </section>
      </div>
    </AppFrame>
  );
}

type PaymentsData = {
  items: {
    id: string;
    method: string;
    amount: number;
    status: string;
    reference: string | null;
    paid_at: string;
    order_id: string;
    order_number: string;
    customer_name: string;
  }[];
  total: number;
  summary: {
    sales: number;
    collected: number;
    refunded: number;
    by_method: Record<string, { count: number; amount: number }>;
    outstanding_now: { count: number; amount: number };
    period: { compare_to: string };
  };
};

/** Money in, money owed: sales, collections and outstanding kept apart, with the people who still owe. */
export function Payments() {
  const { t } = useTranslation();
  const can = useCan();
  const [period, setPeriod] = useState<PeriodValue>({ period: "today" });
  const [data, setData] = useState<PaymentsData | null>(null);
  const [owed, setOwed] = useState<OrderRow[] | null>(null);
  const [owedTotal, setOwedTotal] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const load = useCallback(() => {
    api<PaymentsData>(
      `/api/v1/business/payments?${periodQuery(period)}&page_size=50`,
      { auth: "business" },
    )
      .then(setData)
      .catch((e) => setError(errorMessage(e)));
    api<{ items: OrderRow[]; total: number }>(
      "/api/v1/business/orders?payment=outstanding&page_size=50",
      {
        auth: "business",
      },
    )
      .then((r) => {
        setOwed(r.items);
        setOwedTotal(r.total);
      })
      .catch(() => setOwed([]));
  }, [period]);
  useEffect(load, [load]);

  async function record(o: OrderRow, method: "CASH" | "MOBILE_MONEY") {
    let reference = "";
    if (method === "MOBILE_MONEY") {
      reference = window.prompt(t("ops.pay.reference")) ?? "";
      if (reference === "" && !window.confirm(t("ops.pay.noReference"))) return;
    }
    setBusy(o.id);
    setError("");
    try {
      await api(`/api/v1/business/orders/${o.id}/payments`, {
        auth: "business",
        body: { method, reference: reference.trim() },
      });
      load();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  }

  const s = data?.summary;
  return (
    <AppFrame
      title={t("biz.nav.payments")}
      action={<PeriodPicker value={period} onChange={setPeriod} />}
    >
      <p className="dashSub">{t("ops.pay.intro")}</p>
      {error && <Notice>{error}</Notice>}
      <section className="todayGrid">
        <StatCard
          label={t("ops.money.sales")}
          value={s ? money(s.sales) : "…"}
          sub={t("ops.money.salesHint")}
        />
        <StatCard
          label={t("ops.money.collected")}
          value={s ? money(s.collected) : "…"}
          sub={
            s &&
            `${t("checkout.cash")} ${money(s.by_method.CASH.amount)} · ${t("ops.pay.mobileShort")} ${money(s.by_method.MOBILE_MONEY.amount)}`
          }
        />
        <StatCard
          label={t("ops.money.outstanding")}
          value={s ? money(s.outstanding_now.amount) : "…"}
          sub={
            s && t("ops.dash.ordersCount", { count: s.outstanding_now.count })
          }
          tone={s?.outstanding_now.amount ? "alert" : undefined}
        />
        <StatCard
          label={t("ops.money.refunded")}
          value={s ? money(s.refunded) : "…"}
        />
      </section>
      <section className="panel">
        <h2>{t("ops.pay.owed", { count: owedTotal })}</h2>
        <p className="muted small">{t("ops.pay.owedHint")}</p>
        {!owed && <div className="tableLoading">{t("common.loading")}</div>}
        {owed && !owed.length && (
          <div className="empty">
            <p>{t("ops.pay.nothingOwed")}</p>
          </div>
        )}
        {owed?.map((o) => (
          <div className="owedRow" key={o.id}>
            <Link to={`/app/orders/${o.id}`}>
              <b>{o.order_number}</b> · {o.customer_name}
              <small>{t(`status.${o.status}`)}</small>
            </Link>
            <b>
              {money(o.total - o.amount_paid)}
              {o.amount_paid > 0 && (
                <small>
                  {t("ops.pay.ofTotal", { amount: money(o.total) })}
                </small>
              )}
            </b>
            {can("payments.record") && (
              <span className="rowActions">
                <button
                  className="outlineBtn"
                  disabled={busy === o.id}
                  onClick={() => record(o, "CASH")}
                >
                  <Banknote aria-hidden /> {t("checkout.cash")}
                </button>
                <button
                  className="outlineBtn"
                  disabled={busy === o.id}
                  onClick={() => record(o, "MOBILE_MONEY")}
                >
                  <Smartphone aria-hidden /> {t("ops.pay.mobileShort")}
                </button>
              </span>
            )}
          </div>
        ))}
      </section>
      <section className="panel">
        <h2>{t("ops.pay.received")}</h2>
        {data && !data.items.length && (
          <p className="muted">{t("ops.pay.noneReceived")}</p>
        )}
        {data?.items.map((p) => (
          <Link className="owedRow" key={p.id} to={`/app/orders/${p.order_id}`}>
            <span>
              <b>{p.order_number}</b> · {p.customer_name}
              <small>
                {dateTime(p.paid_at)} ·{" "}
                {p.method === "CASH"
                  ? t("checkout.cash")
                  : t("ops.pay.mobileShort")}
                {p.reference && ` · ${p.reference}`}
              </small>
            </span>
            <b className={p.status === "REFUNDED" ? "pay refunded" : ""}>
              {money(p.amount)}
            </b>
          </Link>
        ))}
      </section>
    </AppFrame>
  );
}
