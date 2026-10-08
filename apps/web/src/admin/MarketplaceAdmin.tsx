import { FormEvent, useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Circle, Play, X } from "lucide-react";
import { api } from "../lib/api";
import { date, dateTime, errorMessage, money, percent } from "../lib/format";
import { Notice } from "../customer/ui";

const BASE = "/api/v1/admin/marketplace";
const VIEWS = ["overview", "providers", "trials"] as const;
type View = (typeof VIEWS)[number];
type Say = (kind: "info" | "error", text: string) => void;

const call = <T = any,>(path: string, body?: unknown, method?: string) =>
  api<T>(`${BASE}${path}`, { auth: "admin", body, method });

function useLoad<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const reload = useCallback(() => {
    if (!path) return;
    api<T>(`${BASE}${path}`, { auth: "admin" })
      .then((d) => {
        setData(d);
        setError("");
      })
      .catch((e) => setError(errorMessage(e)));
  }, [path]);
  useEffect(reload, [reload]);
  return { data, error, reload, setData };
}

const pct = (n: number | null | undefined) =>
  n == null ? "—" : `${n % 1 === 0 ? n.toFixed(0) : n.toFixed(2)}%`;
const isFinance = (role: string) =>
  role === "SUPER_ADMIN" || role === "FINANCE_ADMIN";

export function StatusChip({ status }: { status: string }) {
  const { t } = useTranslation();
  return (
    <span className={`status ${status.toLowerCase()}`}>
      {t(`mp.status.${status}`)}
    </span>
  );
}

function Terms({ a }: { a: any | null }) {
  const { t } = useTranslation();
  if (!a) return <span className="muted">—</span>;
  if (a.kind === "STANDARD") return <span>{t("mpa.terms.standard")}</span>;
  if (a.status === "OFFERED" || a.status === "PENDING_START")
    return (
      <span>
        {t("mpa.terms.trialWaiting", {
          days: a.duration_days,
          rate: pct(a.rate),
        })}
      </span>
    );
  return (
    <span className="mpaTerms">
      {t("mpa.terms.trial", { rate: pct(a.rate) })}
      <small>
        {t("mpa.terms.daysLeft", {
          count: a.days_left ?? 0,
          date: date(a.ends_at),
        })}
      </small>
    </span>
  );
}

// ---- console ---------------------------------------------------------------------------------------------------------
export default function MarketplaceAdmin({ role }: { role: string }) {
  const { t } = useTranslation();
  const [view, setView] = useState<View>("overview");
  const [open, setOpen] = useState<string | null>(null);
  const [notice, setNotice] = useState<{
    kind: "info" | "error";
    text: string;
  } | null>(null);
  const say: Say = (kind, text) => setNotice({ kind, text });
  const show = (id: string) => {
    setOpen(id);
    setView("providers");
  };
  return (
    <div className="mon mpa">
      <nav className="viewTabs" aria-label={t("admin.tabs.applications")}>
        {VIEWS.map((x) => (
          <button
            key={x}
            className={view === x ? "on" : ""}
            onClick={() => {
              setView(x);
              setOpen(null);
              setNotice(null);
            }}
          >
            {t(`mpa.views.${x}`)}
          </button>
        ))}
      </nav>
      {notice && <Notice kind={notice.kind}>{notice.text}</Notice>}
      {view === "overview" && <Overview onOpen={show} />}
      {view === "providers" &&
        (open ? (
          <Provider
            id={open}
            role={role}
            say={say}
            onClose={() => setOpen(null)}
          />
        ) : (
          <Providers onOpen={setOpen} />
        ))}
      {view === "trials" && <Trials onOpen={show} />}
    </div>
  );
}

function LaunchBanner({ mode, hint }: { mode: string; hint?: boolean }) {
  const { t } = useTranslation();
  return (
    <div className={`mpaLaunch mode-${mode.toLowerCase()}`}>
      <b>{t(`mpa.mode.${mode}.title`)}</b>
      <span>{t(`mpa.mode.${mode}.body`)}</span>
      {hint && <small>{t("mpa.mode.where")}</small>}
    </div>
  );
}

