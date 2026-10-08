import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Play, Plus } from "lucide-react";
import { api, newIdempotencyKey } from "../lib/api";
import { date, dateTime, errorMessage, money, percent } from "../lib/format";
import { Notice } from "../customer/ui";
import { MarketplaceSettings } from "./MarketplaceAdmin";

const BASE = "/api/v1/admin/monetization";
const TABS = [
  "overview",
  "plans",
  "marketplace",
  "mpsettings",
  "terms",
  "pilots",
  "invoices",
  "audit",
] as const;
type Tab = (typeof TABS)[number];
type Say = (kind: "info" | "error", text: string) => void;
type Ctx = { canEdit: boolean; say: Say };

const call = <T = any,>(
  path: string,
  body?: unknown,
  method?: string,
  headers?: Record<string, string>,
) => api<T>(`${BASE}${path}`, { auth: "admin", body, method, headers });

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
  return { data, error, reload };
}

const toIso = (d: string) =>
  d ? new Date(`${d}T00:00:00`).toISOString() : undefined;
const today = () => new Date().toISOString().slice(0, 10);

/** Text field for the audit reason every financial change needs. */
function Reason() {
  const { t } = useTranslation();
  return (
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
  );
}

function useSubmit(ctx: Ctx, done: () => void) {
  const [busy, setBusy] = useState(false);
  return {
    busy,
    run: async (fn: () => Promise<unknown>, ok: string, confirm?: string) => {
      if (confirm && !window.confirm(confirm)) return false;
      setBusy(true);
      try {
        await fn();
        ctx.say("info", ok);
        done();
        return true;
      } catch (err) {
        ctx.say("error", errorMessage(err));
        return false;
      } finally {
        setBusy(false);
      }
    },
  };
}

type BusinessRow = {
  id: string;
  name: string;
  plan: string;
  source: string;
  access_until: string | null;
  commission_rate: number;
  commission_scope: string;
  subscription_status: string | null;
  price: number;
  interval: string | null;
  marketplace_status: string;
};

function useBusinesses() {
  const { data } = useLoad<{ items: BusinessRow[] }>(
    "/businesses?page_size=100",
  );
  return data?.items ?? [];
}

function BusinessSelect({
  name = "business_id",
  optional,
}: {
  name?: string;
  optional?: boolean;
}) {
  const { t } = useTranslation();
  const list = useBusinesses();
  return (
    <label>
      {t("mon.business")}
      <select name={name} required={!optional} defaultValue="">
        <option value="">
          {optional ? t("mon.allBusinesses") : t("mon.choose")}
        </option>
        {list.map((b) => (
          <option key={b.id} value={b.id}>
            {b.name}
          </option>
        ))}
      </select>
    </label>
  );
}

type Plan = {
  id: string;
  code: string;
  name: string;
  description: string;
  benefits: string[];
  features: string[];
  status: string;
  is_default: boolean;
  trial_days: number;
  grace_days: number;
  max_staff: number | null;
  max_branches: number | null;
  sort_order: number;
  subscribers: number;
  current_prices: Record<"MONTHLY" | "ANNUAL", number | null>;
  price_history: {
    id: string;
    interval: string;
    amount: number;
    effective_from: string;
    effective_to: string | null;
  }[];
};

function usePlans() {
  return useLoad<Plan[]>("/plans");
}

export default function Monetization({ role }: { role: string }) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("overview");
  const [notice, setNotice] = useState<{
    kind: "info" | "error";
    text: string;
  } | null>(null);
  const ctx: Ctx = {
    canEdit: role === "SUPER_ADMIN" || role === "FINANCE_ADMIN",
    say: (kind, text) => setNotice({ kind, text }),
  };
  return (
    <div className="mon">
      <nav className="viewTabs" aria-label={t("admin.tabs.monetization")}>
        {TABS.map((x) => (
          <button
            key={x}
            className={tab === x ? "on" : ""}
            onClick={() => {
              setTab(x);
              setNotice(null);
            }}
          >
            {t(`mon.tabs.${x}`)}
          </button>
        ))}
      </nav>
      {!ctx.canEdit && <p className="muted small">{t("mon.viewOnly")}</p>}
      {notice && <Notice kind={notice.kind}>{notice.text}</Notice>}
      {tab === "overview" && <Overview ctx={ctx} />}
      {tab === "plans" && <Plans ctx={ctx} />}
      {tab === "marketplace" && <MarketplacePricing ctx={ctx} />}
      {tab === "mpsettings" && (
        <MarketplaceSettings canEdit={ctx.canEdit} say={ctx.say} />
      )}
      {tab === "terms" && <Terms ctx={ctx} />}
      {tab === "pilots" && <Pilots ctx={ctx} />}
      {tab === "invoices" && <Invoices ctx={ctx} />}
      {tab === "audit" && <Audit />}
    </div>
  );
}

