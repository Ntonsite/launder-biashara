import { FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Save } from "lucide-react";
import { api } from "../lib/api";
import { errorMessage } from "../lib/format";
import { useSession } from "../lib/useSession";
import { Notice } from "../customer/ui";
import { AppFrame, useProfile, type Profile } from "./shell";

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
type Area = { name: string; latitude: number; longitude: number };

function useSaver() {
  const [state, setState] = useState<{
    busy: boolean;
    error: string;
    saved: boolean;
  }>({ busy: false, error: "", saved: false });
  async function save(fn: () => Promise<unknown>) {
    setState({ busy: true, error: "", saved: false });
    try {
      await fn();
      setState({ busy: false, error: "", saved: true });
      return true;
    } catch (err) {
      setState({ busy: false, error: errorMessage(err), saved: false });
      return false;
    }
  }
  return { ...state, save };
}

export function ProfileForm({
  profile,
  onSaved,
  submitLabel,
}: {
  profile: Profile;
  onSaved: () => void;
  submitLabel?: string;
}) {
  const { t } = useTranslation();
  const s = useSaver();
  const [areas, setAreas] = useState<Area[]>([]);
  useEffect(() => {
    api<{ items: Area[] }>("/api/v1/marketplace/areas").then((r) =>
      setAreas(r.items),
    );
  }, []);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const area = areas.find((a) => a.name === fd.get("area"));
    const body: Record<string, unknown> = {
      name: fd.get("name"),
      description: fd.get("description"),
      phone: fd.get("phone"),
      address: fd.get("address"),
      area: fd.get("area"),
      pickup_enabled: fd.get("pickup") === "on",
      pickup_fee: Number(fd.get("pickup_fee") || 0),
    };
    // Location comes from the chosen neighbourhood unless one was already set precisely.
    if (area && (profile.latitude == null || profile.area !== area.name))
      Object.assign(body, {
        latitude: area.latitude,
        longitude: area.longitude,
      });
    if (
      await s.save(() =>
        api("/api/v1/business/profile", {
          auth: "business",
          method: "PUT",
          body,
        }),
      )
    )
      onSaved();
  }

  return (
    <form className="workspaceForm" onSubmit={submit}>
      <div className="twoFields">
        <label>
          {t("bizAuth.businessName")}
          <input
            name="name"
            required
            minLength={2}
            defaultValue={profile.name}
          />
        </label>
        <label>
          {t("checkout.phone")}
          <input
            name="phone"
            type="tel"
            required
            defaultValue={profile.phone}
          />
        </label>
      </div>
      <label>
        {t("biz.description")}
        <textarea
          name="description"
          required
          maxLength={2000}
          defaultValue={profile.description}
          placeholder={t("biz.descriptionHint")}
        />
      </label>
      <div className="twoFields">
        <label>
          {t("checkout.area")}
          <select name="area" required defaultValue={profile.area}>
            <option value="">{t("market.chooseArea")}</option>
            {[
              ...new Set([
                ...areas.map((a) => a.name),
                ...(profile.area ? [profile.area] : []),
              ]),
            ].map((a) => (
              <option key={a}>{a}</option>
            ))}
          </select>
        </label>
        <label>
          {t("checkout.address")}
          <input
            name="address"
            required
            minLength={3}
            defaultValue={profile.address}
            placeholder={t("checkout.addressHint")}
          />
        </label>
      </div>
      <div className="twoFields">
        <label className="checkRow">
          <input
            type="checkbox"
            name="pickup"
            defaultChecked={profile.pickup_enabled}
          />{" "}
          {t("biz.offerPickup")}
        </label>
        <label>
          {t("checkout.pickupFee")} (TZS)
          <input
            name="pickup_fee"
            type="number"
            min={0}
            step={500}
            defaultValue={profile.pickup_fee}
          />
        </label>
      </div>
      {s.error && <Notice>{s.error}</Notice>}
      {s.saved && <Notice kind="info">{t("biz.saved")}</Notice>}
      <button className="primary" disabled={s.busy}>
        <Save /> {submitLabel ?? t("biz.save")}
      </button>
    </form>
  );
}

