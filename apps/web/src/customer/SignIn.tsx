import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowRight } from "lucide-react";
import { api, ApiError, sessions, type Session } from "../lib/api";
import { errorMessage } from "../lib/format";
import { Notice } from "./ui";

type Step =
  | { kind: "phone" }
  | { kind: "code"; phone: string; devCode?: string }
  | { kind: "name" };

/** Phone → one-time code → (first time only) name. No passwords for customers. */
export default function SignIn({ onDone }: { onDone: () => void }) {
  const { t, i18n } = useTranslation();
  // A verified session without a name is an unfinished sign-in: resume at the name step.
  const [step, setStep] = useState<Step>(() =>
    sessions.get("customer") && !sessions.get("customer")!.user.name
      ? { kind: "name" }
      : { kind: "phone" },
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (err) {
      if (
        err instanceof ApiError &&
        err.code === "OTP_INVALID" &&
        err.details?.attempts_remaining != null
      ) {
        setError(
          t("errors.OTP_INVALID_LEFT", {
            count: err.details.attempts_remaining,
          }),
        );
      } else setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function submitPhone(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const phone = String(new FormData(e.currentTarget).get("phone"));
    run(async () => {
      const r = await api<{ phone: string; dev_code?: string }>(
        "/api/v1/auth/otp/request",
        { body: { phone } },
      );
      setStep({ kind: "code", phone: r.phone, devCode: r.dev_code });
    });
  }

  function submitCode(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (step.kind !== "code") return;
    const code = String(new FormData(e.currentTarget).get("code")).trim();
    run(async () => {
      const r = await api<Session & { is_new_user: boolean }>(
        "/api/v1/auth/otp/verify",
        { body: { phone: step.phone, code } },
      );
      sessions.set("customer", r);
      if (r.is_new_user) setStep({ kind: "name" });
      else onDone();
    });
  }

  function submitName(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const full_name = String(new FormData(e.currentTarget).get("name")).trim();
    run(async () => {
      const user = await api("/api/v1/auth/me", {
        method: "PATCH",
        body: {
          full_name,
          language: i18n.language.startsWith("sw") ? "sw" : "en",
        },
        auth: "customer",
      });
      const s = sessions.get("customer");
      if (s) sessions.set("customer", { ...s, user });
      onDone();
    });
  }

  return (
    <section className="panel signIn">
      {step.kind === "phone" && (
        <form onSubmit={submitPhone}>
          <h2>{t("auth.title")}</h2>
          <p className="muted">{t("auth.subtitle")}</p>
          <label>
            {t("checkout.phone")}
            <div className="phone">
              <span>+255</span>
              <input
                name="phone"
                type="tel"
                inputMode="tel"
                autoComplete="tel"
                required
                placeholder="712 345 678"
              />
            </div>
          </label>
          {error && <Notice>{error}</Notice>}
          <button className="primary full" disabled={busy}>
            {busy ? t("common.wait") : t("auth.sendCode")} <ArrowRight />
          </button>
        </form>
      )}
      {step.kind === "code" && (
        <form onSubmit={submitCode}>
          <h2>{t("auth.codeTitle")}</h2>
          <p className="muted">{t("auth.codeSent", { phone: step.phone })}</p>
          {step.devCode && (
            <Notice kind="info">
              {t("auth.devCode", { code: step.devCode })}
            </Notice>
          )}
          <label>
            {t("auth.code")}
            <input
              name="code"
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="\d{6}"
              maxLength={6}
              required
              autoFocus
            />
          </label>
          {error && <Notice>{error}</Notice>}
          <button className="primary full" disabled={busy}>
            {busy ? t("common.wait") : t("auth.verify")}
          </button>
          <button
            type="button"
            className="textBtn"
            onClick={() => setStep({ kind: "phone" })}
          >
            {t("auth.changeNumber")}
          </button>
        </form>
      )}
      {step.kind === "name" && (
        <form onSubmit={submitName}>
          <h2>{t("auth.nameTitle")}</h2>
          <p className="muted">{t("auth.nameBody")}</p>
          <label>
            {t("checkout.name")}
            <input
              name="name"
              autoComplete="name"
              required
              minLength={2}
              autoFocus
            />
          </label>
          {error && <Notice>{error}</Notice>}
          <button className="primary full" disabled={busy}>
            {t("common.continue")}
          </button>
        </form>
      )}
    </section>
  );
}
