import { FormEvent, useEffect, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Check, Plus } from "lucide-react";
import { api } from "../lib/api";
import { errorMessage, money } from "../lib/format";
import { useSession } from "../lib/useSession";
import { Notice } from "../customer/ui";
import { HoursForm, ProfileForm } from "./Settings";
import { Lang, type Profile } from "./shell";

const STEPS = ["profile", "hours", "services", "done"] as const;
type ServiceRow = {
  id: string;
  name: string;
  price: number;
  pricing_model: string;
};
const STARTERS = [
  {
    name: "Shirt",
    category: "Wash & Iron",
    pricing_model: "PER_ITEM",
    price: 2000,
  },
  {
    name: "Trouser",
    category: "Wash & Iron",
    pricing_model: "PER_ITEM",
    price: 3000,
  },
  {
    name: "Wash & Fold",
    category: "Wash & Fold",
    pricing_model: "PER_KG",
    price: 4000,
  },
];

/** Four short steps that write straight to the real business profile, hours and services. */
export default function Onboarding() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const session = useSession("business");
  const [step, setStep] = useState(0);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [services, setServices] = useState<ServiceRow[]>([]);
  const [error, setError] = useState("");

  const load = () => {
    api<Profile>("/api/v1/business/profile", { auth: "business" })
      .then(setProfile)
      .catch((e) => setError(errorMessage(e)));
    api<ServiceRow[]>("/api/v1/business/services", { auth: "business" })
      .then(setServices)
      .catch(() => undefined);
  };
  useEffect(() => {
    if (!session) return;
    load();
    api<{ current_step: number }>("/api/v1/business/onboarding", {
      auth: "business",
    })
      .then((r) => setStep(Math.min(Math.max(r.current_step - 1, 0), 3)))
      .catch(() => undefined);
  }, [session?.user.id]);

  if (!session) return <Navigate to="/business/login" replace />;

  async function advance(data: Record<string, unknown> = {}) {
    load();
    const completed = step + 1 >= STEPS.length - 1;
    await api("/api/v1/business/onboarding", {
      auth: "business",
      method: "PUT",
      body: { step: step + 1, data, completed },
    }).catch(() => undefined);
    setStep(step + 1);
  }

  async function addService(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    try {
      await api("/api/v1/business/services", {
        auth: "business",
        body: {
          name: fd.get("name"),
          price: Number(fd.get("price")),
          pricing_model: fd.get("model"),
          category:
            fd.get("model") === "PER_KG" ? "Wash & Fold" : "Wash & Iron",
        },
      });
      form.reset();
      load();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function addStarters() {
    for (const s of STARTERS.filter(
      (x) => !services.some((y) => y.name === x.name),
    )) {
      await api("/api/v1/business/services", {
        auth: "business",
        body: s,
      }).catch((e) => setError(errorMessage(e)));
    }
    load();
  }

  return (
    <main className="onboarding">
      <aside>
        <Link to="/" className="authLogo">
          <img className="logoMark" src="/brand/launder-symbol.svg" alt="" />
          <b>LAUNDER</b>
        </Link>
        <p>{t("onb.setup")}</p>
        {STEPS.map((s, i) => (
          <button
            className={i === step ? "current" : i < step ? "complete" : ""}
            key={s}
            onClick={() => i <= step && setStep(i)}
            aria-current={i === step ? "step" : undefined}
          >
            <i>{i < step ? <Check /> : i + 1}</i>
            <span>{t(`onb.steps.${s}`)}</span>
          </button>
        ))}
      </aside>
      <section>
        <div className="onboardTop">
          <span>
            {t("onb.stepOf", { step: step + 1, total: STEPS.length })}
          </span>
          <Lang />
          <Link to="/app/dashboard">{t("onb.later")}</Link>
        </div>
        <p className="kicker">{profile?.name}</p>
        <h1>{t(`onb.titles.${STEPS[step]}`)}</h1>
        <p className="onboardIntro">{t(`onb.intros.${STEPS[step]}`)}</p>
        {error && <Notice>{error}</Notice>}
        <div className="onboardStepBody">
          {profile && step === 0 && (
            <ProfileForm
              profile={profile}
              onSaved={() => advance()}
              submitLabel={t("onb.saveContinue")}
            />
          )}
          {profile && step === 1 && (
            <HoursForm
              profile={profile}
              onSaved={() => advance()}
              submitLabel={t("onb.saveContinue")}
            />
          )}
          {step === 2 && (
            <>
              {services.map((s) => (
                <p className="spread" key={s.id}>
                  <b>{s.name}</b>
                  <span>
                    {money(s.price)}
                    {s.pricing_model === "PER_KG" && t("common.perKg")}
                  </span>
                </p>
              ))}
              {services.length === 0 && (
                <button className="outlineBtn" onClick={addStarters}>
                  <Plus /> {t("onb.addStarters")}
                </button>
              )}
              <form className="inlineService" onSubmit={addService}>
                <input
                  name="name"
                  required
                  minLength={2}
                  placeholder={t("biz.serviceName")}
                  aria-label={t("biz.serviceName")}
                />
                <input
                  name="price"
                  type="number"
                  min={0}
                  step={100}
                  required
                  placeholder="TZS"
                  aria-label={t("biz.priceTzs")}
                />
                <select name="model" aria-label={t("biz.pricingModel")}>
                  <option value="PER_ITEM">{t("biz.perItem")}</option>
                  <option value="PER_KG">{t("biz.perKg")}</option>
                </select>
                <button className="outlineBtn">{t("biz.add")}</button>
              </form>
              <div className="formActions">
                <button
                  className="primary"
                  disabled={!services.length}
                  onClick={() => advance({ services: services.length })}
                >
                  {t("onb.saveContinue")}
                </button>
              </div>
            </>
          )}
          {step === 3 && (
            <div className="reviewBox">
              <Check />
              <h2>{t("onb.readyTitle", { name: profile?.name })}</h2>
              <p>{t("onb.readyBody")}</p>
              <div className="formActions">
                <button
                  className="primary"
                  onClick={() => nav("/app/dashboard")}
                >
                  {t("onb.openDashboard")}
                </button>
                <Link className="outlineBtn" to="/app/marketplace">
                  {t("onb.joinMarketplace")}
                </Link>
              </div>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
