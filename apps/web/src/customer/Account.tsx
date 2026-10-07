import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight, Package, RotateCcw } from "lucide-react";
import { api, sessions } from "../lib/api";
import { date, errorMessage, money } from "../lib/format";
import { useSession } from "../lib/useSession";
import { reorder } from "./reorder";
import SignIn from "./SignIn";
import { EmptyState, Notice, StatusPill } from "./ui";
import type { OrderSummary, Page } from "./types";

const GROUPS = ["active", "completed", "cancelled"] as const;

export default function Account() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const session = useSession("customer");
  const [group, setGroup] = useState<(typeof GROUPS)[number]>("active");
  const [orders, setOrders] = useState<Page<OrderSummary> | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!session) return;
    setOrders(null);
    api<Page<OrderSummary>>(
      `/api/v1/customer/orders?group=${group}&page_size=50`,
      { auth: "customer" },
    )
      .then(setOrders)
      .catch((err) => setError(errorMessage(err)));
  }, [group, session?.user.id]);

  if (!session?.user.name)
    return (
      <main className="checkout narrow">
        <h1>{t("account.title")}</h1>
        <SignIn onDone={() => undefined} />
      </main>
    );

  async function signOut() {
    const s = sessions.get("customer");
    if (s)
      await api("/api/v1/auth/logout", {
        body: { refresh_token: s.refresh_token },
      }).catch(() => undefined);
    sessions.clear("customer");
    nav("/");
  }

  async function again(id: string) {
    try {
      const r = await reorder(id);
      if (r.quote) nav("/cart", { state: { changes: r.changes } });
      else setError(t("track.reorderNothing"));
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <main className="market">
      <div className="spread accountHead">
        <div>
          <p className="kicker">{session.user.phone}</p>
          <h1>
            {session.user.name
              ? t("account.hello", { name: session.user.name.split(" ")[0] })
              : t("account.title")}
          </h1>
        </div>
        <button className="textBtn" onClick={signOut}>
          {t("account.signOut")}
        </button>
      </div>
      <div className="tabs" role="tablist">
        {GROUPS.map((g) => (
          <button
            key={g}
            role="tab"
            aria-selected={group === g}
            className={group === g ? "active" : ""}
            onClick={() => setGroup(g)}
          >
            {t(`account.${g}`)}
          </button>
        ))}
      </div>
      {error && <Notice>{error}</Notice>}
      {!orders ? (
        <div className="orderList">
          {[0, 1].map((i) => (
            <div className="orderCard" key={i}>
              <div className="shimmer line w60" />
              <div className="shimmer line w40" />
            </div>
          ))}
        </div>
      ) : orders.items.length === 0 ? (
        <EmptyState
          icon={<Package />}
          title={t("account.emptyTitle")}
          body={t("account.emptyBody")}
          action={
            <Link className="primary" to="/laundries">
              {t("nav.find")}
            </Link>
          }
        />
      ) : (
        <div className="orderList">
          {orders.items.map((o) => (
            <article className="orderCard" key={o.id}>
              <div className="spread">
                <div>
                  <h3>{o.laundry.name}</h3>
                  <small className="muted">
                    {o.order_number} · {date(o.created_at)} · {money(o.total)}
                  </small>
                </div>
                <StatusPill status={o.status} />
              </div>
              <p className="muted">{o.items_preview.join(", ")}</p>
              {group === "active" ? (
                <Link className="primary" to={`/account/orders/${o.id}`}>
                  {t("orders.track")} <ArrowRight />
                </Link>
              ) : (
                <div className="actions">
                  <button className="primary" onClick={() => again(o.id)}>
                    <RotateCcw /> {t("orders.reorder")}
                  </button>
                  <Link className="textBtn" to={`/account/orders/${o.id}`}>
                    {t("account.details")}
                  </Link>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </main>
  );
}
