import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../lib/api";
import { errorMessage } from "../lib/format";
import { Notice } from "../customer/ui";
import { AppFrame, Pagination } from "./shell";
import { OrderRows, type OrderRow } from "./Orders";

type CustomerRow = {
  id: string;
  name: string;
  phone: string;
  email: string | null;
  has_app: boolean;
};

export function Customers() {
  const { t } = useTranslation();
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<{
    items: CustomerRow[];
    total: number;
  } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => {
      api<{ items: CustomerRow[]; total: number }>(
        `/api/v1/business/customers?page=${page}&page_size=20${q ? `&q=${encodeURIComponent(q)}` : ""}`,
        { auth: "business" },
      )
        .then(setData)
        .catch((e) => setError(errorMessage(e)));
    }, 250);
    return () => clearTimeout(timer);
  }, [q, page]);

  return (
    <AppFrame title={t("biz.nav.customers")}>
      <div className="toolbar">
        <input
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
          placeholder={t("biz.searchCustomers")}
          aria-label={t("biz.searchCustomers")}
        />
      </div>
      {error && <Notice>{error}</Notice>}
      <section className="orders">
        <div className="tableHead">
          <span>{t("checkout.name")}</span>
          <span>{t("checkout.phone")}</span>
          <span>{t("bizAuth.email")}</span>
          <span />
          <span />
        </div>
        {!data && <div className="tableLoading">{t("common.loading")}</div>}
        {data?.items.map((c) => (
          <div className="order" key={c.id}>
            <b>{c.name}</b>
            <span>{c.phone}</span>
            <span>{c.email ?? "—"}</span>
            <span>
              {c.has_app && <span className="pill">{t("biz.usesApp")}</span>}
            </span>
            <span />
          </div>
        ))}
        {data && (
          <Pagination
            page={page}
            pages={Math.max(1, Math.ceil(data.total / 20))}
            total={data.total}
            pageSize={20}
            onPage={setPage}
          />
        )}
      </section>
    </AppFrame>
  );
}

/** Payments view: orders whose money is still outstanding, then everything recently paid. */
export function Payments() {
  const { t } = useTranslation();
  const [unpaid, setUnpaid] = useState<OrderRow[] | null>(null);
  useEffect(() => {
    api<{ items: OrderRow[] }>(
      "/api/v1/business/orders?page_size=50&status=READY,OUT_FOR_DELIVERY,DELIVERED",
      { auth: "business" },
    )
      .then((r) =>
        setUnpaid(r.items.filter((o) => o.payment_status !== "PAID")),
      )
      .catch(() => setUnpaid([]));
  }, []);
  return (
    <AppFrame title={t("biz.nav.payments")}>
      <p className="dashSub">{t("biz.paymentsIntro")}</p>
      <section className="orders">
        <OrderRows rows={unpaid} />
      </section>
    </AppFrame>
  );
}
