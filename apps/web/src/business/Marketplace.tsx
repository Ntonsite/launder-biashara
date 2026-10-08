import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  BadgePercent,
  BarChart3,
  Check,
  Circle,
  Clock3,
  Gift,
  Inbox,
  MapPin,
  PauseCircle,
  Search,
  ShieldCheck,
  Store,
  Users,
} from "lucide-react";
import { api } from "../lib/api";
import { date, errorMessage, money } from "../lib/format";
import { Notice } from "../customer/ui";
import { AppFrame } from "./shell";
import { useCan } from "./ui";

type Agreement = {
  id: string;
  version: number;
  kind: "TRIAL" | "STANDARD";
  status: "OFFERED" | "PENDING_START" | "ACTIVE" | "ENDED" | "CANCELLED";
  source: string;
  rate: number | null;
  standard_rate: number | null;
  duration_days: number | null;
  starts_at: string | null;
  ends_at: string | null;
  days_left: number | null;
  extensions: number;
  end_reason: string | null;
};
type Offer = {
  days: number;
  rate: number;
  standard_rate: number;
  starts: "WHEN_ORDERS_OPEN" | "ON_APPROVAL";
};
type Terms = {
  rate: number;
  minimum: number;
  includes_pickup_fee: boolean;
  discounts_reduce_basis: boolean;
};
type TrialStats = {
  orders: number;
  sales: number;
  commission_charged: number;
  commission_saved: number;
  new_customers: number;
};
export type MarketplaceView = {
  business_name: string;
  slug: string;
  status:
    | "NOT_ENROLLED"
    | "INVITED"
    | "DRAFT"
    | "PENDING_REVIEW"
    | "CHANGES_REQUESTED"
    | "REJECTED"
    | "APPROVED"
    | "TRIAL_ACTIVE"
    | "ACTIVE"
    | "TRIAL_EXPIRED"
    | "SUSPENDED";
  listing_status: string;
  commercial_status: string;
  ordering_open: boolean;
  accepting_orders: boolean;
  can_apply: boolean;
  self_enrollment: boolean;
  application: {
    contact_name: string | null;
    registration_number: string | null;
    tin: string | null;
    pickup_radius_km: number | null;
  };
  submitted_at: string | null;
  approved_at: string | null;
  post_trial_accepted_at: string | null;
  acceptance_required: boolean;
  rejection_reason: string | null;
  status_reason: string | null;
  invitation: { invited_at: string; note: string | null } | null;
  offer: Offer | null;
  standard_terms: Terms;
  agreement: Agreement | null;
  last_trial: Agreement | null;
  trial_stats: TrialStats | null;
  commission_rate: number;
  listing_fee: number;
  checklist: { key: string; done: boolean; applies?: boolean }[];
};

const FIX_LINKS: Record<string, string> = {
  profile: "/app/settings",
  location: "/app/settings",
  services: "/app/services",
  prices: "/app/services",
  hours: "/app/settings",
  pickup: "/app/settings",
};
const EDITABLE = [
  "NOT_ENROLLED",
  "DRAFT",
  "CHANGES_REQUESTED",
  "REJECTED",
  "INVITED",
];

const pct = (n: number) => `${n % 1 === 0 ? n.toFixed(0) : n.toFixed(2)}%`;

