import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Check } from "lucide-react";
import { api, ApiError, sessions } from "../lib/api";
import {
  date,
  dateTime,
  errorMessage,
  money,
  statusLabel,
} from "../lib/format";
import { useSession } from "../lib/useSession";
import { Notice } from "../customer/ui";
import { Lang, Pagination } from "../business/shell";
import Monetization from "./Monetization";

const TABS = [
  "dashboard",
  "monetization",
  "applications",
  "businesses",
  "orders",
  "customers",
  "payments",
  "reviews",
  "audit",
] as const;
type Tab = (typeof TABS)[number];
type PageData = {
  items: any[];
  total: number;
  page: number;
  page_size: number;
};
const PAGE_SIZE = 20;
const ENDPOINT: Partial<Record<Tab, string>> = {
  applications: "marketplace-applications",
  businesses: "businesses",
  orders: "orders",
  customers: "customers",
  payments: "payments",
  reviews: "reviews",
  audit: "audit-logs",
};

export default function Admin() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const session = useSession("admin");
  const [tab, setTab] = useState<Tab>("dashboard");
  const [stats, setStats] = useState<Record<string, number> | null>(null);
  const [data, setData] = useState<PageData | null>(null);
  const [page, setPage] = useState(1);
  const [detail, setDetail] = useState<any | null>(null);
  const [notice, setNotice] = useState<{
    kind: "error" | "info";
    text: string;
  } | null>(null);

  const load = useCallback(async () => {
    try {
      if (tab === "dashboard")
        setStats(await api("/api/v1/admin/dashboard", { auth: "admin" }));
      else if (tab === "monetization") setData(null);
      else {
        setData(null);
        setData(
          await api<PageData>(
            `/api/v1/admin/${ENDPOINT[tab]}?page=${page}&page_size=${PAGE_SIZE}`,
            { auth: "admin" },
          ),
        );
      }
    } catch (err) {
      if (
        err instanceof ApiError &&
        (err.status === 401 || err.status === 403)
      ) {
        sessions.clear("admin");
        nav("/admin/login");
      } else setNotice({ kind: "error", text: errorMessage(err) });
    }
  }, [tab, page]);

  useEffect(() => {
    if (session) load();
  }, [load, session?.user.id]);

  if (!session) return <Navigate to="/admin/login" replace />;

  async function act(fn: () => Promise<unknown>, message: string) {
    try {
      await fn();
      setNotice({ kind: "info", text: message });
      setDetail(null);
      load();
    } catch (err) {
      setNotice({ kind: "error", text: errorMessage(err) });
    }
  }

  function decide(
    app: any,
    decision: "approve" | "reject" | "suspend" | "reinstate",
  ) {
    let reason: string | null = null;
    if (decision === "reject" || decision === "suspend") {
      reason = window.prompt(t("admin.reasonPrompt"));
      if (!reason?.trim()) return;
    }
    act(
      () =>
        api(`/api/v1/admin/marketplace-applications/${app.id}/${decision}`, {
          auth: "admin",
          body: { reason },
        }),
      t(`admin.decided.${decision}`, { name: app.business_name }),
    );
  }

  async function openApplication(app: any) {
    try {
      setDetail(
        await api(`/api/v1/admin/marketplace-applications/${app.id}`, {
          auth: "admin",
        }),
      );
    } catch (err) {
      setNotice({ kind: "error", text: errorMessage(err) });
    }
  }

  return (
    <main className="adminPage">
      <div className="adminTop">
        <Link className="logo" to="/">
          <img className="logoMark" src="/brand/launder-symbol.svg" alt="" />
          <b>LAUNDER</b>
        </Link>
        <span>{t("admin.title")}</span>
        <Lang />
        <button
          className="textBtn"
          onClick={() => {
            sessions.clear("admin");
            nav("/admin/login");
          }}
        >
          {t("biz.signOut")}
        </button>
      </div>
      <div className="adminShell">
        <aside className="adminNav">
          {TABS.map((id) => (
            <button
              className={tab === id ? "active" : ""}
              key={id}
              onClick={() => {
                setTab(id);
                setPage(1);
                setNotice(null);
                setDetail(null);
              }}
            >
              {t(`admin.tabs.${id}`)}
            </button>
          ))}
        </aside>
        <section className="adminContent">
          <p className="kicker">LAUNDER CONTROL CENTRE</p>
          <h1>{t(`admin.tabs.${tab}`)}</h1>
          {notice && <Notice kind={notice.kind}>{notice.text}</Notice>}

          {tab === "dashboard" && (
            <div className="metrics">
              {stats ? (
                Object.entries(stats).map(([k, v]) => (
                  <div className="metric" key={k}>
                    <p>{t(`admin.stats.${k}`, { defaultValue: k })}</p>
                    <h2>
                      {k === "gmv" || k === "platform_revenue" ? money(v) : v}
                    </h2>
                  </div>
                ))
              ) : (
                <div className="tableLoading">{t("common.loading")}</div>
              )}
            </div>
          )}

          {detail && (
            <article className="workspaceCard">
              <div className="spread">
                <div>
                  <span className={`status ${detail.status.toLowerCase()}`}>
                    {t(`mp.status.${detail.status}`)}
                  </span>
                  <h2>{detail.business_name}</h2>
                  <p className="muted">
                    {detail.area} · {detail.business.address} ·{" "}
                    {detail.business.phone}
                  </p>
                </div>
                <button className="textBtn" onClick={() => setDetail(null)}>
                  {t("common.close")}
                </button>
              </div>
              <p>{detail.business.description}</p>
              <p className="muted small">
                {t("mp.contact")}: {detail.contact_name ?? "—"} ·{" "}
                {t("mp.registration")}: {detail.registration_number ?? "—"} ·
                TIN: {detail.tin ?? "—"} · {t("mp.radius")}:{" "}
                {detail.pickup_radius_km} km
              </p>
              <ul className="checklist">
                {detail.checklist.map((c: any) => (
                  <li key={c.key} className={c.done ? "done" : ""}>
                    {c.done ? <Check /> : "•"} {t(`mp.check.${c.key}`)}
                  </li>
                ))}
              </ul>
              <p className="muted small">
                {detail.services
                  .map((s: any) => `${s.name} ${money(s.price)}`)
                  .join(" · ")}
              </p>
            </article>
          )}

          {tab === "monetization" && <Monetization role={session.user.role} />}

          {tab !== "dashboard" && tab !== "monetization" && (
            <section className="orders adminData">
              {!data ? (
                <div className="tableLoading">{t("common.loading")}</div>
              ) : data.items.length === 0 ? (
                <div className="empty">
                  <p>{t("admin.empty")}</p>
                </div>
              ) : (
                data.items.map((r, i) => (
                  <div className="order adminRow" key={r.id ?? i}>
                    {tab === "applications" && (
                      <>
                        <b>
                          {r.business_name}
                          <small>{r.area}</small>
                        </b>
                        <span>
                          {r.submitted_at ? date(r.submitted_at) : "—"}
                        </span>
                        <span className={`status ${r.status.toLowerCase()}`}>
                          {t(`mp.status.${r.status}`)}
                        </span>
                        <div className="adminActions">
                          <button
                            className="textBtn"
                            onClick={() => openApplication(r)}
                          >
                            {t("admin.review")}
                          </button>
                          {r.status === "PENDING_REVIEW" && (
                            <button
                              className="primary"
                              onClick={() => decide(r, "approve")}
                            >
                              {t("admin.approve")}
                            </button>
                          )}
                          {r.status === "PENDING_REVIEW" && (
                            <button
                              className="outlineBtn"
                              onClick={() => decide(r, "reject")}
                            >
                              {t("admin.reject")}
                            </button>
                          )}
                          {r.status === "ACTIVE" && (
                            <button
                              className="outlineBtn"
                              onClick={() => decide(r, "suspend")}
                            >
                              {t("admin.suspend")}
                            </button>
                          )}
                          {r.status === "SUSPENDED" && (
                            <button
                              className="outlineBtn"
                              onClick={() => decide(r, "reinstate")}
                            >
                              {t("admin.reinstate")}
                            </button>
                          )}
                        </div>
                      </>
                    )}
                    {tab === "businesses" && (
                      <>
                        <b>
                          {r.name}
                          <small>{r.area}</small>
                        </b>
                        <span>
                          {r.review_count
                            ? `★ ${r.rating.toFixed(1)} (${r.review_count})`
                            : "—"}
                        </span>
                        <span
                          className={`status ${r.marketplace_status.toLowerCase()}`}
                        >
                          {t(`mp.status.${r.marketplace_status}`)}
                        </span>
                        <span>{r.status}</span>
                      </>
                    )}
                    {tab === "orders" && (
                      <>
                        <b>
                          {r.order_number}
                          <small>{dateTime(r.created_at)}</small>
                        </b>
                        <span>
                          {r.business_name} · {r.customer_name}
                        </span>
                        <span className={`pill ${r.status.toLowerCase()}`}>
                          {statusLabel(r.status)}
                        </span>
                        <b>
                          {money(r.total)}
                          <small>{t(`payment.${r.payment_status}`)}</small>
                        </b>
                      </>
                    )}
                    {tab === "customers" && (
                      <>
                        <b>{r.name}</b>
                        <span>{r.phone}</span>
                        <span>
                          {r.has_app ? (
                            <span className="pill">{t("biz.usesApp")}</span>
                          ) : null}
                        </span>
                        <span>{r.email ?? ""}</span>
                      </>
                    )}
                    {tab === "payments" && (
                      <>
                        <b>
                          {money(r.amount)}
                          <small>{dateTime(r.created_at)}</small>
                        </b>
                        <span>
                          {r.method === "CASH"
                            ? t("checkout.cash")
                            : t("checkout.mobile")}{" "}
                          {r.reference ?? ""}
                        </span>
                        <span className={`pill ${r.status.toLowerCase()}`}>
                          {t(`payment.${r.status}`)}
                        </span>
                        {r.status === "PAID" ? (
                          <button
                            className="textBtn"
                            onClick={() => {
                              const reason = window.prompt(
                                t("admin.reasonPrompt"),
                              );
                              if (reason?.trim())
                                act(
                                  () =>
                                    api(
                                      `/api/v1/admin/payments/${r.id}/refund`,
                                      { auth: "admin", body: { reason } },
                                    ),
                                  t("admin.refunded"),
                                );
                            }}
                          >
                            {t("admin.refund")}
                          </button>
                        ) : (
                          <span />
                        )}
                      </>
                    )}
                    {tab === "reviews" && (
                      <>
                        <b>
                          {"★".repeat(r.rating)}
                          <small>{r.business_name}</small>
                        </b>
                        <span>
                          {r.comment || "—"}{" "}
                          <small className="muted">— {r.author}</small>
                        </span>
                        <span className={`pill ${r.status.toLowerCase()}`}>
                          {t(`admin.review_${r.status}`)}
                        </span>
                        <button
                          className="textBtn"
                          onClick={() =>
                            act(
                              () =>
                                api(
                                  `/api/v1/admin/reviews/${r.id}/${r.status === "PUBLISHED" ? "hide" : "publish"}`,
                                  { auth: "admin", method: "POST" },
                                ),
                              t("biz.saved"),
                            )
                          }
                        >
                          {r.status === "PUBLISHED"
                            ? t("admin.hide")
                            : t("admin.publish")}
                        </button>
                      </>
                    )}
                    {tab === "audit" && (
                      <>
                        <b>
                          {r.action}
                          <small>{dateTime(r.created_at)}</small>
                        </b>
                        <span>{r.actor ?? t("admin.system")}</span>
                        <span>{r.entity}</span>
                        <span className="muted small">
                          {Object.entries(r.metadata ?? {})
                            .filter(([, v]) => v != null)
                            .map(([k, v]) => `${k}: ${v}`)
                            .join(" · ")}
                        </span>
                      </>
                    )}
                  </div>
                ))
              )}
              {data && data.total > PAGE_SIZE && (
                <Pagination
                  page={page}
                  pages={Math.ceil(data.total / PAGE_SIZE)}
                  total={data.total}
                  pageSize={PAGE_SIZE}
                  onPage={setPage}
                />
              )}
            </section>
          )}
        </section>
      </div>
    </main>
  );
}
