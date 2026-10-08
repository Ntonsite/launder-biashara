import { FormEvent, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight, ShieldCheck } from "lucide-react";
import {
  api,
  ApiError,
  sessions,
  type Audience,
  type Session,
} from "../lib/api";
import { errorMessage } from "../lib/format";
import { Lang } from "./shell";

const ADMIN_ROLES = ["ADMIN", "SUPER_ADMIN", "FINANCE_ADMIN"];
const BUSINESS_ROLES = ["BUSINESS_OWNER", "BRANCH_MANAGER", "STAFF"];

function AuthShell({ kind }: { kind: "login" | "register" | "admin" }) {
  const { t } = useTranslation();
  const nav = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from;
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    setLoading(true);
    setError("");
    try {
      if (kind === "register") {
        const session = await api<Session>("/api/v1/auth/business/register", {
          body: {
            full_name: fd.get("name"),
            business_name: fd.get("business"),
            phone: fd.get("phone"),
            email: fd.get("email"),
            password: fd.get("password"),
          },
        });
        sessions.set("business", session);
        nav("/business/onboarding");
        return;
      }
      const session = await api<Session>("/api/v1/auth/login", {
        body: { email: fd.get("email"), password: fd.get("password") },
      });
      const audience: Audience = kind === "admin" ? "admin" : "business";
      const allowed = kind === "admin" ? ADMIN_ROLES : BUSINESS_ROLES;
      if (!allowed.includes(session.user.role))
        throw new ApiError(401, "INVALID_CREDENTIALS", "");
      sessions.set(audience, session);
      nav(from ?? (kind === "admin" ? "/admin" : "/app/dashboard"));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  const key = kind === "admin" ? "admin" : kind;
  return (
    <main className="authPage">
      <div className="authUtility">
        <Lang />
      </div>
      <Link to="/" className="authLogo">
        <img className="logoMark" src="/brand/launder-symbol.svg" alt="" />
        <b>LAUNDER</b>
      </Link>
      <section
        className={`authPanel ${kind === "register" ? "registerAuth" : "soloAuth"} ${kind === "admin" ? "compactAuth" : ""}`}
      >
        <div>
          <p className="kicker">
            {kind === "admin" ? "PLATFORM ADMIN" : "LAUNDER BUSINESS"}
          </p>
          <h1>{t(`bizAuth.${key}.title`)}</h1>
          <p>{t(`bizAuth.${key}.body`)}</p>
          <form onSubmit={submit}>
            {kind === "register" && (
              <div className="registrationFields">
                <label>
                  {t("bizAuth.fullName")}
                  <input
                    name="name"
                    required
                    minLength={2}
                    autoComplete="name"
                  />
                </label>
                <label>
                  {t("bizAuth.businessName")}
                  <input
                    name="business"
                    required
                    minLength={2}
                    autoComplete="organization"
                  />
                </label>
                <label>
                  {t("checkout.phone")}
                  <input
                    name="phone"
                    type="tel"
                    required
                    placeholder="+255 712 345 678"
                    autoComplete="tel"
                  />
                </label>
              </div>
            )}
            <label>
              {t("bizAuth.email")}
              <input
                name="email"
                type="email"
                required
                autoComplete="email"
                placeholder="you@business.co.tz"
              />
            </label>
            <label>
              {t("bizAuth.password")}
              <input
                name="password"
                type="password"
                required
                minLength={8}
                autoComplete={
                  kind === "register" ? "new-password" : "current-password"
                }
              />
            </label>
            {error && (
              <p className="formError" role="alert">
                {error}
              </p>
            )}
            <button className="primary full" disabled={loading}>
              {loading ? t("common.wait") : t(`bizAuth.${key}.submit`)}{" "}
              <ArrowRight />
            </button>
          </form>
          {kind !== "admin" && (
            <p className="authSwap">
              {kind === "login" ? (
                <>
                  {t("bizAuth.newHere")}{" "}
                  <Link to="/business/register">
                    {t("bizAuth.createAccount")}
                  </Link>
                </>
              ) : (
                <>
                  {t("bizAuth.haveAccount")}{" "}
                  <Link to="/business/login">{t("bizAuth.login.submit")}</Link>
                </>
              )}
            </p>
          )}
        </div>
        {kind === "register" && (
          <div className="authPromise">
            <ShieldCheck />
            <h3>{t("bizAuth.promiseTitle")}</h3>
            <p>{t("bizAuth.promiseBody")}</p>
          </div>
        )}
      </section>
    </main>
  );
}

export const BusinessLogin = () => <AuthShell kind="login" />;
export const BusinessRegister = () => <AuthShell kind="register" />;
export const AdminLogin = () => <AuthShell kind="admin" />;
