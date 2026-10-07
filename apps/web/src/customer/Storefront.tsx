import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowRight,
  Clock3,
  MapPin,
  Minus,
  Plus,
  Star,
  Store,
  Truck,
} from "lucide-react";
import { api, ApiError, mediaUrl } from "../lib/api";
import { cart, cartTotals, useCart } from "../lib/cart";
import { errorMessage, money } from "../lib/format";
import { usePlace } from "../lib/location";
import { EmptyState, Notice } from "./ui";
import type { ServiceData, Storefront as StoreData } from "./types";

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

export default function Storefront() {
  const { slug = "" } = useParams();
  const { t } = useTranslation();
  const nav = useNavigate();
  const { place } = usePlace();
  const current = useCart();
  const [store, setStore] = useState<StoreData | null>(null);
  const [error, setError] = useState<{
    notFound: boolean;
    message: string;
  } | null>(null);

  useEffect(() => {
    const search = place ? `?lat=${place.lat}&lng=${place.lng}` : "";
    setStore(null);
    api<StoreData>(`/api/v1/marketplace/laundries/${slug}${search}`)
      .then(setStore)
      .catch((err) =>
        setError({
          notFound: err instanceof ApiError && err.status === 404,
          message: errorMessage(err),
        }),
      );
  }, [slug, place?.lat, place?.lng]);

  if (error)
    return (
      <main className="storePage">
        {error.notFound ? (
          <EmptyState
            icon={<Store />}
            title={t("store.unavailableTitle")}
            body={t("store.unavailableBody")}
            action={
              <Link className="primary" to="/laundries">
                {t("nav.find")}
              </Link>
            }
          />
        ) : (
          <Notice>{error.message}</Notice>
        )}
      </main>
    );
  if (!store)
    return (
      <main className="storePage" aria-busy="true">
        <div className="storeCover shimmer" />
        <div className="shimmer line w40" style={{ marginTop: 24 }} />
        <div className="shimmer line w60" />
      </main>
    );

  const inCart = current?.laundrySlug === store.slug ? current : null;
  const qty = (id: string) =>
    inCart?.lines.find((l) => l.serviceId === id)?.quantity ?? 0;
  const totals = cartTotals(inCart);

  function change(s: ServiceData, delta: number) {
    if (
      current &&
      current.laundrySlug !== store!.slug &&
      !window.confirm(t("store.replaceCart", { name: current.laundryName }))
    )
      return;
    const step = s.pricing_model === "PER_KG" ? 0.5 : 1;
    const start =
      s.pricing_model === "PER_KG" && qty(s.id) === 0 && delta > 0
        ? 2
        : qty(s.id) + delta * step;
    cart.setQuantity(
      store!,
      {
        serviceId: s.id,
        name: s.name,
        pricingModel: s.pricing_model,
        unitPrice: s.price,
      },
      Math.max(0, start),
    );
  }

  return (
    <main className="storePage">
      <section className="storeCover">
        {store.cover_image_url && (
          <img src={mediaUrl(store.cover_image_url)} alt="" />
        )}
      </section>
      <section className="storeIntro">
        <div>
          <h1>{store.name}</h1>
          <p className="storeMeta">
            {store.review_count > 0 && (
              <span className="rating">
                <Star /> {store.rating.toFixed(1)}{" "}
                <small>
                  ({t("store.reviews", { count: store.review_count })})
                </small>
              </span>
            )}
            <span>
              <MapPin /> {store.area}
              {store.distance_km != null &&
                ` · ${t("common.km", { km: store.distance_km.toFixed(1) })}`}
            </span>
            <span className={store.open_now ? "openText" : "closedText"}>
              <Clock3 />
              {store.open_now
                ? t("store.openUntil", { time: store.today?.closes_at })
                : store.today && !store.today.closed
                  ? t("store.opensAt", { time: store.today.opens_at })
                  : t("common.closed")}
            </span>
          </p>
          {store.description && (
            <p className="storeDescription">{store.description}</p>
          )}
        </div>
        <ul className="storeFacts">
          <li>
            <Truck />{" "}
            {store.pickup_enabled
              ? t("store.pickupFee", { fee: money(store.pickup_fee) })
              : t("store.dropOffOnly")}
          </li>
          {store.fastest_turnaround_hours && (
            <li>
              <Clock3 />{" "}
              {t("store.turnaroundFrom", {
                hours: store.fastest_turnaround_hours,
              })}
            </li>
          )}
        </ul>
      </section>

      <div className="storeGrid">
        <section>
          {store.service_groups.map((group) => (
            <div className="serviceGroup" key={group.category}>
              <h2>
                {t(`categories.${group.category}`, {
                  defaultValue: group.category,
                })}
              </h2>
              {group.services.map((s) => (
                <div className="serviceLine" key={s.id}>
                  <div>
                    {/* Service names are the laundry's own words and are never translated. */}
                    <h3>{s.name}</h3>
                    {s.description && <p>{s.description}</p>}
                    <b>
                      {money(s.price)}
                      {s.pricing_model === "PER_KG" && t("common.perKg")}
                    </b>
                  </div>
                  <div className="counter">
                    {qty(s.id) > 0 && (
                      <>
                        <button
                          aria-label={t("store.remove", { name: s.name })}
                          onClick={() => change(s, -1)}
                        >
                          <Minus />
                        </button>
                        <b aria-live="polite">
                          {s.pricing_model === "PER_KG"
                            ? `${qty(s.id)} kg`
                            : qty(s.id)}
                        </b>
                      </>
                    )}
                    <button
                      aria-label={t("store.add", { name: s.name })}
                      onClick={() => change(s, 1)}
                    >
                      <Plus />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ))}

          {store.reviews.length > 0 && (
            <div className="serviceGroup">
              <h2>{t("store.reviewsTitle")}</h2>
              {store.reviews.map((r) => (
                <blockquote className="review" key={r.id}>
                  <span className="rating">
                    <Star /> {r.rating}
                  </span>
                  {/* Reviews are shown in the language they were written in. */}
                  {r.comment && <p>{r.comment}</p>}
                  <cite>{r.author}</cite>
                </blockquote>
              ))}
            </div>
          )}
        </section>

        <aside className="cart">
          <h2>{t("store.hours")}</h2>
          <dl className="hours">
            {store.hours.map((h) => (
              <div key={h.weekday}>
                <dt>{t(`days.${DAYS[h.weekday]}`)}</dt>
                <dd>
                  {h.closed
                    ? t("common.closed")
                    : `${h.opens_at} – ${h.closes_at}`}
                </dd>
              </div>
            ))}
          </dl>
          {store.address && (
            <p className="muted">
              <MapPin /> {store.address}
            </p>
          )}
        </aside>
      </div>

      {totals.count > 0 && (
        <div className="stickyCart">
          <span>
            {t("cart.summary", { count: totals.count })} ·{" "}
            <b>{money(totals.subtotal)}</b>
          </span>
          <button className="primary" onClick={() => nav("/cart")}>
            {t("cart.view")} <ArrowRight />
          </button>
        </div>
      )}
    </main>
  );
}
