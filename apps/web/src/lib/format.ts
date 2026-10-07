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
