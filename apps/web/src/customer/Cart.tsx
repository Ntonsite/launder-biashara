import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight, Minus, Plus, ShoppingBag, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import { cart, useCart } from "../lib/cart";
import { errorMessage, money } from "../lib/format";
import { EmptyState, Notice } from "./ui";
import type { Quote } from "./types";

export default function CartPage() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const current = useCart();
  const changes: {
    type: string;
    name: string;
    old_price?: number;
    new_price?: number;
  }[] = useLocation().state?.changes ?? [];
  const [quote, setQuote] = useState<Quote | null>(null);
  const [error, setError] = useState("");

  // Re-price against the server whenever the cart changes; the server is the source of truth for money.
  useEffect(() => {
    if (!current) return;
    const controller = new AbortController();
    const items = current.lines.map((l) => ({
      service_id: l.serviceId,
      quantity: l.quantity,
    }));
    api<Quote>(`/api/v1/marketplace/laundries/${current.laundrySlug}/quote`, {
      body: { items },
      signal: controller.signal,
    })
      .then((q) => {
        setQuote(q);
        setError("");
        // Keep display prices honest: if the laundry changed a price, show the new one.
        const changed = current.lines.some((l) => {
          const line = q.items.find((x) => x.service_id === l.serviceId);
          return !line || line.unit_price !== l.unitPrice;
        });
        if (changed) {
          setError(t("errors.PRICE_CHANGED"));
          cart.replace({
            ...current,
            lines: current.lines
              .filter((l) => q.items.some((x) => x.service_id === l.serviceId))
              .map((l) => ({
                ...l,
                unitPrice: q.items.find((x) => x.service_id === l.serviceId)!
                  .unit_price,
              })),
          });
        }
      })
      .catch((err) => err.name !== "AbortError" && setError(errorMessage(err)));
    return () => controller.abort();
  }, [JSON.stringify(current)]);

  if (!current)
    return (
      <main className="checkout narrow">
        <EmptyState
          icon={<ShoppingBag />}
          title={t("cart.emptyTitle")}
          body={t("cart.emptyBody")}
          action={
            <Link className="primary" to="/laundries">
              {t("nav.find")}
            </Link>
          }
        />
      </main>
    );

  const step = (model: string) => (model === "PER_KG" ? 0.5 : 1);
  return (
    <main className="checkout narrow">
      <p className="kicker">{current.laundryName}</p>
      <h1>{t("cart.title")}</h1>
      {changes.length > 0 && (
        <Notice kind="info">
          <b>{t("cart.reorderChanges")}</b>
          <ul>
            {changes.map((c) => (
              <li key={c.name + c.type}>
                {c.type === "UNAVAILABLE"
                  ? t("cart.nowUnavailable", { name: c.name })
                  : t("cart.priceNow", {
                      name: c.name,
                      old: money(c.old_price!),
                      now: money(c.new_price!),
                    })}
              </li>
            ))}
          </ul>
        </Notice>
      )}
      {error && <Notice kind="info">{error}</Notice>}
      <section className="panel">
        {current.lines.map((l) => (
          <div className="cartLine" key={l.serviceId}>
            <div>
              <b>{l.name}</b>
              <small>
                {money(l.unitPrice)}
                {l.pricingModel === "PER_KG" && t("common.perKg")}
              </small>
            </div>
            <div className="counter">
              <button
                aria-label={t("store.remove", { name: l.name })}
                onClick={() =>
                  cart.setQuantity(
                    {
                      slug: current.laundrySlug,
                      name: current.laundryName,
                      pickup_enabled: current.pickupEnabled,
                    },
                    l,
                    l.quantity - step(l.pricingModel),
                  )
                }
              >
                <Minus />
              </button>
              <b>
                {l.pricingModel === "PER_KG" ? `${l.quantity} kg` : l.quantity}
              </b>
              <button
                aria-label={t("store.add", { name: l.name })}
                onClick={() =>
                  cart.setQuantity(
                    {
                      slug: current.laundrySlug,
                      name: current.laundryName,
                      pickup_enabled: current.pickupEnabled,
                    },
                    l,
                    l.quantity + step(l.pricingModel),
                  )
                }
              >
                <Plus />
              </button>
            </div>
            <strong>{money(Math.round(l.unitPrice * l.quantity))}</strong>
            <button
              className="iconBtn"
              aria-label={t("cart.removeLine", { name: l.name })}
              onClick={() =>
                cart.setQuantity(
                  {
                    slug: current.laundrySlug,
                    name: current.laundryName,
                    pickup_enabled: current.pickupEnabled,
                  },
                  l,
                  0,
                )
              }
            >
              <Trash2 />
            </button>
          </div>
        ))}
        <div className="spread totalRow">
          <span>{t("cart.subtotal")}</span>
          <strong>{quote ? money(quote.subtotal) : "…"}</strong>
        </div>
        <p className="muted small">{t("cart.feesLater")}</p>
        <button
          className="primary full"
          disabled={!quote}
          onClick={() => nav("/checkout")}
        >
          {t("common.continue")} <ArrowRight />
        </button>
      </section>
      <Link className="textLink" to={`/laundries/${current.laundrySlug}`}>
        {t("cart.addMore")}
      </Link>
    </main>
  );
}
