import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowDownRight, ArrowRight, ArrowUpRight, Minus } from "lucide-react";
import { percent, trendTone, type Polarity } from "../lib/format";
import { useProfile } from "./shell";
import type { Metric, PeriodInfo } from "./types";

/** Capabilities from the API (profile). Navigation only; the API enforces every one of them. */
export function useCan() {
  const { profile } = useProfile();
  const caps = new Set(profile?.capabilities ?? []);
  return (capability: string) => caps.has(capability);
}

/** "↑ 12% vs same days last month", coloured by whether the change is good news for this metric. */
export function Delta({
  metric,
  goodWhen = "up",
  compareTo,
  inProgress,
}: {
  metric: Metric;
  goodWhen?: Polarity;
  compareTo?: PeriodInfo["compare_to"];
  inProgress?: boolean;
}) {
  const { t } = useTranslation();
  const tone = trendTone(metric.change_pct, goodWhen);
  if (tone === "none") return null;
  const Icon =
    tone === "flat"
      ? Minus
      : (metric.change_pct ?? 0) > 0
        ? ArrowUpRight
        : ArrowDownRight;
  const against = compareTo
    ? t(`ops.compare.${compareTo}${inProgress ? "_partial" : ""}`)
    : "";
  return (
    <span className={`delta ${tone}`}>
      <Icon aria-hidden />
      {tone === "flat"
        ? t("ops.compare.same")
        : percent(Math.abs(metric.change_pct ?? 0))}
      {against && <small> {against}</small>}
    </span>
  );
}

export function StatCard({
  label,
  value,
  sub,
  metric,
  goodWhen,
  compareTo,
  inProgress,
  to,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  metric?: Metric;
  goodWhen?: Polarity;
  compareTo?: PeriodInfo["compare_to"];
  inProgress?: boolean;
  to?: string;
  tone?: "alert";
}) {
  const body = (
    <>
      <p>{label}</p>
      <strong>{value}</strong>
      {metric && (
        <Delta
          metric={metric}
          goodWhen={goodWhen}
          compareTo={compareTo}
          inProgress={inProgress}
        />
      )}
      {sub && <small>{sub}</small>}
      {to && <ArrowRight className="statGo" aria-hidden />}
    </>
  );
  const cls = `stat ${tone === "alert" ? "alert" : ""}`;
  return to ? (
    <Link className={cls} to={to}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

/** Bar chart for daily series. Readable at phone width: no axis clutter, first/last labels, values on hover. */
export function Bars({
  points,
  label,
  valueLabel,
}: {
  points: { key: string; label: string; value: number; muted?: boolean }[];
  label: string;
  valueLabel: (v: number) => string;
}) {
  const max = Math.max(1, ...points.map((p) => p.value));
  const w = 12;
  return (
    <figure className="opsBars">
      <svg
        viewBox={`0 0 ${points.length * w} 100`}
        preserveAspectRatio="none"
        role="img"
        aria-label={label}
      >
        {points.map((p, i) => {
          const h = Math.max(p.value > 0 ? 2 : 0, (p.value / max) * 96);
          return (
            <rect
              key={p.key}
              x={i * w + 1.5}
              y={100 - h}
              width={w - 3}
              height={h}
              rx={1.5}
              className={p.muted ? "muted" : ""}
            >
              <title>{`${p.label}: ${valueLabel(p.value)}`}</title>
            </rect>
          );
        })}
      </svg>
      {points.length > 1 && (
        <figcaption>
          <span>{points[0].label}</span>
          {points.length > 7 && (
            <span>{points[Math.floor(points.length / 2)].label}</span>
          )}
          <span>{points[points.length - 1].label}</span>
        </figcaption>
      )}
      <table className="sr-only">
        <caption>{label}</caption>
        <tbody>
          {points.map((p) => (
            <tr key={p.key}>
              <th>{p.label}</th>
              <td>{valueLabel(p.value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

export function ShareBar({ share }: { share: number | null }) {
  return (
    <span className="shareBar" aria-hidden>
      <i style={{ width: `${Math.min(100, share ?? 0)}%` }} />
    </span>
  );
}

export const PERIODS = [
  "today",
  "yesterday",
  "last_7_days",
  "this_week",
  "last_week",
  "this_month",
  "last_month",
  "custom",
] as const;

export type PeriodValue = { period: string; start?: string; end?: string };

export function periodQuery(p: PeriodValue) {
  const q = new URLSearchParams({ period: p.period });
  if (p.period === "custom" && p.start && p.end) {
    q.set("start", p.start);
    q.set("end", p.end);
  }
  return q;
}

export function PeriodPicker({
  value,
  onChange,
  options = PERIODS,
}: {
  value: PeriodValue;
  onChange: (p: PeriodValue) => void;
  options?: readonly string[];
}) {
  const { t } = useTranslation();
  const today = new Date().toISOString().slice(0, 10);
  return (
    <div className="periodPicker">
      <select
        value={value.period}
        aria-label={t("ops.period.label")}
        onChange={(e) =>
          onChange({
            period: e.target.value,
            start: value.start ?? today,
            end: value.end ?? today,
          })
        }
      >
        {options.map((p) => (
          <option key={p} value={p}>
            {t(`ops.period.${p}`)}
          </option>
        ))}
      </select>
      {value.period === "custom" && (
        <>
          <input
            type="date"
            aria-label={t("ops.period.from")}
            value={value.start ?? today}
            max={value.end ?? today}
            onChange={(e) => onChange({ ...value, start: e.target.value })}
          />
          <input
            type="date"
            aria-label={t("ops.period.to")}
            value={value.end ?? today}
            min={value.start}
            onChange={(e) => onChange({ ...value, end: e.target.value })}
          />
        </>
      )}
    </div>
  );
}

export function SectionHead({
  title,
  question,
  action,
}: {
  title: string;
  question?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="sectionHead">
      <div>
        <h2>{title}</h2>
        {question && <p>{question}</p>}
      </div>
      {action}
    </div>
  );
}
