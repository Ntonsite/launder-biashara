import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft,
  Check,
  Minus,
  Plus,
  Printer,
  UserRound,
  X,
} from "lucide-react";
import { api } from "../lib/api";
import { dateTime, errorMessage, money } from "../lib/format";
import { Notice } from "../customer/ui";
import type { ServiceData } from "../customer/types";
import { AppFrame, useProfile } from "./shell";
import { localInput } from "./Orders";

type Service = ServiceData & {
  active: boolean;
  pricing_model: "PER_ITEM" | "PER_KG" | "PACKAGE";
};
type Match = { id: string; name: string; phone: string; orders: number };
type PayMode = "later" | "full" | "part";

const looksLikePhone = (v: string) => /^[+\d\s-]{9,}$/.test(v.trim());
const stepOf = (s: Service) => (s.pricing_model === "PER_KG" ? 0.5 : 1);

/**
 * Counter order, built for speed: the normal walk-in is "tap services → Create". Customer details are optional
 * (search existing, type a phone to add someone new, type a name for the slip, or leave it blank).
 */
export function NewOrder() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [services, setServices] = useState<Service[]>([]);
  const [qty, setQty] = useState<Record<string, number>>({});
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<Match[]>([]);
  const [selected, setSelected] = useState<Match | null>(null);
  const [newName, setNewName] = useState("");
  const [source, setSource] = useState<"WALK_IN" | "PHONE" | "WHATSAPP">(
    "WALK_IN",
  );
  const [due, setDue] = useState("");
  const [editDue, setEditDue] = useState(false);
  const [notes, setNotes] = useState("");
  const [discount, setDiscount] = useState(0);
  const [payMode, setPayMode] = useState<PayMode>("later");
  const [method, setMethod] = useState<"CASH" | "MOBILE_MONEY">("CASH");
  const [partAmount, setPartAmount] = useState(0);
  const [reference, setReference] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api<Service[]>("/api/v1/business/services", { auth: "business" })
      .then((s) => setServices(s.filter((x) => x.active)))
      .catch((e) => setError(errorMessage(e)));
    const id = params.get("customer");
    if (id)
      api<Match>(`/api/v1/business/customers/${id}`, { auth: "business" })
        .then(setSelected)
        .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (selected || query.trim().length < 2) return setMatches([]);
    const term = looksLikePhone(query)
      ? query.replace(/\D/g, "").slice(-9)
      : query.trim();
    const timer = setTimeout(() => {
      api<{ items: Match[] }>(
        `/api/v1/business/customers?q=${encodeURIComponent(term)}&page_size=5`,
        { auth: "business" },
      )
        .then((r) => setMatches(r.items))
        .catch(() => setMatches([]));
    }, 200);
    return () => clearTimeout(timer);
  }, [query, selected]);

  const groups = useMemo(() => {
    const map = new Map<string, Service[]>();
    for (const s of services)
      map.set(s.category, [...(map.get(s.category) ?? []), s]);
    return [...map.entries()];
  }, [services]);

  const subtotal = services.reduce(
    (sum, s) => sum + Math.round((qty[s.id] ?? 0) * s.price),
    0,
  );
  const total = Math.max(0, subtotal - discount);
  const chosen = services.filter((s) => (qty[s.id] ?? 0) > 0);
  const promised = new Date(
    Date.now() +
      Math.max(24, ...chosen.map((s) => s.turnaround_hours)) * 3_600_000,
  );
  const paidNow =
    payMode === "full"
      ? total
      : payMode === "part"
        ? Math.min(partAmount, total)
        : 0;
  const phoneTyped = !selected && looksLikePhone(query);
  const guestName = !selected && !phoneTyped ? query.trim() : "";

  const add = (s: Service, delta: number) =>
    setQty((q) => ({
      ...q,
      [s.id]: Math.max(0, Math.round(((q[s.id] ?? 0) + delta) * 2) / 2),
    }));

  async function submit(e: FormEvent, printSlip: boolean) {
    e.preventDefault();
    if (busy || !subtotal) return;
    setBusy(true);
    setError("");
    try {
      const order = await api<{ id: string }>("/api/v1/business/orders", {
        auth: "business",
        body: {
          customer_id: selected?.id,
          phone: phoneTyped ? query.trim() : "",
          customer_name: phoneTyped ? newName.trim() : guestName,
          source,
          notes,
          discount,
          due_at: editDue && due ? new Date(due).toISOString() : undefined,
          items: chosen.map((s) => ({ service_id: s.id, quantity: qty[s.id] })),
          payment:
            paidNow > 0
              ? {
                  method,
                  amount: paidNow,
                  reference: method === "MOBILE_MONEY" ? reference.trim() : "",
                }
              : undefined,
        },
      });
      nav(
        printSlip
          ? `/app/orders/${order.id}/slip?print=1`
          : `/app/orders/${order.id}`,
      );
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <AppFrame title={t("walkin.title")} kicker={t("walkin.kicker")}>
      <form className="walkIn" onSubmit={(e) => submit(e, false)}>
        <section className="panel wiCustomer">
          <h2>{t("walkin.customer")}</h2>
          {selected ? (
            <div className="selectedCustomer">
              <UserRound aria-hidden />
              <span>
                <b>{selected.name}</b>
                <small>
                  {selected.phone} ·{" "}
                  {t("ops.newOrder.known", { count: selected.orders })}
                </small>
              </span>
              <button
                type="button"
                className="iconBtn"
                aria-label={t("walkin.changeCustomer")}
                onClick={() => setSelected(null)}
              >
                <X />
              </button>
            </div>
          ) : (
            <>
              <input
                ref={searchRef}
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t("walkin.searchPlaceholder")}
                aria-label={t("walkin.searchPlaceholder")}
                autoComplete="off"
              />
              {matches.length > 0 && (
                <ul className="matches" aria-label={t("walkin.matches")}>
                  {matches.map((m) => (
                    <li key={m.id}>
                      <button
                        type="button"
                        onClick={() => {
                          setSelected(m);
                          setQuery("");
                        }}
                      >
                        <b>{m.name}</b> <small>{m.phone}</small>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {phoneTyped && !matches.length && (
                <label className="newCustomerName">
                  {t("walkin.newCustomerName")}
                  <input
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    required
                    minLength={2}
                  />
                </label>
              )}
              <p className="muted small">
                {phoneTyped
                  ? t("walkin.willSave")
                  : guestName
                    ? t("walkin.guestNamed", { name: guestName })
                    : t("walkin.guest")}
              </p>
            </>
          )}
          <div
            className="segmented small"
            role="group"
            aria-label={t("biz.col.source")}
          >
            {(["WALK_IN", "PHONE", "WHATSAPP"] as const).map((s) => (
              <button
                type="button"
                key={s}
                className={source === s ? "on" : ""}
                aria-pressed={source === s}
                onClick={() => setSource(s)}
              >
                {t(`biz.source.${s}`)}
              </button>
            ))}
          </div>
        </section>

        <section className="panel wiServices">
          <h2>{t("biz.nav.services")}</h2>
          {!services.length && <p className="muted">{t("common.loading")}</p>}
          {groups.map(([category, list]) => (
            <div key={category} className="tileGroup">
              <h3>{category}</h3>
              <div className="tiles">
                {list.map((s) => {
                  const n = qty[s.id] ?? 0;
                  return (
                    <div key={s.id} className={`tile ${n ? "on" : ""}`}>
                      <button
                        type="button"
                        className="tileMain"
                        onClick={() => add(s, stepOf(s))}
                        aria-label={t("store.add", { name: s.name })}
                      >
                        <b>{s.name}</b>
                        <small>
                          {money(s.price)}
                          {t(`walkin.unit.${s.pricing_model}`)}
                        </small>
                        {n > 0 && (
                          <em>
                            {s.pricing_model === "PER_KG" ? `${n} kg` : `×${n}`}
                          </em>
                        )}
                      </button>
                      {n > 0 && (
                        <div className="tileStep">
                          <button
                            type="button"
                            onClick={() => add(s, -stepOf(s))}
                            aria-label={t("store.remove", { name: s.name })}
                          >
                            <Minus />
                          </button>
                          {s.pricing_model === "PER_KG" ? (
                            <input
                              type="number"
                              min={0}
                              step={0.5}
                              value={n}
                              aria-label={t("walkin.kgFor", { name: s.name })}
                              onChange={(e) =>
                                setQty({
                                  ...qty,
                                  [s.id]: Math.max(
                                    0,
                                    Math.round(Number(e.target.value) * 2) / 2,
                                  ),
                                })
                              }
                            />
                          ) : (
                            <b>{n}</b>
                          )}
                          <button
                            type="button"
                            onClick={() => add(s, stepOf(s))}
                            aria-label={t("store.add", { name: s.name })}
                          >
                            <Plus />
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
          {services.length > 0 && (
            <p className="muted small">
              <Link to="/app/services">{t("walkin.editServices")}</Link>
            </p>
          )}
        </section>

        <section className="panel wiDetails">
          <div className="dueRow">
            <span>
              {t("walkin.readyBy")}{" "}
              <b>
                {dateTime(
                  (editDue && due ? new Date(due) : promised).toISOString(),
                )}
              </b>
            </span>
            {!editDue ? (
              <button
                type="button"
                className="textBtn"
                onClick={() => {
                  setDue(localInput(promised));
                  setEditDue(true);
                }}
              >
                {t("ops.detail.changePromise")}
              </button>
            ) : (
              <input
                type="datetime-local"
                value={due}
                min={localInput(new Date())}
                onChange={(e) => setDue(e.target.value)}
                aria-label={t("ops.newOrder.promised")}
              />
            )}
          </div>
          <div className="twoFields">
            <label>
              {t("biz.notes")}
              <input
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                maxLength={500}
                placeholder={t("biz.notesHint")}
              />
            </label>
            <label>
              {t("ops.newOrder.discount")}
              <input
                type="number"
                min={0}
                max={subtotal}
                step={100}
                value={discount || ""}
                onChange={(e) =>
                  setDiscount(Math.max(0, Number(e.target.value) || 0))
                }
              />
            </label>
          </div>
          <h2>{t("ops.newOrder.paidNow")}</h2>
          <div
            className="segmented"
            role="group"
            aria-label={t("ops.newOrder.paidNow")}
          >
            {(["later", "full", "part"] as const).map((m) => (
              <button
                type="button"
                key={m}
                className={payMode === m ? "on" : ""}
                aria-pressed={payMode === m}
                onClick={() => setPayMode(m)}
              >
                {t(`walkin.pay.${m}`)}
              </button>
            ))}
          </div>
          {payMode !== "later" && (
            <div className="payFields">
              <div
                className="segmented small"
                role="group"
                aria-label={t("checkout.payment")}
              >
                {(["CASH", "MOBILE_MONEY"] as const).map((m) => (
                  <button
                    type="button"
                    key={m}
                    className={method === m ? "on" : ""}
                    aria-pressed={method === m}
                    onClick={() => setMethod(m)}
                  >
                    {m === "CASH"
                      ? t("checkout.cash")
                      : t("ops.pay.mobileShort")}
                  </button>
                ))}
              </div>
              {payMode === "part" && (
                <label>
                  {t("walkin.amountNow")}
                  <input
                    type="number"
                    min={100}
                    max={Math.max(total - 1, 100)}
                    step={100}
                    required
                    value={partAmount || ""}
                    onChange={(e) =>
                      setPartAmount(Math.max(0, Number(e.target.value) || 0))
                    }
                  />
                </label>
              )}
              {method === "MOBILE_MONEY" && (
                <label>
                  {t("ops.pay.reference")}
                  <input
                    value={reference}
                    onChange={(e) => setReference(e.target.value)}
                    maxLength={60}
                  />
                </label>
              )}
            </div>
          )}
        </section>

        {error && <Notice>{error}</Notice>}
        <div className="wiBar">
          <div>
            <span>{t("common.total")}</span>
            <b>{money(total)}</b>
            {discount > 0 && (
              <small>
                {t("ops.newOrder.afterDiscount", { amount: money(discount) })}
              </small>
            )}
            {paidNow > 0 && paidNow < total && (
              <small>
                {t("walkin.balanceAfter", { amount: money(total - paidNow) })}
              </small>
            )}
          </div>
          <button
            type="button"
            className="outlineBtn"
            disabled={busy || !subtotal}
            onClick={(e) => submit(e, true)}
          >
            <Printer aria-hidden /> {t("walkin.createPrint")}
          </button>
          <button className="primary" disabled={busy || !subtotal}>
            <Check aria-hidden /> {t("biz.createOrder")}
          </button>
        </div>
      </form>
    </AppFrame>
  );
}

type SlipOrder = {
  id: string;
  order_number: string;
  created_at: string;
  due_at: string | null;
  status: string;
  notes: string;
  subtotal: number;
  discount: number;
  delivery_fee: number;
  total: number;
  amount_paid: number;
  balance: number;
  payment_status: string;
  customer: { name: string; phone: string | null; is_guest: boolean };
  items: {
    name: string;
    pricing_model: string;
    unit_price: number;
    quantity: number;
    line_total: number;
  }[];
  payments: { method: string; amount: number; paid_at: string }[];
};

/** Customer order slip / receipt. Sized for 80 mm receipt printers and plain A4 alike. */
export function OrderSlip() {
  const { id = "" } = useParams();
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const { profile } = useProfile();
  const [o, setO] = useState<SlipOrder | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api<SlipOrder>(`/api/v1/business/orders/${id}`, { auth: "business" })
      .then(setO)
      .catch((e) => setError(errorMessage(e)));
  }, [id]);
  useEffect(() => {
    if (o && profile && params.get("print") === "1")
      setTimeout(() => window.print(), 300);
  }, [o, profile]);

  return (
    <AppFrame
      title={t("walkin.slip")}
      action={
        <div className="reportActions noPrint">
          <Link className="outlineBtn" to={`/app/orders/${id}`}>
            <ArrowLeft aria-hidden /> {t("walkin.backToOrder")}
          </Link>
          <button
            className="primary"
            onClick={() => window.print()}
            disabled={!o}
          >
            <Printer aria-hidden /> {t("ops.reports.print")}
          </button>
        </div>
      }
    >
      {error && <Notice>{error}</Notice>}
      {o && (
        <div className="slip" aria-label={t("walkin.slip")}>
          <div className="slipHead">
            <b>{profile?.name}</b>
            <span>
              {[profile?.address, profile?.area].filter(Boolean).join(", ")}
            </span>
            <span>{profile?.phone}</span>
          </div>
          <div className="slipNumber">
            <small>{t("walkin.orderNo")}</small>
            <strong>{o.order_number}</strong>
          </div>
          <dl>
            <div>
              <dt>{t("walkin.date")}</dt>
              <dd>{dateTime(o.created_at)}</dd>
            </div>
            <div>
              <dt>{t("biz.col.customer")}</dt>
              <dd>
                {o.customer.name}
                {o.customer.phone && <small> {o.customer.phone}</small>}
              </dd>
            </div>
            {o.due_at && (
              <div className="ready">
                <dt>{t("walkin.readyBy")}</dt>
                <dd>{dateTime(o.due_at)}</dd>
              </div>
            )}
          </dl>
          <table>
            <tbody>
              {o.items.map((i) => (
                <tr key={i.name}>
                  <td>
                    {i.pricing_model === "PER_KG"
                      ? `${i.quantity} kg`
                      : `${i.quantity}×`}{" "}
                    {i.name}
                    <small> @ {money(i.unit_price)}</small>
                  </td>
                  <td>{money(i.line_total)}</td>
                </tr>
              ))}
              {o.discount > 0 && (
                <tr>
                  <td>{t("ops.newOrder.discount")}</td>
                  <td>−{money(o.discount)}</td>
                </tr>
              )}
              <tr className="total">
                <td>{t("common.total")}</td>
                <td>{money(o.total)}</td>
              </tr>
              {o.payments.map((p, n) => (
                <tr key={n}>
                  <td>
                    {t("walkin.paid")} ·{" "}
                    {p.method === "CASH"
                      ? t("checkout.cash")
                      : t("ops.pay.mobileShort")}
                  </td>
                  <td>{money(p.amount)}</td>
                </tr>
              ))}
              <tr className="balance">
                <td>
                  {o.balance > 0
                    ? t("walkin.balanceDue")
                    : t("walkin.fullyPaid")}
                </td>
                <td>{money(o.balance)}</td>
              </tr>
            </tbody>
          </table>
          {o.notes && <p>“{o.notes}”</p>}
          <p className="slipFoot">{t("walkin.slipFooter")}</p>
        </div>
      )}
    </AppFrame>
  );
}
