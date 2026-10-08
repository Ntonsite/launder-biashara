import i18n from "../i18n";
import { ApiError } from "./api";

const locale = () => (i18n.language === "sw" ? "sw-TZ" : "en-TZ");

export const money = (n: number) =>
  `TZS ${new Intl.NumberFormat(locale(), { maximumFractionDigits: 0 }).format(n)}`;

export const dateTime = (iso?: string | null) =>
  iso
    ? new Intl.DateTimeFormat(locale(), {
        weekday: "short",
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(iso))
    : "";

export const date = (iso?: string | null) =>
  iso
    ? new Intl.DateTimeFormat(locale(), {
        day: "numeric",
        month: "short",
        year: "numeric",
      }).format(new Date(iso))
    : "";

export const time = (iso?: string | null) =>
  iso
    ? new Intl.DateTimeFormat(locale(), {
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(iso))
    : "";

export const statusLabel = (status: string) =>
  i18n.t(`status.${status}`, { defaultValue: status.replaceAll("_", " ") });

/** Human message for an API failure. Known codes are translated; anything else falls back to a calm generic line. */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const key = `errors.${err.code}`;
    if (i18n.exists(key)) return i18n.t(key);
    if (err.status === 0) return i18n.t("errors.NETWORK");
    if (err.status >= 500) return i18n.t("errors.SERVER");
    return err.message;
  }
  return i18n.t("errors.SERVER");
}

export const quantityLabel = (qty: number, model: string) =>
  model === "PER_KG" ? `${qty} kg` : `${qty}×`;

/** Compact money for cards and chart labels: TZS 4.8M, TZS 185K. Full amounts stay in tables and reports. */
export const moneyShort = (n: number) => {
  const abs = Math.abs(n);
  if (abs >= 1_000_000)
    return `TZS ${new Intl.NumberFormat(locale(), { maximumFractionDigits: 1 }).format(n / 1_000_000)}M`;
  if (abs >= 10_000)
    return `TZS ${new Intl.NumberFormat(locale(), { maximumFractionDigits: 0 }).format(n / 1000)}K`;
  return money(n);
};

export const percent = (n: number | null | undefined) =>
  n == null
    ? "—"
    : `${new Intl.NumberFormat(locale(), { maximumFractionDigits: 1 }).format(n)}%`;

export const weekdayName = (index: number, style: "long" | "short" = "long") =>
  // 2024-01-01 was a Monday; index 0 = Monday, as the API sends it.
  new Intl.DateTimeFormat(locale(), { weekday: style, timeZone: "UTC" }).format(
    new Date(Date.UTC(2024, 0, 1 + index)),
  );

export const longDate = (d: Date | string) =>
  new Intl.DateTimeFormat(locale(), {
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(typeof d === "string" ? new Date(`${d}T12:00:00`) : d);

export const dayMonth = (iso: string) =>
  new Intl.DateTimeFormat(locale(), { day: "numeric", month: "short" }).format(
    new Date(`${iso}T12:00:00`),
  );

/** Items as staff say them: "5× Shirt, 2 kg Wash & Fold". */
export const itemsSummary = (
  items: { name: string; quantity: number; pricing_model: string }[],
) =>
  items
    .map((i) =>
      i.pricing_model === "PER_KG"
        ? `${i.quantity} kg ${i.name}`
        : `${i.quantity}× ${i.name}`,
    )
    .join(", ");

export type Polarity = "up" | "down" | "neutral";

/** Whether a change is good news. Outstanding money or late orders going up is not. */
export function trendTone(
  change: number | null | undefined,
  goodWhen: Polarity,
): "good" | "bad" | "flat" | "none" {
  if (change == null) return "none";
  if (Math.abs(change) < 1 || goodWhen === "neutral") return "flat";
  return change > 0 === (goodWhen === "up") ? "good" : "bad";
}
