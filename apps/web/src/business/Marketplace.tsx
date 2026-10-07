import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Check, Circle, Clock3, Store } from "lucide-react";
import { api } from "../lib/api";
import { date, errorMessage } from "../lib/format";
import { useSession } from "../lib/useSession";
import { Notice } from "../customer/ui";
import { AppFrame } from "./shell";

type Status = {
  business_name: string;
  slug: string;
  status:
    "NOT_ENROLLED" | "PENDING_REVIEW" | "ACTIVE" | "REJECTED" | "SUSPENDED";
  commission_rate: number | null;
  pickup_radius_km: number | null;
  submitted_at: string | null;
  approved_at: string | null;
  rejection_reason: string | null;
  checklist: { key: string; done: boolean }[];
};

const FIX_LINKS: Record<string, string> = {
  profile: "/app/settings",
  location: "/app/settings",
  services: "/app/services",
  hours: "/app/settings",
};

export default function MarketplaceBusiness() {
  const { t } = useTranslation();
  const session = useSession("business");
  const [data, setData] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () =>
    api<Status>("/api/v1/business/marketplace", { auth: "business" })
      .then(setData)
      .catch((e) => setError(errorMessage(e)));
  useEffect(() => {
    load();
  }, []);

  async function apply(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    setBusy(true);
    setError("");
    try {
      setData(
        await api<Status>("/api/v1/business/marketplace/application", {
          auth: "business",
          body: {
            contact_name: fd.get("contact_name"),
            registration_number: fd.get("registration_number"),
            tin: fd.get("tin"),
            pickup_radius_km: Number(fd.get("radius")),
            accept_terms: fd.get("terms") === "on",
          },
        }),
      );
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const ready = data?.checklist.every((c) => c.done);
  const canApply =
    data &&
    (data.status === "NOT_ENROLLED" || data.status === "REJECTED") &&
    session?.user.role === "BUSINESS_OWNER";

  return (
    <AppFrame title={t("biz.nav.marketplace")}>
      {error && <Notice>{error}</Notice>}
      {data && (
        <>
          <section className="marketStatus">
            <div className="marketStatusIcon">
              <Store />
            </div>
            <div>
              <span className={"status " + data.status.toLowerCase()}>
                {t(`mp.status.${data.status}`)}
              </span>
              <h2>{t(`mp.headline.${data.status}`)}</h2>
              <p>{t(`mp.body.${data.status}`)}</p>
              {data.rejection_reason && (
                <p className="formError">{data.rejection_reason}</p>
              )}
              {data.status === "ACTIVE" && (
                <Link className="textLink" to={`/laundries/${data.slug}`}>
                  {t("mp.viewStorefront")}
                </Link>
              )}
            </div>
          </section>

          {data.status === "PENDING_REVIEW" && (
            <section className="workspaceCard reviewProgress">
              <Clock3 />
              <h3>{t("mp.submittedOn", { date: date(data.submitted_at) })}</h3>
              <button className="outlineBtn" onClick={load}>
                {t("mp.refresh")}
              </button>
            </section>
          )}

          {canApply && (
            <div className="detailGrid">
              <section className="workspaceCard">
                <h3>{t("mp.checklist")}</h3>
                <ul className="checklist">
                  {data.checklist.map((c) => (
                    <li key={c.key} className={c.done ? "done" : ""}>
                      {c.done ? <Check /> : <Circle />}
                      <span>{t(`mp.check.${c.key}`)}</span>
                      {!c.done && (
                        <Link to={FIX_LINKS[c.key]}>{t("mp.fix")}</Link>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
              <form className="workspaceCard workspaceForm" onSubmit={apply}>
                <h3>{t("mp.apply")}</h3>
                <label>
                  {t("mp.contact")}
                  <input
                    name="contact_name"
                    required
                    minLength={2}
                    defaultValue={session?.user.name}
                  />
                </label>
                <label>
                  {t("mp.registration")}
                  <input name="registration_number" maxLength={60} />
                </label>
                <label>
                  TIN
                  <input name="tin" maxLength={30} />
                </label>
                <label>
                  {t("mp.radius")}
                  <input
                    name="radius"
                    type="number"
                    min={1}
                    max={30}
                    defaultValue={8}
                    required
                  />
                </label>
                <label className="checkRow">
                  <input type="checkbox" name="terms" required />{" "}
                  {t("mp.terms")}
                </label>
                <button className="primary" disabled={busy || !ready}>
                  {t("mp.submit")}
                </button>
                {!ready && (
                  <p className="muted small">{t("mp.completeFirst")}</p>
                )}
              </form>
            </div>
          )}
        </>
      )}
    </AppFrame>
  );
}
