import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Check, RotateCcw, Star } from "lucide-react";
import { api } from "../lib/api";
import { dateTime, errorMessage, money, statusLabel } from "../lib/format";
import { useSession } from "../lib/useSession";
import { reorder } from "./reorder";
import SignIn from "./SignIn";
import { Notice, StatusPill } from "./ui";
import type { OrderDetail } from "./types";

const POLL_MS = 20000;

export default function Tracking() {
  const { id = "" } = useParams();
  const [params] = useSearchParams();
  const { t } = useTranslation();
  const nav = useNavigate();
  const session = useSession("customer");
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  const load = useCallback(() => {
    api<OrderDetail>(`/api/v1/customer/orders/${id}`, { auth: "customer" })
      .then((o) => {
        setOrder(o);
        setError("");
      })
      .catch((err) => setError(errorMessage(err)));
  }, [id]);

  useEffect(() => {
    if (!session) return;
    load();
  }, [load, session?.user.id]);

  // Gentle polling only while the order is moving and the tab is visible.
  useEffect(() => {
    if (!order || ["COMPLETED", "CANCELLED", "REJECTED"].includes(order.status))
      return;
    const timer = setInterval(
      () => document.visibilityState === "visible" && load(),
      POLL_MS,
    );
    return () => clearInterval(timer);
  }, [order?.status, load]);

  async function act(fn: () => Promise<unknown>, message?: string) {
    setBusy(true);
    setError("");
    try {
      await fn();
      if (message) setNotice(message);
      load();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (!session?.user.name)
    return (
      <main className="checkout narrow">
        <SignIn onDone={load} />
      </main>
    );
  if (!order)
    return (
      <main className="tracking">
        {error ? (
          <Notice>{error}</Notice>
        ) : (
          <div className="trackCard">
            <div className="shimmer line w60" />
            <div className="shimmer line w80" />
          </div>
        )}
      </main>
    );

  const reached = new Set(order.events.map((e) => e.status));
  const currentIndex = order.stages.indexOf(order.status);
  const closed = order.status === "CANCELLED" || order.status === "REJECTED";
  const eventAt = (s: string) => order.events.find((e) => e.status === s)?.at;

  async function submitReview(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    await act(
      () =>
        api(`/api/v1/customer/orders/${order!.id}/review`, {
          auth: "customer",
          body: {
            rating: Number(fd.get("rating")),
            comment: String(fd.get("comment") || ""),
          },
        }),
      t("track.reviewThanks"),
    );
  }

  async function orderAgain() {
    setBusy(true);
    try {
      const r = await reorder(order!.id);
      if (!r.quote) {
        setError(t("track.reorderNothing"));
        return;
      }
      nav("/cart", { state: { changes: r.changes } });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="tracking">
      {params.get("placed") && (
        <div className="placed">
          <div className="successIcon">
            <Check />
          </div>
          <h1>{t("checkout.success")}</h1>
          <p>{t("checkout.successText")}</p>
        </div>
      )}
      {error && <Notice>{error}</Notice>}
      {notice && <Notice kind="info">{notice}</Notice>}

      <section className="trackCard">
        <div className="spread">
          <div>
            <small className="muted">
              {order.order_number} · {order.laundry.name}
            </small>
            <h2>
              {closed
                ? statusLabel(order.status)
                : t(`track.headline.${order.status}`, {
                    defaultValue: statusLabel(order.status),
                  })}
            </h2>
          </div>
          <StatusPill status={order.status} />
        </div>
        {closed ? (
          order.cancel_reason && <p className="muted">{order.cancel_reason}</p>
        ) : (
          <ol className="vtimeline">
            {order.stages.map((s, i) => {
              const done = reached.has(s) && i < currentIndex;
              const now = i === currentIndex;
              const skipped = i < currentIndex && !reached.has(s);
              if (skipped) return null; // stages the laundry legitimately skipped (e.g. no drying) are hidden
              return (
                <li key={s} className={done ? "done" : now ? "now" : ""}>
                  <i aria-hidden="true">{done ? <Check /> : null}</i>
                  <div>
                    <b>{statusLabel(s)}</b>
                    {now && (
                      <span>
                        {t(`track.detail.${s}`, { defaultValue: "" })}
                      </span>
                    )}
                    {(done || now) && eventAt(s) && (
                      <small>{dateTime(eventAt(s))}</small>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </section>

      <section className="trackCard">
        <h3>{t("track.summary")}</h3>
        {order.items.map((i) => (
          <div className="spread" key={i.name}>
            <span>
              {i.pricing_model === "PER_KG"
                ? `${i.quantity} kg`
                : `${i.quantity} ×`}{" "}
              {i.name}
            </span>
            <span>{money(i.line_total)}</span>
          </div>
        ))}
        {order.delivery_fee > 0 && (
          <div className="spread">
            <span>{t("checkout.pickupFee")}</span>
            <span>{money(order.delivery_fee)}</span>
          </div>
        )}
        <div className="spread totalRow">
          <b>{t("common.total")}</b>
          <strong>{money(order.total)}</strong>
        </div>
        {order.pickup_window_start && (
          <p className="muted">
            {t("checkout.pickup")}: {dateTime(order.pickup_window_start)} ·{" "}
            {order.pickup_address}
          </p>
        )}
        <p className="muted">
          {t("checkout.payment")}:{" "}
          {order.payment_method === "CASH"
            ? t("checkout.cash")
            : t("checkout.mobile")}{" "}
          · {t(`payment.${order.payment_status}`)}
          {order.payment?.failure_reason &&
            order.payment.status === "FAILED" &&
            ` — ${order.payment.failure_reason}`}
        </p>

        <div className="actions">
          {order.can_pay && (
            <button
              className="primary"
              disabled={busy}
              onClick={() =>
                act(
                  () =>
                    api(
                      `/api/v1/customer/orders/${order.id}/payments/mobile-money`,
                      { auth: "customer", body: { phone: session.user.phone } },
                    ),
                  t("track.payPrompt"),
                )
              }
            >
              {t("track.payNow", { amount: money(order.total) })}
            </button>
          )}
          {order.can_confirm && (
            <button
              className="primary"
              disabled={busy}
              onClick={() =>
                act(() =>
                  api(`/api/v1/customer/orders/${order.id}/confirm`, {
                    auth: "customer",
                    method: "POST",
                  }),
                )
              }
            >
              {t("track.confirm")}
            </button>
          )}
          {order.can_cancel && (
            <button
              className="outlineBtn"
              disabled={busy}
              onClick={() =>
                window.confirm(t("track.cancelConfirm")) &&
                act(() =>
                  api(`/api/v1/customer/orders/${order.id}/cancel`, {
                    auth: "customer",
                    body: {},
                  }),
                )
              }
            >
              {t("track.cancel")}
            </button>
          )}
          {["COMPLETED", "DELIVERED", "CANCELLED", "REJECTED"].includes(
            order.status,
          ) && (
            <button className="outlineBtn" disabled={busy} onClick={orderAgain}>
              <RotateCcw /> {t("orders.reorder")}
            </button>
          )}
        </div>
      </section>

      {order.can_review && (
        <form className="trackCard" onSubmit={submitReview}>
          <h3>{t("track.reviewTitle", { name: order.laundry.name })}</h3>
          <fieldset className="stars">
            <legend className="sr-only">{t("track.rating")}</legend>
            {[5, 4, 3, 2, 1].map((n) => (
              <label key={n}>
                <input
                  type="radio"
                  name="rating"
                  value={n}
                  required
                  defaultChecked={n === 5}
                />
                <Star aria-hidden="true" />
                <span className="sr-only">
                  {t("track.stars", { count: n })}
                </span>
              </label>
            ))}
          </fieldset>
          <textarea
            name="comment"
            maxLength={1000}
            placeholder={t("track.reviewHint")}
            aria-label={t("track.reviewHint")}
          />
          <button className="primary" disabled={busy}>
            {t("track.submitReview")}
          </button>
        </form>
      )}
      {order.review && (
        <p className="muted">
          {t("track.yourReview")}: {"★".repeat(order.review.rating)}{" "}
          {order.review.comment}
        </p>
      )}
      <Link className="textLink" to="/account">
        {t("orders.title")}
      </Link>
    </main>
  );
}