export default function MarketplaceBusiness() {
  const { t } = useTranslation();
  const can = useCan();
  const owner = can("marketplace.manage");
  const [data, setData] = useState<MarketplaceView | null>(null);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [joining, setJoining] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = () =>
    api<MarketplaceView>("/api/v1/business/marketplace", { auth: "business" })
      .then(setData)
      .catch((e) => setError(errorMessage(e)));
  useEffect(() => {
    load();
  }, []);

  async function send(path: string, body: unknown, method: string, ok: string) {
    setBusy(true);
    setError("");
    setInfo("");
    try {
      setData(
        await api<MarketplaceView>(`/api/v1/business/marketplace/${path}`, {
          auth: "business",
          body,
          method,
        }),
      );
      setInfo(ok);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function application(form: HTMLFormElement) {
    const fd = new FormData(form);
    return {
      contact_name: String(fd.get("contact_name") || ""),
      registration_number: String(fd.get("registration_number") || ""),
      tin: String(fd.get("tin") || ""),
      pickup_radius_km: Number(fd.get("radius") || 8),
    };
  }

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    send(
      "application",
      {
        ...application(e.currentTarget),
        accept_terms: fd.get("terms") === "on",
        accept_post_trial: fd.get("post_trial") === "on",
      },
      "POST",
      data?.status === "INVITED" ? t("mpx.joined") : t("mpx.submitted"),
    );
  }

  const acceptTerms = () =>
    send("accept-terms", {}, "POST", t("mpx.termsAccepted"));

  if (!data)
    return (
      <AppFrame title={t("biz.nav.marketplace")}>
        {error ? (
          <Notice>{error}</Notice>
        ) : (
          <div className="tableLoading">{t("common.loading")}</div>
        )}
      </AppFrame>
    );

  const showForm =
    owner &&
    data.can_apply &&
    EDITABLE.includes(data.status) &&
    (joining || data.status !== "NOT_ENROLLED");

  return (
    <AppFrame title={t("biz.nav.marketplace")}>
      {error && <Notice>{error}</Notice>}
      {info && <Notice kind="info">{info}</Notice>}

      {data.status === "NOT_ENROLLED" && !joining && (
        <Pitch
          data={data}
          onJoin={owner && data.can_apply ? () => setJoining(true) : undefined}
        />
      )}

      {data.status !== "NOT_ENROLLED" && <StatusHeader data={data} />}

      {data.invitation && (
        <section className="mpInvite workspaceCard">
          <Gift aria-hidden />
          <div>
            <h3>{t("mpx.invitedTitle")}</h3>
            {data.invitation.note && (
              <blockquote>{data.invitation.note}</blockquote>
            )}
            <p className="muted">{t("mpx.invitedBody")}</p>
          </div>
        </section>
      )}

      {showForm && (
        <JoinFlow
          data={data}
          busy={busy}
          onSubmit={submit}
          onSave={(form) =>
            send("application", application(form), "PUT", t("mpx.draftSaved"))
          }
        />
      )}

      {data.status === "PENDING_REVIEW" && (
        <section className="workspaceCard reviewProgress">
          <Clock3 />
          <h3>{t("mp.submittedOn", { date: date(data.submitted_at) })}</h3>
          <p className="muted">{t("mpx.reviewNext")}</p>
          {data.offer && <OfferCard offer={data.offer} compact />}
          <button className="outlineBtn" onClick={load}>
            {t("mp.refresh")}
          </button>
        </section>
      )}

      {data.status === "APPROVED" && <Waiting data={data} />}

      {(data.status === "TRIAL_ACTIVE" ||
        (data.status === "SUSPENDED" && data.agreement?.kind === "TRIAL")) && (
        <TrialDashboard
          data={data}
          owner={owner}
          busy={busy}
          onAccept={acceptTerms}
        />
      )}

      {data.status === "TRIAL_EXPIRED" && (
        <Expired data={data} owner={owner} busy={busy} onAccept={acceptTerms} />
      )}

      {data.status === "ACTIVE" && <Live data={data} />}
    </AppFrame>
  );
}

// ---- not enrolled: why join ------------------------------------------------------------------------------------------
function Pitch({
  data,
  onJoin,
}: {
  data: MarketplaceView;
  onJoin?: () => void;
}) {
  const { t } = useTranslation();
  const benefits: [typeof Search, string][] = [
    [Search, "reach"],
    [Inbox, "orders"],
    [Store, "oneSystem"],
    [BarChart3, "track"],
    [BadgePercent, "commission"],
  ];
  return (
    <>
      <section className="mpHero">
        <div>
          <p className="kicker">LAUNDER MARKETPLACE</p>
          <h2>{t("mpx.pitchTitle")}</h2>
          <p>{t("mpx.pitchBody")}</p>
          {onJoin ? (
            <button className="primary" onClick={onJoin}>
              {t("mpx.join")}
            </button>
          ) : (
            <p className="mpNote">
              {data.self_enrollment
                ? t("mpx.ownerOnly")
                : t("mpx.byInvitation")}
            </p>
          )}
        </div>
        {data.offer ? (
          <OfferCard offer={data.offer} />
        ) : (
          <StandardCard data={data} />
        )}
      </section>
      <ul className="mpBenefits">
        {benefits.map(([Icon, key]) => (
          <li key={key}>
            <Icon aria-hidden />
            <b>{t(`mpx.benefit.${key}.title`)}</b>
            <span>
              {t(`mpx.benefit.${key}.body`, {
                rate: pct(data.standard_terms.rate),
              })}
            </span>
          </li>
        ))}
      </ul>
      <p className="muted small mpOptional">
        <ShieldCheck className="inlineIcon" aria-hidden /> {t("mpx.optional")}
      </p>
    </>
  );
}

function OfferCard({ offer, compact }: { offer: Offer; compact?: boolean }) {
  const { t } = useTranslation();
  return (
    <div className={`mpOffer${compact ? " compact" : ""}`}>
      <span className="pill">{t("mpx.offer.kicker")}</span>
      <strong>
        {offer.rate === 0
          ? t("mpx.offer.free", { days: offer.days })
          : t("mpx.offer.reduced", { days: offer.days, rate: pct(offer.rate) })}
      </strong>
      <p>
        {t("mpx.offer.after", { rate: pct(offer.standard_rate) })}{" "}
        {offer.starts === "WHEN_ORDERS_OPEN"
          ? t("mpx.offer.startsWhenOpen")
          : t("mpx.offer.startsOnApproval")}
      </p>
      {!compact && <small>{t("mpx.offer.fine")}</small>}
    </div>
  );
}

function StandardCard({ data }: { data: MarketplaceView }) {
  const { t } = useTranslation();
  return (
    <div className="mpOffer">
      <span className="pill">{t("mpx.standard.kicker")}</span>
      <strong>
        {t("mpx.standard.rate", { rate: pct(data.standard_terms.rate) })}
      </strong>
      <p>{t("mpx.standard.body")}</p>
      {data.listing_fee > 0 && (
        <small>
          {t("mpx.listingFee", { amount: money(data.listing_fee) })}
        </small>
      )}
    </div>
  );
}

// ---- application -----------------------------------------------------------------------------------------------------
function JoinFlow({
  data,
  busy,
  onSubmit,
  onSave,
}: {
  data: MarketplaceView;
  busy: boolean;
  onSubmit: (e: FormEvent<HTMLFormElement>) => void;
  onSave: (form: HTMLFormElement) => void;
}) {
  const { t } = useTranslation();
  const steps = data.checklist.filter(
    (c) => c.key !== "terms" && c.applies !== false,
  );
  const ready = steps.every((c) => c.done);
  const offer = data.offer;
  return (
    <div className="detailGrid mpJoin">
      <section className="workspaceCard">
        <h3>{t("mpx.readiness")}</h3>
        <p className="muted small">
          {t("mpx.readyCount", {
            done: steps.filter((c) => c.done).length,
            total: steps.length,
          })}
        </p>
        <ul className="checklist">
          {steps.map((c) => (
            <li key={c.key} className={c.done ? "done" : ""}>
              {c.done ? <Check /> : <Circle />}
              <span>{t(`mpx.check.${c.key}`)}</span>
              {!c.done && FIX_LINKS[c.key] && (
                <Link to={FIX_LINKS[c.key]}>{t("mp.fix")}</Link>
              )}
              {!c.done && c.key === "verification" && (
                <small>{t("mpx.check.verificationHint")}</small>
              )}
            </li>
          ))}
        </ul>
      </section>
      <form className="workspaceCard workspaceForm" onSubmit={onSubmit}>
        <h3>
          {data.status === "INVITED" ? t("mpx.confirmTitle") : t("mp.apply")}
        </h3>
        <label>
          {t("mp.contact")}
          <input
            name="contact_name"
            required
            minLength={2}
            defaultValue={data.application.contact_name ?? ""}
          />
        </label>
        <label>
          {t("mp.registration")}
          <input
            name="registration_number"
            maxLength={60}
            defaultValue={data.application.registration_number ?? ""}
          />
        </label>
        <label>
          TIN
          <input
            name="tin"
            maxLength={30}
            defaultValue={data.application.tin ?? ""}
          />
        </label>
        <label>
          {t("mp.radius")}
          <input
            name="radius"
            type="number"
            min={1}
            max={30}
            defaultValue={data.application.pickup_radius_km ?? 8}
            required
          />
        </label>
        <div className="mpTerms">
          <h4>{t("mpx.termsTitle")}</h4>
          <ul>
            {offer && (
              <li>
                {offer.rate === 0
                  ? t("mpx.offer.free", { days: offer.days })
                  : t("mpx.offer.reduced", {
                      days: offer.days,
                      rate: pct(offer.rate),
                    })}
              </li>
            )}
            <li>
              {t("mpx.terms.standard", {
                rate: pct(data.standard_terms.rate),
              })}
            </li>
            <li>{t("mpx.terms.basis")}</li>
            <li>{t("mpx.terms.walkIn")}</li>
            <li>{t("mpx.terms.prices")}</li>
            {offer && data.acceptance_required && (
              <li>{t("mpx.terms.afterTrial")}</li>
            )}
          </ul>
        </div>
        <label className="checkRow">
          <input type="checkbox" name="terms" required /> {t("mpx.acceptTerms")}
        </label>
        {offer && data.acceptance_required && (
          <label className="checkRow">
            <input type="checkbox" name="post_trial" />{" "}
            {t("mpx.acceptPostTrial", { rate: pct(offer.standard_rate) })}
          </label>
        )}
        <div className="formActions">
          <button className="primary" disabled={busy || !ready}>
            {data.status === "INVITED" ? t("mpx.confirmJoin") : t("mp.submit")}
          </button>
          <button
            type="button"
            className="outlineBtn"
            disabled={busy}
            onClick={(e) => onSave(e.currentTarget.form!)}
          >
            {t("mpx.saveDraft")}
          </button>
        </div>
        {!ready && <p className="muted small">{t("mp.completeFirst")}</p>}
      </form>
    </div>
  );
}

// ---- status header ---------------------------------------------------------------------------------------------------
function StatusHeader({ data }: { data: MarketplaceView }) {
  const { t } = useTranslation();
  const reason =
    data.status === "SUSPENDED" ? data.status_reason : data.rejection_reason;
  return (
    <section className="marketStatus">
      <div className="marketStatusIcon">
        {data.status === "SUSPENDED" || data.status === "TRIAL_EXPIRED" ? (
          <PauseCircle />
        ) : (
          <Store />
        )}
      </div>
      <div>
        <span className={"status " + data.status.toLowerCase()}>
          {t(`mp.status.${data.status}`)}
        </span>
        <h2>{t(`mp.headline.${data.status}`)}</h2>
        <p>{t(`mp.body.${data.status}`)}</p>
        {reason &&
          ["CHANGES_REQUESTED", "REJECTED", "SUSPENDED"].includes(
            data.status,
          ) && <p className="formError">{reason}</p>}
        {data.accepting_orders && (
          <Link className="textLink" to={`/laundries/${data.slug}`}>
            {t("mp.viewStorefront")}
          </Link>
        )}
      </div>
    </section>
  );
}

function Waiting({ data }: { data: MarketplaceView }) {
  const { t } = useTranslation();
  const missing = data.checklist.filter((c) => !c.done && c.applies !== false);
  return (
    <section className="workspaceCard reviewProgress">
      <Clock3 />
      <h3>
        {missing.length
          ? t("mpx.waiting.setup")
          : !data.ordering_open
            ? t("mpx.waiting.launch")
            : t("mpx.waiting.activation")}
      </h3>
      <p className="muted">
        {data.agreement?.kind === "TRIAL"
          ? t("mpx.waiting.trialKept", {
              days: data.agreement.duration_days,
              rate: pct(data.agreement.rate ?? 0),
            })
          : t("mpx.waiting.body")}
      </p>
      {missing.length > 0 && (
        <ul className="checklist">
          {missing.map((c) => (
            <li key={c.key}>
              <Circle /> <span>{t(`mpx.check.${c.key}`)}</span>
              {FIX_LINKS[c.key] && (
                <Link to={FIX_LINKS[c.key]}>{t("mp.fix")}</Link>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ---- trial -----------------------------------------------------------------------------------------------------------
function TrialStatsGrid({
  stats,
  label,
}: {
  stats: TrialStats;
  label: string;
}) {
  const { t } = useTranslation();
  const cards: [string, string | number, typeof Inbox][] = [
    ["orders", stats.orders, Inbox],
    ["sales", money(stats.sales), BarChart3],
    ["saved", money(stats.commission_saved), BadgePercent],
    ["newCustomers", stats.new_customers, Users],
  ];
  return (
    <section className="panel">
      <h2>{label}</h2>
      <div className="todayGrid mpStats">
        {cards.map(([k, v, Icon]) => (
          <div className="stat" key={k}>
            <p>
              <Icon className="inlineIcon" aria-hidden /> {t(`mpx.stats.${k}`)}
            </p>
            <strong>{v}</strong>
          </div>
        ))}
      </div>
      {stats.commission_charged > 0 && (
        <p className="muted small">
          {t("mpx.stats.charged", { amount: money(stats.commission_charged) })}
        </p>
      )}
    </section>
  );
}

function TrialDashboard({
  data,
  owner,
  busy,
  onAccept,
}: {
  data: MarketplaceView;
  owner: boolean;
  busy: boolean;
  onAccept: () => void;
}) {
  const { t } = useTranslation();
  const a = data.agreement!;
  const total = (a.duration_days ?? 0) + 0;
  const used =
    a.starts_at && a.ends_at
      ? Math.min(
          1,
          Math.max(
            0,
            (Date.now() - new Date(a.starts_at).getTime()) /
              (new Date(a.ends_at).getTime() - new Date(a.starts_at).getTime()),
          ),
        )
      : 0;
  const urgent = (a.days_left ?? 99) <= 7;
  return (
    <>
      <section className="mpTrial">
        <div className="mpTrialMain">
          <p className="kicker">{t("mpx.trial.kicker")}</p>
          <h2>{t("mpx.trial.daysLeft", { count: a.days_left ?? 0 })}</h2>
          <div
            className="mpProgress"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(used * 100)}
            aria-label={t("mpx.trial.progress")}
          >
            <span style={{ width: `${used * 100}%` }} />
          </div>
          <p>
            {t("mpx.trial.dates", {
              start: date(a.starts_at),
              end: date(a.ends_at),
            })}
            {a.extensions > 0 && ` · ${t("mpx.trial.extended")}`}
          </p>
        </div>
        <dl className="mpTerms2">
          <div>
            <dt>{t("mpx.trial.now")}</dt>
            <dd>{pct(data.commission_rate)}</dd>
          </div>
          <div>
            <dt>{t("mpx.trial.after")}</dt>
            <dd>{pct(a.standard_rate ?? data.standard_terms.rate)}</dd>
          </div>
          <div>
            <dt>{t("mpx.trial.length")}</dt>
            <dd>{t("mpx.trial.days", { count: total })}</dd>
          </div>
        </dl>
      </section>

      {data.trial_stats && (
        <TrialStatsGrid
          stats={data.trial_stats}
          label={t("mpx.trial.results")}
        />
      )}

      <section className={`panel mpNext${urgent ? " urgent" : ""}`}>
        <h2>{t("mpx.next.title")}</h2>
        {data.post_trial_accepted_at || !data.acceptance_required ? (
          <p>
            <Check className="inlineIcon" aria-hidden />{" "}
            {t("mpx.next.continues", {
              date: date(a.ends_at),
              rate: pct(a.standard_rate ?? data.standard_terms.rate),
            })}
          </p>
        ) : (
          <>
            <p>
              {t("mpx.next.decide", {
                date: date(a.ends_at),
                rate: pct(a.standard_rate ?? data.standard_terms.rate),
              })}
            </p>
            {owner && (
              <button className="primary" disabled={busy} onClick={onAccept}>
                {t("mpx.next.acceptNow", {
                  rate: pct(a.standard_rate ?? data.standard_terms.rate),
                })}
              </button>
            )}
          </>
        )}
        <p className="muted small">{t("mpx.fees")}</p>
        <Link className="textLink" to="/app/reports/marketplace">
          {t("mpx.next.report")}
        </Link>
      </section>
    </>
  );
}

function Expired({
  data,
  owner,
  busy,
  onAccept,
}: {
  data: MarketplaceView;
  owner: boolean;
  busy: boolean;
  onAccept: () => void;
}) {
  const { t } = useTranslation();
  const rate = pct(data.standard_terms.rate);
  return (
    <>
      <section className="panel mpNext urgent">
        <h2>{t("mpx.expired.title", { rate })}</h2>
        <ul className="mpFacts">
          <li>{t("mpx.expired.paused")}</li>
          <li>{t("mpx.expired.existing")}</li>
          <li>{t("mpx.expired.business")}</li>
        </ul>
        <div className="mpTerms">
          <h4>{t("mpx.termsTitle")}</h4>
          <ul>
            <li>{t("mpx.terms.standard", { rate })}</li>
            <li>{t("mpx.terms.basis")}</li>
            <li>{t("mpx.terms.walkIn")}</li>
          </ul>
        </div>
        {owner && (
          <button className="primary" disabled={busy} onClick={onAccept}>
            {t("mpx.expired.accept", { rate })}
          </button>
        )}
      </section>
      {data.trial_stats && (
        <TrialStatsGrid
          stats={data.trial_stats}
          label={t("mpx.trial.summary")}
        />
      )}
    </>
  );
}

function Live({ data }: { data: MarketplaceView }) {
  const { t } = useTranslation();
  return (
    <>
      <section className="panel">
        <h2>{t("mpx.live.terms")}</h2>
        <dl className="mpTerms2 light">
          <div>
            <dt>{t("mpx.live.commission")}</dt>
            <dd>{pct(data.commission_rate)}</dd>
          </div>
          <div>
            <dt>{t("mpx.live.radius")}</dt>
            <dd>
              <MapPin className="inlineIcon" aria-hidden />{" "}
              {data.application.pickup_radius_km ?? "—"} km
            </dd>
          </div>
          <div>
            <dt>{t("mpx.live.since")}</dt>
            <dd>{date(data.agreement?.starts_at ?? data.approved_at)}</dd>
          </div>
        </dl>
        <p className="muted small">
          {t("mpx.terms.basis")} {t("mpx.fees")}
        </p>
        <Link className="textLink" to="/app/reports/marketplace">
          {t("mpx.next.report")}
        </Link>
      </section>
      {data.trial_stats && data.last_trial && (
        <TrialStatsGrid
          stats={data.trial_stats}
          label={t("mpx.trial.summary")}
        />
      )}
    </>
  );
}