export function HoursForm({
  profile,
  onSaved,
  submitLabel,
}: {
  profile: Profile;
  onSaved: () => void;
  submitLabel?: string;
}) {
  const { t } = useTranslation();
  const s = useSaver();
  const initial = DAYS.map(
    (_, weekday) =>
      profile.hours.find((h) => h.weekday === weekday) ?? {
        weekday,
        opens_at: "08:00",
        closes_at: "18:00",
        closed: weekday === 6,
      },
  );
  const [days, setDays] = useState(initial);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (
      await s.save(() =>
        api("/api/v1/business/hours", {
          auth: "business",
          method: "PUT",
          body: { days },
        }),
      )
    )
      onSaved();
  }

  return (
    <form className="workspaceForm" onSubmit={submit}>
      <div className="hoursList">
        {days.map((d, i) => (
          <div key={d.weekday}>
            <b>{t(`days.${DAYS[d.weekday]}`)}</b>
            <input
              type="time"
              aria-label={t("biz.opens")}
              value={d.opens_at}
              disabled={d.closed}
              onChange={(e) =>
                setDays(
                  days.map((x, j) =>
                    j === i ? { ...x, opens_at: e.target.value } : x,
                  ),
                )
              }
            />
            <span>–</span>
            <input
              type="time"
              aria-label={t("biz.closes")}
              value={d.closes_at}
              disabled={d.closed}
              onChange={(e) =>
                setDays(
                  days.map((x, j) =>
                    j === i ? { ...x, closes_at: e.target.value } : x,
                  ),
                )
              }
            />
            <label className="checkRow">
              <input
                type="checkbox"
                checked={d.closed}
                onChange={(e) =>
                  setDays(
                    days.map((x, j) =>
                      j === i ? { ...x, closed: e.target.checked } : x,
                    ),
                  )
                }
              />{" "}
              {t("common.closed")}
            </label>
          </div>
        ))}
      </div>
      {s.error && <Notice>{s.error}</Notice>}
      {s.saved && <Notice kind="info">{t("biz.saved")}</Notice>}
      <button className="primary" disabled={s.busy}>
        <Save /> {submitLabel ?? t("biz.save")}
      </button>
    </form>
  );
}

const ROLES = ["STAFF", "CASHIER", "DRIVER", "BRANCH_MANAGER"] as const;

function Staff() {
  const { t } = useTranslation();
  const session = useSession("business");
  const [items, setItems] = useState<
    { id: string; name: string; email: string; role: string; active: boolean }[]
  >([]);
  const s = useSaver();
  const [role, setRole] = useState<string>("STAFF");
  const load = () =>
    api<{ items: typeof items }>("/api/v1/business/staff", {
      auth: "business",
    }).then((r) => setItems(r.items));
  useEffect(() => {
    load();
  }, []);

  async function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    const ok = await s.save(() =>
      api("/api/v1/business/staff", {
        auth: "business",
        body: {
          full_name: fd.get("name"),
          email: fd.get("email"),
          password: fd.get("password"),
          role: fd.get("role"),
        },
      }),
    );
    if (ok) {
      form.reset();
      load();
    }
  }

  return (
    <section className="workspaceCard">
      <h2>{t("biz.staff")}</h2>
      {items.map((m) => (
        <p className="spread" key={m.id}>
          <span>
            <b>{m.name}</b> <small className="muted">{m.email}</small>
          </span>
          <span className="pill">{t(`biz.role.${m.role}`)}</span>
        </p>
      ))}
      {session?.user.role === "BUSINESS_OWNER" && (
        <form className="workspaceForm" onSubmit={add}>
          <div className="twoFields">
            <input
              name="name"
              required
              minLength={2}
              placeholder={t("bizAuth.fullName")}
              aria-label={t("bizAuth.fullName")}
            />
            <input
              name="email"
              type="email"
              required
              placeholder={t("bizAuth.email")}
              aria-label={t("bizAuth.email")}
            />
            <input
              name="password"
              type="password"
              required
              minLength={8}
              placeholder={t("biz.tempPassword")}
              aria-label={t("biz.tempPassword")}
              autoComplete="new-password"
            />
            <select
              name="role"
              aria-label={t("biz.roleLabel")}
              value={role}
              onChange={(e) => setRole(e.target.value)}
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {t(`biz.role.${r}`)}
                </option>
              ))}
            </select>
          </div>
          <p className="muted small">{t(`ops.roleAbout.${role}`)}</p>
          {s.error && <Notice>{s.error}</Notice>}
          <button className="outlineBtn" disabled={s.busy}>
            {t("biz.addStaff")}
          </button>
        </form>
      )}
    </section>
  );
}

function SettingsBody() {
  const { t } = useTranslation();
  const { profile, reload } = useProfile();
  if (!profile)
    return <div className="tableLoading">{t("common.loading")}</div>;
  return (
    <div className="settingsGrid">
      <section className="workspaceCard">
        <h2>{t("biz.profileAndLocation")}</h2>
        <ProfileForm profile={profile} onSaved={reload} />
      </section>
      <section className="workspaceCard">
        <h2>{t("store.hours")}</h2>
        <HoursForm
          key={JSON.stringify(profile.hours)}
          profile={profile}
          onSaved={reload}
        />
      </section>
      <Staff />
    </div>
  );
}

export default function Settings() {
  const { t } = useTranslation();
  return (
    <AppFrame title={t("biz.nav.settings")}>
      <SettingsBody />
    </AppFrame>
  );
}
