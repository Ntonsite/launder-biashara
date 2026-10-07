import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { MapPin, Star, Truck } from "lucide-react";
import { mediaUrl } from "../lib/api";
import { money, statusLabel } from "../lib/format";
import type { LaundryCardData } from "./types";

export function LaundryCard({ l }: { l: LaundryCardData }) {
  const { t } = useTranslation();
  return (
    <Link to={`/laundries/${l.slug}`} className="laundryCard">
      <div className="photo">
        {l.cover_thumb_url ? (
          <img src={mediaUrl(l.cover_thumb_url)} alt="" loading="lazy" />
        ) : (
          <span>{l.name.slice(0, 2)}</span>
        )}
        <label className={l.open_now ? "" : "closedTag"}>
          <span className="dot" />
          {l.open_now ? t("common.open") : t("common.closed")}
        </label>
      </div>
      <div className="cardBody">
        <div className="spread">
          <h3>{l.name}</h3>
          {l.review_count > 0 && (
            <strong
              className="rating"
              aria-label={t("store.ratingLabel", {
                rating: l.rating.toFixed(1),
              })}
            >
              <Star /> {l.rating.toFixed(1)}
            </strong>
          )}
        </div>
        <p>
          <MapPin /> {l.area}
          {l.distance_km != null &&
            ` · ${t("common.km", { km: l.distance_km.toFixed(1) })}`}
        </p>
        <div className="spread cardFoot">
          <p>
            {l.starting_price && (
              <>
                {t("common.from")}&nbsp;<b>{money(l.starting_price.amount)}</b>
                {l.starting_price.unit === "PER_KG" && t("common.perKg")}
              </>
            )}
          </p>
          {l.pickup_available && (
            <span className="miniBadge">
              <Truck /> {t("common.pickup")}
            </span>
          )}
        </div>
      </div>
    </Link>
  );
}

export function CardSkeletons({ count = 3 }: { count?: number }) {
  return (
    <div className="cards" aria-busy="true">
      {Array.from({ length: count }, (_, i) => (
        <div className="laundryCard skeletonCard" key={i}>
          <div className="photo shimmer" />
          <div className="cardBody">
            <div className="shimmer line w60" />
            <div className="shimmer line w40" />
            <div className="shimmer line w80" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  body,
  action,
}: {
  icon: React.ReactNode;
  title: string;
  body?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="emptyState">
      <div className="emptyIcon">{icon}</div>
      <h3>{title}</h3>
      {body && <p>{body}</p>}
      {action}
    </div>
  );
}

export function StatusPill({ status }: { status: string }) {
  return (
    <span className={`pill ${status.toLowerCase()}`}>
      {statusLabel(status)}
    </span>
  );
}

export function Notice({
  kind = "error",
  children,
}: {
  kind?: "error" | "info";
  children: React.ReactNode;
}) {
  return (
    <div
      className={`notice ${kind}`}
      role={kind === "error" ? "alert" : "status"}
    >
      {children}
    </div>
  );
}