// ---- overview ----------------------------------------------------------------------------------------------------------
function Overview({ ctx }: { ctx: Ctx }) {
  const { t } = useTranslation();
  const [range, setRange] = useState({
    start: today().slice(0, 8) + "01",
    end: today(),
  });
  const { data, reload } = useLoad<any>(
    `/revenue?start=${range.start}&end=${range.end}`,
  );
  const submit = useSubmit(ctx, reload);
  if (!data) return <div className="tableLoading">{t("common.loading")}</div>;
  const s = data.subscriptions,
    m = data.marketplace,
    p = data.platform_revenue;
  const cards: [string, string | number][] = [
    ["mrr", money(s.mrr)],
    ["activePaid", s.active_paid],
    ["trialing", s.trialing],
    ["complimentary", s.complimentary],
    ["pastDue", s.past_due],
    ["expired", s.expired_in_period],
    ["invoiced", money(s.invoiced)],
    ["collected", money(s.collected)],
    ["outstanding", `${money(s.outstanding)} · ${s.outstanding_invoices}`],
  ];
  return (
    <>
      <div className="monToolbar">
        <label>
          {t("ops.period.from")}{" "}
          <input
            type="date"
            value={range.start}
            onChange={(e) => setRange({ ...range, start: e.target.value })}
          />
        </label>
        <label>
          {t("ops.period.to")}{" "}
          <input
            type="date"
            value={range.end}
            onChange={(e) => setRange({ ...range, end: e.target.value })}
          />
        </label>
        {ctx.canEdit && (
          <button
            className="outlineBtn"
            disabled={submit.busy}
            onClick={() =>
              submit.run(async () => {
                const r = await call<Record<string, number>>(
                  "/billing/run",
                  {},
                  "POST",
                );
                ctx.say(
                  "info",
                  t("mon.ranBilling", {
                    summary:
                      Object.entries(r)
                        .filter(([, v]) => v)
                        .map(([k, v]) => `${k}: ${v}`)
                        .join(", ") || "—",
                  }),
                );
              }, t("mon.ranBillingShort"))
            }
          >
            <Play aria-hidden /> {t("mon.runBilling")}
          </button>
        )}
      </div>
      <h3>{t("mon.saas")}</h3>
      <div className="todayGrid">
        {cards.map(([k, v]) => (
          <div className="stat" key={k}>
            <p>{t(`mon.kpi.${k}`)}</p>
            <strong>{v}</strong>
          </div>
        ))}
      </div>
      <h3>{t("mon.marketplace")}</h3>
      <div className="todayGrid">
        {(
          [
            "gmv",
            "commission_earned",
            "commission_reversed",
            "commission_net",
          ] as const
        ).map((k) => (
          <div className="stat" key={k}>
            <p>{t(`mon.kpi.${k}`)}</p>
            <strong>{money(m[k])}</strong>
          </div>
        ))}
      </div>
      <section className="panel">
        <h2>{t("mon.platformRevenue")}</h2>
        <dl className="ledger">
          <div>
            <dt>{t("mon.kpi.collected")}</dt>
            <dd>{money(p.subscription_collections)}</dd>
          </div>
          <div>
            <dt>{t("mon.kpi.commission_net")}</dt>
            <dd>{money(p.marketplace_commission_net)}</dd>
          </div>
          <div className="strong">
            <dt>{t("mon.total")}</dt>
            <dd>{money(p.total)}</dd>
          </div>
        </dl>
        <p
          className={`muted small ${data.reconciliation.matches ? "" : "danger"}`}
        >
          {data.reconciliation.matches
            ? t("mon.reconciled")
            : t("mon.notReconciled", {
                invoices: money(data.reconciliation.invoice_payments),
                payments: money(data.reconciliation.payments_recorded),
              })}
        </p>
      </section>
      <section className="panel">
        <h2>{t("mon.byBusiness")}</h2>
        {m.by_business.length === 0 ? (
          <p className="muted">{t("admin.empty")}</p>
        ) : (
          <table className="reportTable">
            <thead>
              <tr>
                <th>{t("mon.business")}</th>
                <th>{t("ops.metric.orders")}</th>
                <th>GMV</th>
                <th>{t("mon.kpi.commission_earned")}</th>
                <th>{t("mon.kpi.commission_reversed")}</th>
                <th>{t("mon.kpi.commission_net")}</th>
              </tr>
            </thead>
            <tbody>
              {m.by_business.map((b: any) => (
                <tr key={b.business_id}>
                  <td>{b.name}</td>
                  <td>{b.orders}</td>
                  <td>{money(b.gmv)}</td>
                  <td>{money(b.earned)}</td>
                  <td>{money(b.reversed)}</td>
                  <td>{money(b.net)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}

// ---- plans -------------------------------------------------------------------------------------------------------------
function Plans({ ctx }: { ctx: Ctx }) {
  const { t } = useTranslation();
  const { data: plans, reload } = usePlans();
  const { data: features } =
    useLoad<{ key: string; label: string }[]>("/features");
  const [creating, setCreating] = useState(false);
  const submit = useSubmit(ctx, reload);
  if (!plans || !features)
    return <div className="tableLoading">{t("common.loading")}</div>;

  function create(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const chosen = Object.fromEntries(
      features!.map((f) => [f.key, fd.get(`f_${f.key}`) === "on"]),
    );
    submit
      .run(
        () =>
          call("/plans", {
            code: String(fd.get("code")).toUpperCase(),
            name: fd.get("name"),
            description: fd.get("description"),
            benefits: String(fd.get("benefits") || "")
              .split("\n")
              .map((x) => x.trim())
              .filter(Boolean),
            monthly_price: Number(fd.get("monthly")),
            annual_price: Number(fd.get("annual")),
            trial_days: Number(fd.get("trial") || 0),
            grace_days: Number(fd.get("grace") || 7),
            max_staff: fd.get("staff") ? Number(fd.get("staff")) : null,
            sort_order: Number(fd.get("sort") || 10),
            status: fd.get("status"),
            features: chosen,
            reason: fd.get("reason"),
          }),
        t("mon.saved"),
      )
      .then((ok) => ok && setCreating(false));
  }

  return (
    <>
      {ctx.canEdit && !creating && (
        <button className="primary" onClick={() => setCreating(true)}>
          <Plus aria-hidden /> {t("mon.newPlan")}
        </button>
      )}
      {creating && (
        <form className="panel monForm" onSubmit={create}>
          <h2>{t("mon.newPlan")}</h2>
          <div className="formGrid">
            <label>
              {t("mon.code")}
              <input
                name="code"
                required
                pattern="[A-Za-z][A-Za-z0-9_]{1,39}"
              />
            </label>
            <label>
              {t("mon.name")}
              <input name="name" required minLength={2} />
            </label>
            <label>
              {t("mon.monthly")}
              <input name="monthly" type="number" min={0} step={500} required />
            </label>
            <label>
              {t("mon.annual")}
              <input name="annual" type="number" min={0} step={500} required />
            </label>
            <label>
              {t("mon.trialDays")}
              <input
                name="trial"
                type="number"
                min={0}
                max={365}
                defaultValue={0}
              />
            </label>
            <label>
              {t("mon.graceDays")}
              <input
                name="grace"
                type="number"
                min={0}
                max={90}
                defaultValue={7}
              />
            </label>
            <label>
              {t("mon.maxStaff")}
              <input name="staff" type="number" min={0} />
            </label>
            <label>
              {t("mon.sort")}
              <input name="sort" type="number" min={0} defaultValue={20} />
            </label>
            <label>
              {t("mon.status")}
              <select name="status" defaultValue="ACTIVE">
                <option value="ACTIVE">{t("mon.planStatus.ACTIVE")}</option>
                <option value="HIDDEN">{t("mon.planStatus.HIDDEN")}</option>
              </select>
            </label>
          </div>
          <label>
            {t("mon.description")}
            <input name="description" maxLength={500} />
          </label>
          <label>
            {t("mon.benefits")}
            <textarea
              name="benefits"
              rows={4}
              placeholder={t("mon.benefitsHint")}
            />
          </label>
          <fieldset className="featureGrid">
            <legend>{t("mon.features")}</legend>
            {features.map((f) => (
              <label key={f.key} className="check">
                <input type="checkbox" name={`f_${f.key}`} /> {f.label}
              </label>
            ))}
          </fieldset>
          <Reason />
          <div className="actions">
            <button className="primary" disabled={submit.busy}>
              {t("mon.create")}
            </button>
            <button
              type="button"
              className="textBtn"
              onClick={() => setCreating(false)}
            >
              {t("common.cancel")}
            </button>
          </div>
        </form>
      )}
      <div className="planAdminGrid">
        {plans.map((p) => (
          <PlanAdmin
            key={p.id}
            plan={p}
            features={features}
            ctx={ctx}
            reload={reload}
          />
        ))}
      </div>
    </>
  );
}

function PlanAdmin({
  plan,
  features,
  ctx,
  reload,
}: {
  plan: Plan;
  features: { key: string; label: string }[];
  ctx: Ctx;
  reload: () => void;
}) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<"" | "price" | "edit" | "features">("");
  const submit = useSubmit(ctx, () => {
    setMode("");
    reload();
  });

  function price(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const interval = String(fd.get("interval"));
    const amount = Number(fd.get("amount"));
    const from = String(fd.get("from") || "");
    submit.run(
      () =>
        call(`/plans/${plan.id}/prices`, {
          interval,
          amount,
          effective_from: from ? toIso(from) : undefined,
          reason: fd.get("reason"),
        }),
      t("mon.saved"),
      t("mon.confirmPrice", {
        plan: plan.name,
        interval: t(`billing.intervals.${interval}`),
        from: money(plan.current_prices[interval as "MONTHLY"] ?? 0),
        to: money(amount),
        date: from || t("mon.now"),
      }),
    );
  }
  function edit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    submit.run(
      () =>
        call(
          `/plans/${plan.id}`,
          {
            name: fd.get("name"),
            description: fd.get("description"),
            benefits: String(fd.get("benefits") || "")
              .split("\n")
              .map((x) => x.trim())
              .filter(Boolean),
            status: fd.get("status"),
            trial_days: Number(fd.get("trial")),
            grace_days: Number(fd.get("grace")),
            max_staff: fd.get("staff") ? Number(fd.get("staff")) : null,
            max_branches: fd.get("branches")
              ? Number(fd.get("branches"))
              : null,
            sort_order: Number(fd.get("sort")),
            ...(fd.get("default") === "on" && !plan.is_default
              ? { is_default: true }
              : {}),
            reason: fd.get("reason"),
          },
          "PATCH",
        ),
      t("mon.saved"),
      fd.get("status") === "RETIRED"
        ? t("mon.confirmRetire", { plan: plan.name })
        : undefined,
    );
  }
  function saveFeatures(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    submit.run(
      () =>
        call(
          `/plans/${plan.id}/features`,
          {
            features: Object.fromEntries(
              features.map((f) => [f.key, fd.get(`f_${f.key}`) === "on"]),
            ),
            reason: fd.get("reason"),
          },
          "PUT",
        ),
      t("mon.saved"),
      t("mon.confirmFeatures", { plan: plan.name, count: plan.subscribers }),
    );
  }

  return (
    <article className={`panel planAdmin ${plan.status.toLowerCase()}`}>
      <div className="spread">
        <div>
          <h2>
            {plan.name}{" "}
            {plan.is_default && (
              <span className="pill">{t("mon.default")}</span>
            )}
          </h2>
          <p className="muted small">
            {plan.code} · {t(`mon.planStatus.${plan.status}`)} ·{" "}
            {t("mon.subscribers", { count: plan.subscribers })}
          </p>
        </div>
        <div className="planPrices">
          <strong>{money(plan.current_prices.MONTHLY ?? 0)}</strong>
          <small>{t("billing.per.MONTHLY")}</small>
          <span className="muted small">
            {money(plan.current_prices.ANNUAL ?? 0)} {t("billing.per.ANNUAL")}
          </span>
        </div>
      </div>
      <p className="small">{plan.description}</p>
      <p className="muted small">
        {t("mon.planFacts", {
          trial: plan.trial_days,
          grace: plan.grace_days,
          staff: plan.max_staff ?? "∞",
          branches: plan.max_branches ?? "∞",
        })}
      </p>
      <ul className="featureChips">
        {features.map((f) => (
          <li key={f.key} className={plan.features.includes(f.key) ? "on" : ""}>
            {f.label}
          </li>
        ))}
      </ul>
      {ctx.canEdit && plan.status !== "RETIRED" && (
        <div className="actions">
          <button
            className="outlineBtn"
            onClick={() => setMode(mode === "price" ? "" : "price")}
          >
            {t("mon.changePrice")}
          </button>
          <button
            className="outlineBtn"
            onClick={() => setMode(mode === "features" ? "" : "features")}
          >
            {t("mon.editFeatures")}
          </button>
          <button
            className="textBtn"
            onClick={() => setMode(mode === "edit" ? "" : "edit")}
          >
            {t("mon.editDetails")}
          </button>
        </div>
      )}
      {mode === "price" && (
        <form className="monForm" onSubmit={price}>
          <div className="formGrid">
            <label>
              {t("billing.interval")}
              <select name="interval">
                <option value="MONTHLY">
                  {t("billing.intervals.MONTHLY")}
                </option>
                <option value="ANNUAL">{t("billing.intervals.ANNUAL")}</option>
              </select>
            </label>
            <label>
              {t("mon.amount")}
              <input name="amount" type="number" min={0} step={500} required />
            </label>
            <label>
              {t("mon.effectiveFrom")}
              <input name="from" type="date" min={today()} />
            </label>
          </div>
          <p className="muted small">{t("mon.priceNote")}</p>
          <Reason />
          <button className="primary" disabled={submit.busy}>
            {t("mon.save")}
          </button>
        </form>
      )}
      {mode === "features" && (
        <form className="monForm" onSubmit={saveFeatures}>
          <fieldset className="featureGrid">
            {features.map((f) => (
              <label key={f.key} className="check">
                <input
                  type="checkbox"
                  name={`f_${f.key}`}
                  defaultChecked={plan.features.includes(f.key)}
                />{" "}
                {f.label}
              </label>
            ))}
          </fieldset>
          <p className="muted small">{t("mon.featuresNote")}</p>
          <Reason />
          <button className="primary" disabled={submit.busy}>
            {t("mon.save")}
          </button>
        </form>
      )}
      {mode === "edit" && (
        <form className="monForm" onSubmit={edit}>
          <div className="formGrid">
            <label>
              {t("mon.name")}
              <input name="name" defaultValue={plan.name} required />
            </label>
            <label>
              {t("mon.status")}
              <select name="status" defaultValue={plan.status}>
                {["ACTIVE", "HIDDEN", "RETIRED"].map((s) => (
                  <option key={s} value={s}>
                    {t(`mon.planStatus.${s}`)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("mon.trialDays")}
              <input
                name="trial"
                type="number"
                min={0}
                defaultValue={plan.trial_days}
              />
            </label>
            <label>
              {t("mon.graceDays")}
              <input
                name="grace"
                type="number"
                min={0}
                defaultValue={plan.grace_days}
              />
            </label>
            <label>
              {t("mon.maxStaff")}
              <input
                name="staff"
                type="number"
                min={0}
                defaultValue={plan.max_staff ?? ""}
              />
            </label>
            <label>
              {t("mon.maxBranches")}
              <input
                name="branches"
                type="number"
                min={1}
                defaultValue={plan.max_branches ?? ""}
              />
            </label>
            <label>
              {t("mon.sort")}
              <input
                name="sort"
                type="number"
                min={0}
                defaultValue={plan.sort_order}
              />
            </label>
            <label className="check">
              <input
                type="checkbox"
                name="default"
                defaultChecked={plan.is_default}
                disabled={plan.is_default}
              />{" "}
              {t("mon.makeDefault")}
            </label>
          </div>
          <label>
            {t("mon.description")}
            <input name="description" defaultValue={plan.description} />
          </label>
          <label>
            {t("mon.benefits")}
            <textarea
              name="benefits"
              rows={4}
              defaultValue={plan.benefits.join("\n")}
            />
          </label>
          <Reason />
          <button className="primary" disabled={submit.busy}>
            {t("mon.save")}
          </button>
        </form>
      )}
      <details>
        <summary className="small">{t("mon.priceHistory")}</summary>
        <ul className="plainList small">
          {plan.price_history.map((h) => (
            <li key={h.id}>
              {t(`billing.intervals.${h.interval}`)} · {money(h.amount)} ·{" "}
              {date(h.effective_from)} –{" "}
              {h.effective_to ? date(h.effective_to) : t("mon.open")}
            </li>
          ))}
        </ul>
      </details>
    </article>
  );
}

// ---- marketplace pricing -----------------------------------------------------------------------------------------------
type Rule = {
  id: string;
  scope: string;
  business_id: string | null;
  business_name: string | null;
  rate: number;
  min_commission: number;
  include_pickup_fee: boolean;
  discounts_reduce_basis: boolean;
  effective_from: string;
  effective_to: string | null;
  reason: string;
  state: string;
};

function RuleRow({
  r,
  ctx,
  reload,
}: {
  r: Rule;
  ctx: Ctx;
  reload: () => void;
}) {
  const { t } = useTranslation();
  const submit = useSubmit(ctx, reload);
  return (
    <li className={`ruleRow ${r.state.toLowerCase()}`}>
      <b>{percent(r.rate)}</b>
      <span>
        {r.business_name ?? t(`mon.scope.${r.scope}`)}
        <small>
          {date(r.effective_from)} –{" "}
          {r.effective_to ? date(r.effective_to) : t("mon.open")} ·{" "}
          {t(`mon.state.${r.state}`)}
          {r.min_commission > 0 &&
            ` · ${t("mon.min", { amount: money(r.min_commission) })}`}
          {r.include_pickup_fee && ` · ${t("mon.withPickup")}`}
          {!r.discounts_reduce_basis && ` · ${t("mon.beforeDiscounts")}`}
        </small>
        <small className="muted">{r.reason}</small>
      </span>
      {ctx.canEdit && r.scope !== "DEFAULT" && r.state !== "ENDED" && (
        <button
          className="textBtn danger"
          disabled={submit.busy}
          onClick={() => {
            const reason = window.prompt(t("mon.reason"));
            if (reason && reason.trim().length >= 3)
              submit.run(
                () => call(`/commission/rules/${r.id}/end`, { reason }),
                t("mon.saved"),
              );
          }}
        >
          {t("mon.end")}
        </button>
      )}
    </li>
  );
}

function RuleForm({
  scope,
  ctx,
  reload,
  current,
}: {
  scope: "DEFAULT" | "BUSINESS" | "PROMOTION";
  ctx: Ctx;
  reload: () => void;
  current?: Rule;
}) {
  const { t } = useTranslation();
  const submit = useSubmit(ctx, reload);
  function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    const rate = Number(fd.get("rate"));
    const from = String(fd.get("from") || "");
    const confirm =
      scope === "DEFAULT"
        ? t("mon.confirmDefault", {
            from: percent(current?.rate ?? null),
            to: percent(rate),
            date: from || t("mon.now"),
          })
        : undefined;
    submit
      .run(
        () =>
          call("/commission/rules", {
            scope,
            business_id: fd.get("business_id") || null,
            rate,
            min_commission: Number(fd.get("min") || 0),
            include_pickup_fee: fd.get("pickup") === "on",
            discounts_reduce_basis: fd.get("gross") !== "on",
            effective_from: from ? toIso(from) : undefined,
            effective_to: fd.get("to")
              ? toIso(String(fd.get("to")))
              : undefined,
            reason: fd.get("reason"),
          }),
        t("mon.saved"),
        confirm,
      )
      .then((ok) => ok && form.reset());
  }
  return (
    <form className="monForm" onSubmit={save}>
      <div className="formGrid">
        {scope !== "DEFAULT" && (
          <BusinessSelect optional={scope === "PROMOTION"} />
        )}
        <label>
          {t("mon.rate")}
          <input
            name="rate"
            type="number"
            min={0}
            max={50}
            step={0.25}
            required
          />
        </label>
        <label>
          {t("mon.minCommission")}
          <input name="min" type="number" min={0} step={100} defaultValue={0} />
        </label>
        <label>
          {t("mon.effectiveFrom")}
          <input name="from" type="date" min={today()} />
        </label>
        {scope === "PROMOTION" && (
          <label>
            {t("mon.until")}
            <input name="to" type="date" required min={today()} />
          </label>
        )}
        <label className="check">
          <input type="checkbox" name="pickup" /> {t("mon.includePickup")}
        </label>
        <label className="check">
          <input type="checkbox" name="gross" /> {t("mon.beforeDiscountsLabel")}
        </label>
      </div>
      {scope === "DEFAULT" && (
        <p className="muted small">{t("mon.defaultNote")}</p>
      )}
      <Reason />
      <button className="primary" disabled={submit.busy}>
        {t(`mon.add.${scope}`)}
      </button>
    </form>
  );
}

function MarketplacePricing({ ctx }: { ctx: Ctx }) {
  const { t } = useTranslation();
  const { data: rules, reload } = useLoad<Rule[]>("/commission/rules");
  const { data: settings, reload: reloadSettings } =
    useLoad<{ key: string; label: string; value: unknown }[]>("/settings");
  const businesses = useBusinesses();
  const [calc, setCalc] = useState<{ business: string; amount: number }>({
    business: "",
    amount: 30000,
  });
  const [preview, setPreview] = useState<any>(null);
  const submit = useSubmit(ctx, reloadSettings);
  useEffect(() => {
    if (!calc.business) return setPreview(null);
    call(
      `/commission/preview?business_id=${calc.business}&services=${calc.amount}`,
    )
      .then(setPreview)
      .catch(() => setPreview(null));
  }, [calc.business, calc.amount, rules]);
  if (!rules || !settings)
    return <div className="tableLoading">{t("common.loading")}</div>;
  const by = (scope: string) => rules.filter((r) => r.scope === scope);
  const current = by("DEFAULT").find((r) => r.state === "IN_FORCE");

  return (
    <>
      <section className="panel">
        <h2>{t("mon.defaultRate")}</h2>
        {current && (
          <p className="bigRate">
            {percent(current.rate)}{" "}
            <small className="muted">
              {t("mon.since", { date: date(current.effective_from) })}
            </small>
          </p>
        )}
        <ul className="ruleList">
          {by("DEFAULT").map((r) => (
            <RuleRow key={r.id} r={r} ctx={ctx} reload={reload} />
          ))}
        </ul>
        {ctx.canEdit && (
          <RuleForm
            scope="DEFAULT"
            ctx={ctx}
            reload={reload}
            current={current}
          />
        )}
      </section>
      <section className="panel">
        <h2>{t("mon.calculator")}</h2>
        <div className="formGrid">
          <label>
            {t("mon.business")}
            <select
              value={calc.business}
              onChange={(e) => setCalc({ ...calc, business: e.target.value })}
            >
              <option value="">{t("mon.choose")}</option>
              {businesses.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("mon.orderServices")}
            <input
              type="number"
              min={0}
              step={1000}
              value={calc.amount}
              onChange={(e) =>
                setCalc({ ...calc, amount: Number(e.target.value) })
              }
            />
          </label>
        </div>
        {preview && (
          <dl className="ledger">
            <div>
              <dt>{t("mon.ruleApplied")}</dt>
              <dd>
                {percent(preview.rule.rate)} ·{" "}
                {t(`mon.scope.${preview.rule.scope}`)}
              </dd>
            </div>
            <div>
              <dt>{t("mon.basis")}</dt>
              <dd>{money(preview.basis)}</dd>
            </div>
            <div>
              <dt>{t("mon.commission")}</dt>
              <dd>{money(preview.commission)}</dd>
            </div>
            <div className="strong">
              <dt>{t("mon.laundryGets")}</dt>
              <dd>{money(preview.laundry_amount)}</dd>
            </div>
          </dl>
        )}
      </section>
      <div className="opsCols even">
        <section className="panel">
          <h2>{t("mon.businessRates")}</h2>
          <ul className="ruleList">
            {by("BUSINESS").map((r) => (
              <RuleRow key={r.id} r={r} ctx={ctx} reload={reload} />
            ))}
          </ul>
          {ctx.canEdit && (
            <RuleForm scope="BUSINESS" ctx={ctx} reload={reload} />
          )}
        </section>
        <section className="panel">
          <h2>{t("mon.promotions")}</h2>
          <ul className="ruleList">
            {by("PROMOTION").map((r) => (
              <RuleRow key={r.id} r={r} ctx={ctx} reload={reload} />
            ))}
          </ul>
          {ctx.canEdit && (
            <RuleForm scope="PROMOTION" ctx={ctx} reload={reload} />
          )}
        </section>
      </div>
      <p className="muted small">{t("mon.precedence")}</p>
      <section className="panel">
        <h2>{t("mon.settings")}</h2>
        {settings.map((s) => (
          <form
            key={s.key}
            className="settingRow"
            onSubmit={(e) => {
              e.preventDefault();
              const fd = new FormData(e.currentTarget);
              const raw = String(fd.get("value"));
              const value = typeof s.value === "number" ? Number(raw) : raw;
              submit.run(
                () =>
                  call(
                    `/settings/${s.key}`,
                    { value, reason: fd.get("reason") },
                    "PUT",
                  ),
                t("mon.saved"),
              );
            }}
          >
            <label>
              {t(`mon.setting.${s.key}`, { defaultValue: s.label })}
              {typeof s.value === "number" ? (
                <input
                  name="value"
                  type="number"
                  min={0}
                  defaultValue={s.value as number}
                  disabled={!ctx.canEdit}
                />
              ) : (
                <textarea
                  name="value"
                  rows={2}
                  defaultValue={String(s.value ?? "")}
                  disabled={!ctx.canEdit}
                />
              )}
            </label>
            {ctx.canEdit && (
              <>
                <input
                  name="reason"
                  required
                  minLength={3}
                  placeholder={t("mon.reason")}
                  aria-label={t("mon.reason")}
                />
                <button className="outlineBtn" disabled={submit.busy}>
                  {t("mon.save")}
                </button>
              </>
            )}
          </form>
        ))}
      </section>
    </>
  );
}

// ---- business terms ----------------------------------------------------------------------------------------------------
type Override = {
  id: string;
  business_name: string;
  type: string;
  plan_name: string;
  value: number;
  effective_from: string;
  expires_at: string | null;
  reason: string;
  state: string;
  pilot: boolean;
};

function Terms({ ctx }: { ctx: Ctx }) {
  const { t } = useTranslation();
  const [q, setQ] = useState("");
  const [ended, setEnded] = useState(false);
  const { data: list, reload: reloadList } = useLoad<{ items: BusinessRow[] }>(
    `/businesses?page_size=100${q ? `&q=${encodeURIComponent(q)}` : ""}`,
  );
  const { data: overrides, reload } = useLoad<Override[]>(
    `/overrides?include_ended=${ended}`,
  );
  const { data: plans } = usePlans();
  const [type, setType] = useState("COMPLIMENTARY_PLAN");
  const refresh = () => {
    reload();
    reloadList();
  };
  const submit = useSubmit(ctx, refresh);
  if (!overrides || !plans)
    return <div className="tableLoading">{t("common.loading")}</div>;
  const available = plans.filter((p) => p.status !== "RETIRED");

  function create(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    const days = fd.get("days") ? Number(fd.get("days")) : undefined;
    const name = list?.items.find((b) => b.id === fd.get("business_id"))?.name;
    submit
      .run(
        () =>
          call("/overrides", {
            business_id: fd.get("business_id"),
            type,
            plan_id: fd.get("plan_id"),
            value: Number(fd.get("value") || 0),
            effective_from: fd.get("from")
              ? toIso(String(fd.get("from")))
              : undefined,
            days,
            reason: fd.get("reason"),
          }),
        t("mon.saved"),
        t("mon.confirmOverride", {
          business: name,
          type: t(`mon.overrideType.${type}`),
        }),
      )
      .then((ok) => ok && form.reset());
  }
  function assign(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    submit.run(
      () =>
        call(`/businesses/${fd.get("business_id")}/subscription`, {
          plan_id: fd.get("plan_id"),
          interval: fd.get("interval"),
          reason: fd.get("reason"),
        }),
      t("mon.saved"),
      t("mon.confirmAssign"),
    );
  }

  return (
    <>
      <section className="panel">
        <div className="spread">
          <h2>{t("mon.businesses")}</h2>
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t("mon.search")}
            aria-label={t("mon.search")}
          />
        </div>
        <table className="reportTable">
          <thead>
            <tr>
              <th>{t("mon.business")}</th>
              <th>{t("mon.plan")}</th>
              <th>{t("mon.access")}</th>
              <th>{t("mon.price")}</th>
              <th>{t("mon.commission")}</th>
            </tr>
          </thead>
          <tbody>
            {list?.items.map((b) => (
              <tr key={b.id}>
                <td>
                  {b.name}
                  <small className="muted">
                    {" "}
                    {t(`mp.status.${b.marketplace_status}`)}
                  </small>
                </td>
                <td>{b.plan}</td>
                <td>
                  {t(`billing.source.${b.source}`)}
                  {b.access_until && (
                    <small className="muted"> · {date(b.access_until)}</small>
                  )}
                </td>
                <td>
                  {b.price
                    ? `${money(b.price)} ${t(`billing.per.${b.interval}`)}`
                    : "—"}
                </td>
                <td>
                  {percent(b.commission_rate)}
                  <small className="muted">
                    {" "}
                    {t(`mon.scope.${b.commission_scope}`)}
                  </small>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="panel">
        <div className="spread">
          <h2>{t("mon.overrides")}</h2>
          <label className="check small">
            <input
              type="checkbox"
              checked={ended}
              onChange={(e) => setEnded(e.target.checked)}
            />{" "}
            {t("mon.showEnded")}
          </label>
        </div>
        {overrides.length === 0 ? (
          <p className="muted">{t("admin.empty")}</p>
        ) : (
          <ul className="ruleList">
            {overrides.map((o) => (
              <li key={o.id} className={`ruleRow ${o.state.toLowerCase()}`}>
                <b>{t(`mon.overrideType.${o.type}`)}</b>
                <span>
                  {o.business_name} · {o.plan_name}
                  {o.type === "PLAN_PRICE" &&
                    ` · ${money(o.value)} ${t("billing.per.MONTHLY")}`}
                  {o.type === "PLAN_DISCOUNT" && ` · ${percent(o.value)}`}
                  <small>
                    {date(o.effective_from)} –{" "}
                    {o.expires_at ? date(o.expires_at) : t("mon.open")} ·{" "}
                    {t(`mon.state.${o.state}`)}
                    {o.pilot && ` · ${t("mon.tabs.pilots")}`}
                  </small>
                  <small className="muted">{o.reason}</small>
                </span>
                {ctx.canEdit &&
                  (o.state === "IN_FORCE" || o.state === "SCHEDULED") && (
                    <button
                      className="textBtn danger"
                      onClick={() => {
                        const reason = window.prompt(t("mon.reason"));
                        if (reason && reason.trim().length >= 3)
                          submit.run(
                            () => call(`/overrides/${o.id}/revoke`, { reason }),
                            t("mon.saved"),
                          );
                      }}
                    >
                      {t("mon.revoke")}
                    </button>
                  )}
              </li>
            ))}
          </ul>
        )}
      </section>
      {ctx.canEdit && (
        <div className="opsCols even">
          <form className="panel monForm" onSubmit={create}>
            <h2>{t("mon.newOverride")}</h2>
            <div className="segmented small" role="group">
              {["COMPLIMENTARY_PLAN", "PLAN_PRICE", "PLAN_DISCOUNT"].map(
                (x) => (
                  <button
                    type="button"
                    key={x}
                    className={type === x ? "on" : ""}
                    onClick={() => setType(x)}
                  >
                    {t(`mon.overrideType.${x}`)}
                  </button>
                ),
              )}
            </div>
            <div className="formGrid">
              <BusinessSelect />
              <label>
                {t("mon.plan")}
                <select name="plan_id" required>
                  {available.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </label>
              {type === "PLAN_PRICE" && (
                <label>
                  {t("mon.monthlyPrice")}
                  <input
                    name="value"
                    type="number"
                    min={0}
                    step={500}
                    required
                  />
                </label>
              )}
              {type === "PLAN_DISCOUNT" && (
                <label>
                  {t("mon.discountPct")}
                  <input
                    name="value"
                    type="number"
                    min={1}
                    max={100}
                    required
                  />
                </label>
              )}
              <label>
                {t("mon.effectiveFrom")}
                <input name="from" type="date" min={today()} />
              </label>
              <label>
                {t("mon.forDays")}
                <input
                  name="days"
                  type="number"
                  min={1}
                  max={3650}
                  placeholder={t("mon.noExpiry")}
                />
              </label>
            </div>
            <Reason />
            <button className="primary" disabled={submit.busy}>
              {t("mon.create")}
            </button>
          </form>
          <form className="panel monForm" onSubmit={assign}>
            <h2>{t("mon.assignPlan")}</h2>
            <div className="formGrid">
              <BusinessSelect />
              <label>
                {t("mon.plan")}
                <select name="plan_id" required>
                  {available.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("billing.interval")}
                <select name="interval">
                  <option value="MONTHLY">
                    {t("billing.intervals.MONTHLY")}
                  </option>
                  <option value="ANNUAL">
                    {t("billing.intervals.ANNUAL")}
                  </option>
                </select>
              </label>
            </div>
            <p className="muted small">{t("mon.assignNote")}</p>
            <Reason />
            <button className="outlineBtn" disabled={submit.busy}>
              {t("mon.assign")}
            </button>
          </form>
        </div>
      )}
    </>
  );
}

// ---- pilots ------------------------------------------------------------------------------------------------------------
type Pilot = {
  id: string;
  name: string;
  plan_name: string;
  duration_days: number;
  transition_policy: string;
  status: string;
  notes: string;
  enrollments: {
    id: string;
    business_name: string;
    starts_at: string;
    ends_at: string;
    status: string;
  }[];
};

function Pilots({ ctx }: { ctx: Ctx }) {
  const { t } = useTranslation();
  const { data: pilots, reload } = useLoad<Pilot[]>("/pilots");
  const { data: plans } = usePlans();
  const businesses = useBusinesses();
  const submit = useSubmit(ctx, reload);
  if (!pilots || !plans)
    return <div className="tableLoading">{t("common.loading")}</div>;
  return (
    <>
      {pilots.map((p) => (
        <section className="panel" key={p.id}>
          <div className="spread">
            <div>
              <h2>{p.name}</h2>
              <p className="muted small">
                {p.plan_name} · {t("mon.days", { count: p.duration_days })} ·{" "}
                {t(`mon.policy.${p.transition_policy}`)} ·{" "}
                {t(`mon.pilotStatus.${p.status}`)}
              </p>
            </div>
            {ctx.canEdit && p.status === "ACTIVE" && (
              <button
                className="textBtn"
                onClick={() => {
                  const reason = window.prompt(t("mon.reason"));
                  if (reason && reason.trim().length >= 3)
                    submit.run(
                      () => call(`/pilots/${p.id}/close`, { reason }),
                      t("mon.saved"),
                    );
                }}
              >
                {t("mon.closePilot")}
              </button>
            )}
          </div>
          {p.notes && <p className="small">{p.notes}</p>}
          <table className="reportTable">
            <thead>
              <tr>
                <th>{t("mon.business")}</th>
                <th>{t("mon.starts")}</th>
                <th>{t("mon.ends")}</th>
                <th>{t("mon.status")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {p.enrollments.map((e) => (
                <tr key={e.id}>
                  <td>{e.business_name}</td>
                  <td>{date(e.starts_at)}</td>
                  <td>{date(e.ends_at)}</td>
                  <td>{t(`mon.enrollStatus.${e.status}`)}</td>
                  <td>
                    {ctx.canEdit && e.status === "ACTIVE" && (
                      <button
                        className="textBtn danger"
                        onClick={() => {
                          const reason = window.prompt(t("mon.reason"));
                          if (reason && reason.trim().length >= 3)
                            submit.run(
                              () =>
                                call(
                                  `/pilots/${p.id}/enrollments/${e.id}/remove`,
                                  { reason },
                                ),
                              t("mon.saved"),
                            );
                        }}
                      >
                        {t("mon.remove")}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {ctx.canEdit && p.status === "ACTIVE" && (
            <form
              className="monForm inline"
              onSubmit={(e) => {
                e.preventDefault();
                const fd = new FormData(e.currentTarget);
                const ids = fd
                  .getAll("business_ids")
                  .map(String)
                  .filter(Boolean);
                if (!ids.length) return;
                submit.run(
                  () =>
                    call(`/pilots/${p.id}/enrollments`, {
                      business_ids: ids,
                      starts_at: fd.get("from")
                        ? toIso(String(fd.get("from")))
                        : undefined,
                    }),
                  t("mon.saved"),
                  t("mon.confirmEnroll", {
                    count: ids.length,
                    plan: p.plan_name,
                    days: p.duration_days,
                  }),
                );
              }}
            >
              <label>
                {t("mon.addBusinesses")}
                <select name="business_ids" multiple size={4}>
                  {businesses.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("mon.effectiveFrom")}
                <input name="from" type="date" />
              </label>
              <button className="outlineBtn" disabled={submit.busy}>
                {t("mon.enroll")}
              </button>
            </form>
          )}
        </section>
      ))}
      {ctx.canEdit && (
        <form
          className="panel monForm"
          onSubmit={(e) => {
            e.preventDefault();
            const form = e.currentTarget;
            const fd = new FormData(form);
            submit
              .run(
                () =>
                  call("/pilots", {
                    name: fd.get("name"),
                    plan_id: fd.get("plan_id"),
                    duration_days: Number(fd.get("days")),
                    transition_policy: fd.get("policy"),
                    notes: fd.get("notes"),
                  }),
                t("mon.saved"),
              )
              .then((ok) => ok && form.reset());
          }}
        >
          <h2>{t("mon.newPilot")}</h2>
          <div className="formGrid">
            <label>
              {t("mon.name")}
              <input name="name" required minLength={3} />
            </label>
            <label>
              {t("mon.plan")}
              <select name="plan_id">
                {plans
                  .filter((p) => p.status === "ACTIVE")
                  .map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              {t("mon.durationDays")}
              <input
                name="days"
                type="number"
                min={7}
                max={365}
                defaultValue={90}
                required
              />
            </label>
            <label>
              {t("mon.atTheEnd")}
              <select name="policy">
                {["DOWNGRADE", "INVOICE"].map((x) => (
                  <option key={x} value={x}>
                    {t(`mon.policy.${x}`)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label>
            {t("mon.notes")}
            <input name="notes" maxLength={500} />
          </label>
          <p className="muted small">{t("mon.pilotNote")}</p>
          <button className="primary" disabled={submit.busy}>
            {t("mon.create")}
          </button>
        </form>
      )}
    </>
  );
}

// ---- invoices & payments -----------------------------------------------------------------------------------------------
function Invoices({ ctx }: { ctx: Ctx }) {
  const { t } = useTranslation();
  const [status, setStatus] = useState("OPEN");
  const { data, reload } = useLoad<{ items: any[]; total: number }>(
    `/invoices?page_size=50${status ? `&status=${status}` : ""}`,
  );
  const [open, setOpen] = useState<string | null>(null);
  const { data: detail, reload: reloadDetail } = useLoad<any>(
    open ? `/invoices/${open}` : null,
  );
  const idempotencyKey = useMemo(
    () => newIdempotencyKey(),
    [open, detail?.amount_paid],
  );
  const submit = useSubmit(ctx, () => {
    reload();
    reloadDetail();
  });

  return (
    <div className="opsCols">
      <section className="panel">
        <div className="segmented small" role="group">
          {["OPEN", "PAID", "VOID", ""].map((s) => (
            <button
              key={s || "all"}
              className={status === s ? "on" : ""}
              onClick={() => setStatus(s)}
            >
              {s ? t(`billing.invoiceStatus.${s}`) : t("ops.view.all")}
            </button>
          ))}
        </div>
        {!data ? (
          <div className="tableLoading">{t("common.loading")}</div>
        ) : data.items.length === 0 ? (
          <p className="muted">{t("admin.empty")}</p>
        ) : (
          <ul className="invoiceList">
            {data.items.map((i) => (
              <li key={i.id}>
                <button
                  className={open === i.id ? "on" : ""}
                  onClick={() => setOpen(i.id)}
                >
                  <b>{i.number}</b>
                  <span>
                    {i.business_name}
                    <small>
                      {date(i.period_start)} – {date(i.period_end)}
                    </small>
                  </span>
                  <span className="amount">
                    {money(i.amount_due)}
                    <small className={`pill inv-${i.status.toLowerCase()}`}>
                      {t(`billing.invoiceStatus.${i.status}`)}
                    </small>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="panel">
        {!detail ? (
          <p className="muted">{t("mon.pickInvoice")}</p>
        ) : (
          <>
            <h2>
              {detail.number} · {detail.business_name}
            </h2>
            <table className="reportTable">
              <tbody>
                {detail.lines.map((l: any, n: number) => (
                  <tr key={n}>
                    <td>{l.description}</td>
                    <td>{money(l.amount)}</td>
                  </tr>
                ))}
                <tr className="strong">
                  <td>{t("billing.total")}</td>
                  <td>{money(detail.amount_due)}</td>
                </tr>
                {detail.payments.map((p: any) => (
                  <tr key={p.id}>
                    <td>
                      {dateTime(p.received_at)} ·{" "}
                      {t(`billing.method.${p.method}`)}
                      {p.reference && ` · ${p.reference}`}
                    </td>
                    <td>−{money(p.amount)}</td>
                  </tr>
                ))}
                <tr className="strong">
                  <td>{t("billing.balance")}</td>
                  <td>{money(detail.balance)}</td>
                </tr>
              </tbody>
            </table>
            {detail.void_reason && (
              <p className="muted">
                {t("billing.voided", { reason: detail.void_reason })}
              </p>
            )}
            {ctx.canEdit && detail.status === "OPEN" && (
              <>
                <form
                  className="monForm"
                  key={idempotencyKey}
                  onSubmit={(e) => {
                    e.preventDefault();
                    const fd = new FormData(e.currentTarget);
                    const amount = Number(fd.get("amount"));
                    submit.run(
                      () =>
                        call(
                          `/invoices/${detail.id}/payments`,
                          {
                            amount,
                            method: fd.get("method"),
                            reference: fd.get("reference"),
                            note: fd.get("note"),
                            received_at: fd.get("received")
                              ? toIso(String(fd.get("received")))
                              : undefined,
                          },
                          "POST",
                          { "Idempotency-Key": idempotencyKey },
                        ),
                      t("mon.paymentRecorded"),
                      t("mon.confirmPayment", {
                        amount: money(amount),
                        number: detail.number,
                      }),
                    );
                  }}
                >
                  <h3>{t("mon.recordPayment")}</h3>
                  <div className="formGrid">
                    <label>
                      {t("mon.amount")}
                      <input
                        name="amount"
                        type="number"
                        min={1}
                        max={detail.balance}
                        defaultValue={detail.balance}
                        required
                      />
                    </label>
                    <label>
                      {t("mon.method")}
                      <select name="method">
                        {["MOBILE_MONEY", "BANK_TRANSFER", "CASH"].map((m) => (
                          <option key={m} value={m}>
                            {t(`billing.method.${m}`)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      {t("mon.reference")}
                      <input name="reference" maxLength={80} />
                    </label>
                    <label>
                      {t("mon.received")}
                      <input name="received" type="date" max={today()} />
                    </label>
                  </div>
                  <label>
                    {t("mon.notes")}
                    <input name="note" maxLength={255} />
                  </label>
                  <p className="muted small">{t("mon.manualOnly")}</p>
                  <button className="primary" disabled={submit.busy}>
                    {t("mon.record")}
                  </button>
                </form>
                {detail.amount_paid === 0 && (
                  <button
                    className="textBtn danger"
                    onClick={() => {
                      const reason = window.prompt(t("mon.reason"));
                      if (reason && reason.trim().length >= 3)
                        submit.run(
                          () => call(`/invoices/${detail.id}/void`, { reason }),
                          t("mon.saved"),
                        );
                    }}
                  >
                    {t("mon.void")}
                  </button>
                )}
              </>
            )}
          </>
        )}
      </section>
    </div>
  );
}

// ---- audit -------------------------------------------------------------------------------------------------------------
function changes(
  before: Record<string, unknown> | null,
  after: Record<string, unknown> | null,
) {
  if (!after) return "";
  return Object.keys(after)
    .filter(
      (k) => !before || JSON.stringify(before[k]) !== JSON.stringify(after[k]),
    )
    .slice(0, 6)
    .map(
      (k) =>
        `${k}: ${before && k in before ? JSON.stringify(before[k]) : "—"} → ${JSON.stringify(after[k])}`,
    )
    .join(" · ");
}

function Audit() {
  const { t } = useTranslation();
  const { data } = useLoad<{ items: any[] }>("/audit?page_size=100");
  if (!data) return <div className="tableLoading">{t("common.loading")}</div>;
  return (
    <section className="panel">
      <ul className="auditList">
        {data.items.map((a) => (
          <li key={a.id}>
            <span className="muted small">{dateTime(a.created_at)}</span>
            <b>{t(`mon.action.${a.action}`, { defaultValue: a.action })}</b>
            <span>
              {a.business_name ?? ""} <small className="muted">{a.actor}</small>
            </span>
            <span className="small">{a.reason}</span>
            <code>{changes(a.before, a.after)}</code>
          </li>
        ))}
      </ul>
    </section>
  );
}
