import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight } from "lucide-react";
import { api } from "../lib/api";
import { errorMessage, money } from "../lib/format";
import { Notice } from "../customer/ui";
import { AppFrame } from "./shell";
import { OrderRows, type OrderRow } from "./Orders";

type Analytics = {
  orders: number;
  revenue: number;
  outstanding: number;
  average_order: number;
  today_orders: number;
  today_revenue: number;
  ready_for_collection: number;
  new_orders: number;
  orders_last_7_days: number;
  sources: Record<string, number>;
  marketplace_commission: number;
  rating: number;
  review_count: number;
};

export default function Dashboard() {
  const { t } = useTranslation();
  const [data, setData] = useState<Analytics | null>(null);
  const [recent, setRecent] = useState<OrderRow[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Analytics>("/api/v1/business/analytics", { auth: "business" })
      .then(setData)
      .catch((e) => setError(errorMessage(e)));
    api<{ items: OrderRow[] }>("/api/v1/business/orders?page_size=5", {
      auth: "business",
    })
      .then((r) => setRecent(r.items))
      .catch(() => setRecent([]));
  }, []);

  const hour = new Date().getHours();
  const greeting = t(
    hour < 12 ? "biz.morning" : hour < 17 ? "biz.afternoon" : "biz.evening",
  );
  const sourceTotal = data
    ? Object.values(data.sources).reduce((a, b) => a + b, 0)
    : 0;

  return (
    <AppFrame title={greeting}>
      {error && <Notice>{error}</Notice>}
      <div className="metrics">
        {[
          [t("biz.metrics.newOrders"), data?.new_orders],
          [t("biz.metrics.todayOrders"), data?.today_orders],
          [t("biz.metrics.todayRevenue"), data && money(data.today_revenue)],
          [t("biz.metrics.ready"), data?.ready_for_collection],
          [t("biz.metrics.outstanding"), data && money(data.outstanding)],
        ].map(([label, value]) => (
          <div className="metric" key={String(label)}>
            <p>{label}</p>
            <h2>{value ?? <span className="shimmer line w40" />}</h2>
          </div>
        ))}
      </div>
      <div className="dashGrid">
        <section className="workspaceCard sourceMix">
          <p className="kicker">{t("biz.orderMix")}</p>
          <h2>{t("biz.whereFrom")}</h2>
          <div className="legend">
            {data &&
              Object.entries(data.sources).map(([source, count]) => (
                <span key={source}>
                  <i className={`${source.toLowerCase()}Dot`} />{" "}
                  {t(`biz.source.${source}`)}{" "}
                  <b>
                    {sourceTotal ? Math.round((count / sourceTotal) * 100) : 0}%
                  </b>
                </span>
              ))}
          </div>
          {data && (
            <p className="muted small">
              {t("biz.paidRevenue")}: <b>{money(data.revenue)}</b> ·{" "}
              {t("biz.avgOrder")}: <b>{money(data.average_order)}</b>
              {data.marketplace_commission > 0 && (
                <>
                  {" "}
                  · {t("biz.commission")}:{" "}
                  <b>{money(data.marketplace_commission)}</b>
                </>
              )}
            </p>
          )}
        </section>
        <section className="quick">
          <h2>{t("biz.quickActions")}</h2>
          {[
            ["biz.newOrder", "/app/orders/new"],
            ["biz.addService", "/app/services"],
            ["biz.marketplaceStatus", "/app/marketplace"],
          ].map(([key, to]) => (
            <Link key={key} to={to}>
              {t(key)}
              <ArrowRight />
            </Link>
          ))}
        </section>
      </div>
      <section className="orders">
        <div className="spread">
          <h2>{t("biz.recentOrders")}</h2>
          <Link to="/app/orders">
            {t("biz.viewAll")} <ArrowRight />
          </Link>
        </div>
        <OrderRows rows={recent} />
      </section>
    </AppFrame>
  );
}