function Overview({ onOpen }: { onOpen: (id: string) => void }) {
  const { t } = useTranslation();
  const { data } = useLoad<any>("/overview");
  if (!data) return <div className="tableLoading">{t("common.loading")}</div>;
  const cards: [string, string | number][] = [
    ["applications", data.applications_pending],
    ["invited", data.invited],
    ["approved", data.approved],
    ["waiting", data.waiting_to_start],
    ["activeTrials", data.active_trials],
    ["activeProviders", data.active_providers],
    ["expired", data.trial_expired],
    ["suspended", data.suspended],
    [
      "conversion",
      data.conversion_rate == null ? "—" : percent(data.conversion_rate * 100),
    ],
  ];
  const c = data.commission;
  return (
    <>
      <LaunchBanner mode={data.mode} hint />
      <h3>{t("mpa.funnel")}</h3>
      <div className="todayGrid">
        {cards.map(([k, v]) => (
          <div className="stat" key={k}>
            <p>{t(`mpa.kpi.${k}`)}</p>
            <strong>{v}</strong>
          </div>
        ))}
      </div>
      <h3>
        {t("mpa.money", { start: date(data.start), end: date(data.end) })}
      </h3>
      <div className="todayGrid">
        {(
          [
            ["gmv", data.gmv],
            ["commission_net", c.net],
            ["commission_standard", c.standard],
            ["commission_trial", c.trial],
            ["commission_waived", c.waived],
          ] as const
        ).map(([k, v]) => (
          <div className="stat" key={k}>
            <p>{t(`mpa.kpi.${k}`)}</p>
            <strong>{money(v)}</strong>
          </div>
        ))}
      </div>
      <p className="muted small">
        {t("mpa.reconcile", {
          earned: money(c.earned),
          reversed: money(-c.reversed),
          net: money(c.net),
          orders: data.marketplace_orders,
        })}
      </p>
      <section className="panel">
        <h2>{t("mpa.pipeline")}</h2>
        {data.expiring.length === 0 ? (
          <p className="muted">{t("mpa.noExpiring")}</p>
        ) : (
          <ul className="ruleList">
            {data.expiring.map((e: any) => (
              <li className="ruleRow" key={e.business_id}>
                <b>{t("mpa.terms.daysShort", { count: e.days_left })}</b>
                <span>
                  <button
                    className="textBtn"
                    onClick={() => onOpen(e.business_id)}
                  >
                    {e.business_name}
                  </button>
                  <small>{date(e.ends_at)}</small>
                </span>
                <span className={`pill ${e.accepted ? "" : "inv-open"}`}>
                  {e.accepted ? t("mpa.accepted") : t("mpa.notAccepted")}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

const FILTERS = [
  "",
  "PENDING_REVIEW",
  "INVITED",
  "CHANGES_REQUESTED",
  "APPROVED",
  "TRIAL_ACTIVE",
  "ACTIVE",
  "TRIAL_EXPIRED",
  "SUSPENDED",
  "REJECTED",
  "DRAFT",
  "NOT_ENROLLED",
];

function Providers({ onOpen }: { onOpen: (id: string) => void }) {
  const { t } = useTranslation();
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const { data } = useLoad<{ items: any[]; total: number }>(
    `/providers?page_size=100&status=${status}${q ? `&q=${encodeURIComponent(q)}` : ""}`,
  );
  return (
    <section className="panel">
      <div className="monToolbar">
        <select
          aria-label={t("mpa.filter")}
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          {FILTERS.map((s) => (
            <option key={s} value={s}>
              {s ? t(`mp.status.${s}`) : t("mpa.allEnrolled")}
            </option>
          ))}
        </select>
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t("mon.search")}
          aria-label={t("mon.search")}
        />
      </div>
      {!data ? (
        <div className="tableLoading">{t("common.loading")}</div>
      ) : data.items.length === 0 ? (
        <p className="muted">{t("admin.empty")}</p>
      ) : (
        <ul className="mpaList">
          {data.items.map((r) => (
            <li key={r.business_id}>
              <button onClick={() => onOpen(r.business_id)}>
                <span>
                  <b>{r.business_name}</b>
                  <small>
                    {r.area} ·{" "}
                    {t("mpa.readyShort", { done: r.ready, total: r.checks })}
                    {r.launch_cohort ? ` · ${t("mpa.cohort")}` : ""}
                  </small>
                </span>
                <StatusChip status={r.status} />
                <Terms a={r.agreement} />
                <small className="muted">
                  {r.submitted_at
                    ? t("mpa.submitted", { date: date(r.submitted_at) })
                    : r.invited_at
                      ? t("mpa.invitedOn", { date: date(r.invited_at) })
                      : ""}
                </small>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

type Action =
  | "invite"
  | "approve"
  | "request-changes"
  | "reject"
  | "activate"
  | "suspend"
  | "reactivate"
  | "grant"
  | "extend"
  | "end";

const NEEDS_REASON: Action[] = [
  "request-changes",
  "reject",
  "suspend",
  "grant",
  "extend",
  "end",
];

function Provider({
  id,
  role,
  say,
  onClose,
}: {
  id: string;
  role: string;
  say: Say;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const { data: p, setData } = useLoad<any>(`/providers/${id}`);
  const [action, setAction] = useState<Action | null>(null);
  const [busy, setBusy] = useState(false);
  const finance = isFinance(role);
  if (!p) return <div className="tableLoading">{t("common.loading")}</div>;

  const a = p.agreement;
  const trialOpen = a?.kind === "TRIAL";
  const actions: Action[] = [];
  if (
    ["NOT_ENROLLED", "DRAFT", "REJECTED", "CHANGES_REQUESTED"].includes(
      p.review_status,
    )
  )
    actions.push("invite");
  if (p.review_status === "PENDING_REVIEW")
    actions.push("approve", "request-changes", "reject");
  if (p.review_status === "INVITED") actions.push("reject");
  if (p.review_status === "APPROVED") {
    if (p.listing_status === "HIDDEN") actions.push("activate");
    if (p.listing_status === "SUSPENDED") actions.push("reactivate");
    else actions.push("suspend");
    if (finance && trialOpen) actions.push("extend", "end");
    if (finance && !trialOpen) actions.push("grant");
  }

  async function run(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!action) return;
    const fd = new FormData(e.currentTarget);
    const num = (k: string) => (fd.get(k) ? Number(fd.get(k)) : undefined);
    const reason = String(fd.get("reason") || "");
    const paths: Record<Action, [string, unknown]> = {
      invite: [
        "/invite",
        {
          note: reason,
          trial_days: num("days"),
          trial_rate: fd.get("rate") ? String(fd.get("rate")) : undefined,
          launch_cohort: fd.get("cohort") === "on" ? true : undefined,
        },
      ],
      approve: [
        "/approve",
        {
          reason,
          trial_days: num("days"),
          trial_rate: fd.get("rate") ? String(fd.get("rate")) : undefined,
          skip_trial: fd.get("skip") === "on",
        },
      ],
      "request-changes": ["/request-changes", { reason }],
      reject: ["/reject", { reason }],
      activate: ["/activate", { reason }],
      suspend: ["/suspend", { reason }],
      reactivate: ["/reactivate", { reason }],
      grant: [
        "/trial/grant",
        {
          reason,
          days: num("days"),
          rate: fd.get("rate") ? String(fd.get("rate")) : undefined,
        },
      ],
      extend: ["/trial/extend", { reason, days: num("days") }],
      end: ["/trial/end", { reason }],
    };
    if (action === "end" && !window.confirm(t("mpa.confirmEnd"))) return;
    setBusy(true);
    try {
      const [path, body] = paths[action];
      setData(await call(`/providers/${id}${path}`, body, "POST"));
      say("info", t(`mpa.done.${action}`, { name: p.business_name }));
      setAction(null);
    } catch (err) {
      say("error", errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function cohort(included: boolean) {
    try {
      setData(await call(`/providers/${id}/cohort`, { included }, "POST"));
    } catch (err) {
      say("error", errorMessage(err));
    }
  }

  const customTerms =
    finance &&
    (action === "invite" || action === "approve" || action === "grant");
  return (
    <article className="mpaDetail">
      <div className="spread">
        <div>
          <StatusChip status={p.status} />
          <h2>{p.business_name}</h2>
          <p className="muted">
            {p.area} · {p.business.address} · {p.business.phone}
          </p>
          <p className="mpaStates">
            <span>
              {t("mpa.state.review")}:{" "}
              <b>{t(`mpa.review.${p.review_status}`)}</b>
            </span>
            <span>
              {t("mpa.state.commercial")}:{" "}
              <b>{t(`mpa.commercial.${p.commercial_status}`)}</b>
            </span>
            <span>
              {t("mpa.state.listing")}:{" "}
              <b>{t(`mpa.listing.${p.listing_status}`)}</b>
            </span>
            <span>
              {t("mpa.state.orders")}:{" "}
              <b>{p.accepting_orders ? t("mpa.yes") : t("mpa.no")}</b>
            </span>
          </p>
        </div>
        <button
          className="textBtn"
          onClick={onClose}
          aria-label={t("common.close")}
        >
          <X aria-hidden /> {t("common.close")}
        </button>
      </div>

      <div className="mpaActions">
        {actions.map((x) => (
          <button
            key={x}
            className={
              x === "approve" || x === "activate" || x === "reactivate"
                ? "primary"
                : "outlineBtn"
            }
            onClick={() => setAction(action === x ? null : x)}
            aria-expanded={action === x}
          >
            {t(`mpa.action.${x}`)}
          </button>
        ))}
        <label className="check">
          <input
            type="checkbox"
            checked={p.launch_cohort}
            onChange={(e) => cohort(e.target.checked)}
          />{" "}
          {t("mpa.cohortLabel")}
        </label>
      </div>

      {action && (
        <form className="panel monForm" onSubmit={run}>
          <h3>{t(`mpa.action.${action}`)}</h3>
          <p className="muted small">{t(`mpa.help.${action}`)}</p>
          {(customTerms || action === "extend") && (
            <div className="formGrid">
              <label>
                {action === "extend" ? t("mpa.extendBy") : t("mpa.trialDays")}
                <input
                  name="days"
                  type="number"
                  min={1}
                  max={365}
                  required={action === "extend"}
                  placeholder={
                    action === "extend" ? "" : String(p.trial_offer?.days ?? "")
                  }
                />
              </label>
              {action !== "extend" && (
                <label>
                  {t("mpa.trialRate")}
                  <input
                    name="rate"
                    type="number"
                    min={0}
                    max={50}
                    step={0.01}
                    placeholder={
                      p.trial_offer ? String(p.trial_offer.rate) : ""
                    }
                  />
                </label>
              )}
            </div>
          )}
          {action === "approve" && finance && (
            <label className="check">
              <input type="checkbox" name="skip" /> {t("mpa.skipTrial")}
            </label>
          )}
          {action === "invite" && (
            <label className="check">
              <input type="checkbox" name="cohort" /> {t("mpa.cohortLabel")}
            </label>
          )}
          <label>
            {action === "invite" ? t("mpa.note") : t("mon.reason")}
            <input
              name="reason"
              required={NEEDS_REASON.includes(action)}
              minLength={NEEDS_REASON.includes(action) ? 3 : 0}
              maxLength={action === "invite" ? 500 : 255}
            />
          </label>
          <div className="formActions">
            <button className="primary" disabled={busy}>
              {t(`mpa.action.${action}`)}
            </button>
            <button
              type="button"
              className="textBtn"
              onClick={() => setAction(null)}
            >
              {t("common.cancel")}
            </button>
          </div>
        </form>
      )}

      <div className="detailGrid">
        <section className="panel">
          <h3>{t("mpa.readiness")}</h3>
          <ul className="checklist">
            {p.checklist
              .filter((c: any) => c.applies !== false)
              .map((c: any) => (
                <li key={c.key} className={c.done ? "done" : ""}>
                  {c.done ? <Check /> : <Circle />} {t(`mpx.check.${c.key}`)}
                </li>
              ))}
          </ul>
          <p className="muted small">
            {t("mp.contact")}: {p.application.contact_name ?? "—"} ·{" "}
            {t("mp.registration")}: {p.application.registration_number ?? "—"} ·
            TIN: {p.application.tin ?? "—"} · {t("mp.radius")}:{" "}
            {p.application.pickup_radius_km} km
          </p>
          {p.application.invitation_note && (
            <p className="muted small">
              {t("mpa.note")}: {p.application.invitation_note}
            </p>
          )}
          <p>{p.business.description}</p>
          <p className="muted small">
            {p.services
              .map((s: any) => `${s.name} ${money(s.price)}`)
              .join(" · ")}
          </p>
        </section>
        <section className="panel">
          <h3>{t("mpa.commercialTerms")}</h3>
          <dl className="ledger">
            <div>
              <dt>{t("mpa.currentRate")}</dt>
              <dd>{pct(p.commission.rate)}</dd>
            </div>
            <div>
              <dt>{t("mpa.standardRate")}</dt>
              <dd>{pct(p.standard_terms.rate)}</dd>
            </div>
            <div>
              <dt>{t("mpa.agreement")}</dt>
              <dd>
                <Terms a={a} />
              </dd>
            </div>
            <div>
              <dt>{t("mpa.postTrial")}</dt>
              <dd>
                {p.post_trial_accepted
                  ? t("mpa.accepted")
                  : t("mpa.notAccepted")}
              </dd>
            </div>
          </dl>
          {p.trial_stats && (
            <p className="muted small">
              {t("mpa.trialUsage", {
                orders: p.trial_stats.orders,
                sales: money(p.trial_stats.sales),
                saved: money(p.trial_stats.commission_saved),
                customers: p.trial_stats.new_customers,
              })}
            </p>
          )}
          <h4>{t("mpa.versions")}</h4>
          <ul className="ruleList">
            {p.agreements.map((x: any) => (
              <li
                className={`ruleRow ${x.status === "ACTIVE" ? "" : "ended"}`}
                key={x.id}
              >
                <b>v{x.version}</b>
                <span>
                  {x.kind === "TRIAL"
                    ? t("mpa.trialTerms", {
                        days: x.duration_days,
                        rate: pct(x.rate),
                      })
                    : t("mpa.terms.standard")}
                  <small>
                    {x.starts_at ? date(x.starts_at) : t("mpa.notStarted")}
                    {x.ends_at ? ` → ${date(x.ends_at)}` : ""} ·{" "}
                    {t(`mpa.source.${x.source}`)}
                    {x.extensions
                      ? ` · ${t("mpa.extensions", { count: x.extensions })}`
                      : ""}
                  </small>
                </span>
                <span className="pill">
                  {t(`mpa.agreementStatus.${x.status}`)}
                  {x.end_reason
                    ? ` · ${t(`mpa.endReason.${x.end_reason}`)}`
                    : ""}
                </span>
              </li>
            ))}
          </ul>
        </section>
      </div>
      <section className="panel">
        <h3>{t("mpa.history")}</h3>
        <ul className="auditList">
          {p.history.map((h: any, i: number) => (
            <li key={i}>
              <span>{dateTime(h.created_at)}</span>
              <span>{h.actor === "system" ? t("admin.system") : h.actor}</span>
              <b>{t(`mpa.event.${h.action}`, { defaultValue: h.action })}</b>
              <span>
                {h.to_status ? t(`mp.status.${h.to_status}`) : ""}
                {h.reason ? ` · ${h.reason}` : ""}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </article>
  );
}

const BUCKETS = [
  "active",
  "expiring",
  "waiting",
  "converted",
  "expired",
] as const;

function Trials({ onOpen }: { onOpen: (id: string) => void }) {
  const { t } = useTranslation();
  const [bucket, setBucket] = useState<(typeof BUCKETS)[number]>("active");
  const { data } = useLoad<any[]>(`/trials?bucket=${bucket}`);
  return (
    <section className="panel">
      <div className="chipRow" role="tablist">
        {BUCKETS.map((b) => (
          <button
            key={b}
            role="tab"
            aria-selected={bucket === b}
            className={`chip ${bucket === b ? "on" : ""}`}
            onClick={() => setBucket(b)}
          >
            {t(`mpa.bucket.${b}`)}
          </button>
        ))}
      </div>
      {!data ? (
        <div className="tableLoading">{t("common.loading")}</div>
      ) : data.length === 0 ? (
        <p className="muted">{t("admin.empty")}</p>
      ) : (
        <table className="reportTable">
          <thead>
            <tr>
              <th>{t("mon.business")}</th>
              <th>{t("mpa.agreement")}</th>
              <th>{t("mpa.period")}</th>
              <th>{t("mpx.stats.orders")}</th>
              <th>{t("mpx.stats.sales")}</th>
              <th>{t("mpx.stats.saved")}</th>
              <th>{t("mpa.postTrial")}</th>
            </tr>
          </thead>
          <tbody>
            {data.map((r) => (
              <tr key={r.agreement.id}>
                <td>
                  <button
                    className="textBtn"
                    onClick={() => onOpen(r.business_id)}
                  >
                    {r.business_name}
                  </button>
                  <br />
                  <StatusChip status={r.status} />
                </td>
                <td>
                  {t("mpa.trialTerms", {
                    days: r.agreement.duration_days,
                    rate: pct(r.agreement.rate),
                  })}
                </td>
                <td>
                  {r.agreement.starts_at
                    ? date(r.agreement.starts_at)
                    : t("mpa.notStarted")}
                  {r.agreement.ends_at ? ` → ${date(r.agreement.ends_at)}` : ""}
                  {r.agreement.days_left != null && (
                    <small>
                      {" "}
                      (
                      {t("mpa.terms.daysShort", {
                        count: r.agreement.days_left,
                      })}
                      )
                    </small>
                  )}
                </td>
                <td>{r.stats?.orders ?? "—"}</td>
                <td>{r.stats ? money(r.stats.sales) : "—"}</td>
                <td>{r.stats ? money(r.stats.commission_saved) : "—"}</td>
                <td>
                  {r.post_trial_accepted
                    ? t("mpa.accepted")
                    : t("mpa.notAccepted")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

// ---- settings (Admin → Monetization → Marketplace settings) --------------------------------------------------------
type Setting = {
  key: string;
  label: string;
  value: any;
  updated_at: string | null;
};
const GROUPS: [string, string[]][] = [
  ["launch", ["marketplace_mode"]],
  [
    "enrolment",
    [
      "marketplace_self_enrollment",
      "marketplace_invitations",
      "marketplace_approval_required",
      "marketplace_verification_required",
      "marketplace_auto_activate",
    ],
  ],
  [
    "trial",
    [
      "marketplace_trial_enabled",
      "marketplace_trial_days",
      "marketplace_trial_rate",
      "marketplace_trial_start",
      "marketplace_trial_one_per_business",
      "marketplace_trial_extension_allowed",
      "marketplace_trial_max_extensions",
    ],
  ],
  ["after", ["marketplace_acceptance_required", "marketplace_reminder_days"]],
  ["suspension", ["marketplace_suspension_pauses_trial"]],
];
const CHOICES: Record<string, string[]> = {
  marketplace_mode: ["OFF", "PILOT", "PUBLIC"],
  marketplace_trial_start: ["WHEN_ORDERS_OPEN", "ON_APPROVAL"],
};

export function MarketplaceSettings({
  canEdit,
  say,
}: {
  canEdit: boolean;
  say: Say;
}) {
  const { t } = useTranslation();
  const { data, reload } = useLoad<{
    settings: Setting[];
    standard_commission: any;
  }>("/settings");
  const [busy, setBusy] = useState(false);
  if (!data) return <div className="tableLoading">{t("common.loading")}</div>;
  const byKey = Object.fromEntries(data.settings.map((s) => [s.key, s]));

  function parse(key: string, raw: FormDataEntryValue | null, current: any) {
    if (typeof current === "boolean") return raw === "on";
    if (key === "marketplace_reminder_days")
      return String(raw ?? "")
        .split(/[\s,]+/)
        .filter(Boolean)
        .map(Number);
    if (key === "marketplace_trial_rate") return String(raw ?? "");
    if (typeof current === "number") return Number(raw);
    return String(raw ?? "");
  }

  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const values: Record<string, any> = {};
    for (const s of data!.settings) {
      const next = parse(s.key, fd.get(s.key), s.value);
      const same =
        s.key === "marketplace_trial_rate"
          ? Number(next) === Number(s.value)
          : JSON.stringify(next) === JSON.stringify(s.value);
      if (!same) values[s.key] = next;
    }
    if (!Object.keys(values).length)
      return say("info", t("mpa.settings.nothing"));
    if (
      values.marketplace_mode &&
      !window.confirm(t(`mpa.settings.confirmMode.${values.marketplace_mode}`))
    )
      return;
    setBusy(true);
    try {
      await call("/settings", { values, reason: fd.get("reason") }, "PUT");
      say(
        "info",
        t("mpa.settings.saved", { count: Object.keys(values).length }),
      );
      reload();
    } catch (err) {
      say("error", errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function runNow() {
    try {
      const r = await call<Record<string, number>>(
        "/lifecycle/run",
        {},
        "POST",
      );
      say(
        "info",
        t("mon.ranBilling", {
          summary:
            Object.entries(r)
              .filter(([, v]) => v)
              .map(([k, v]) => `${k}: ${v}`)
              .join(", ") || "—",
        }),
      );
    } catch (err) {
      say("error", errorMessage(err));
    }
  }

  return (
    <form className="mpaSettings" onSubmit={save}>
      <LaunchBanner mode={byKey.marketplace_mode.value} />
      <p className="muted small">{t("mpa.settings.intro")}</p>
      {GROUPS.map(([group, keys]) => (
        <section className="panel" key={group}>
          <h2>{t(`mpa.settings.group.${group}`)}</h2>
          {keys.map((key) => {
            const s = byKey[key];
            if (!s) return null;
            const label = t(`mpa.settings.${key}`, { defaultValue: s.label });
            if (CHOICES[key])
              return (
                <fieldset className="mpaChoice" key={key} disabled={!canEdit}>
                  <legend>{label}</legend>
                  {CHOICES[key].map((c) => (
                    <label key={c} className="check">
                      <input
                        type="radio"
                        name={key}
                        value={c}
                        defaultChecked={s.value === c}
                      />
                      <span>
                        <b>{t(`mpa.choice.${c}.title`)}</b>
                        <small>{t(`mpa.choice.${c}.body`)}</small>
                      </span>
                    </label>
                  ))}
                </fieldset>
              );
            if (typeof s.value === "boolean")
              return (
                <label className="check settingCheck" key={key}>
                  <input
                    type="checkbox"
                    name={key}
                    defaultChecked={s.value}
                    disabled={!canEdit}
                  />{" "}
                  {label}
                </label>
              );
            return (
              <label className="settingField" key={key}>
                {label}
                <input
                  name={key}
                  disabled={!canEdit}
                  defaultValue={
                    Array.isArray(s.value) ? s.value.join(", ") : s.value
                  }
                  inputMode={
                    key === "marketplace_reminder_days" ? "text" : "decimal"
                  }
                />
              </label>
            );
          })}
          {group === "trial" && (
            <p className="muted small">
              {t("mpa.settings.standard", {
                rate: pct(data.standard_commission.rate),
              })}
            </p>
          )}
        </section>
      ))}
      {canEdit && (
        <section className="panel">
          <label className="reason">
            {t("mon.reason")}
            <input
              name="reason"
              required
              minLength={3}
              maxLength={255}
              placeholder={t("mon.reasonHint")}
            />
          </label>
          <div className="formActions">
            <button className="primary" disabled={busy}>
              {t("mpa.settings.save")}
            </button>
            <button type="button" className="outlineBtn" onClick={runNow}>
              <Play aria-hidden /> {t("mpa.settings.runNow")}
            </button>
          </div>
        </section>
      )}
    </form>
  );
}
