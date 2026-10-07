import { createContext, useContext, useEffect, useState } from "react";
import {
  Link,
  NavLink,
  Navigate,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  LayoutDashboard,
  LogOut,
  Menu,
  Package,
  Settings,
  ShoppingBag,
  Store,
  Users,
  Wallet,
  X,
} from "lucide-react";
import { api, sessions } from "../lib/api";
import { useSession } from "../lib/useSession";

export type Profile = {
  id: string;
  name: string;
  slug: string;
  description: string;
  phone: string;
  address: string;
  area: string;
  city: string;
  status: string;
  latitude: number | null;
  longitude: number | null;
  pickup_enabled: boolean;
  pickup_fee: number;
  rating: number;
  review_count: number;
  hours: {
    weekday: number;
    opens_at: string;
    closes_at: string;
    closed: boolean;
  }[];
};

export function Lang() {
  const { i18n } = useTranslation();
  return (
    <div className="lang" role="group" aria-label="Language / Lugha">
      {(["en", "sw"] as const).map((l) => (
        <button
          key={l}
          className={i18n.language === l ? "on" : ""}
          aria-pressed={i18n.language === l}
          onClick={() => i18n.changeLanguage(l)}
        >
          {l.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

export function Pagination({
  page,
  pages,
  total,
  pageSize,
  onPage,
}: {
  page: number;
  pages: number;
  total: number;
  pageSize: number;
  onPage: (p: number) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="pagination">
      <span>
        {t("biz.showing", {
          from: total ? (page - 1) * pageSize + 1 : 0,
          to: Math.min(page * pageSize, total),
          total,
        })}
      </span>
      <div>
        <button disabled={page <= 1} onClick={() => onPage(page - 1)}>
          {t("biz.previous")}
        </button>
        <button disabled={page >= pages} onClick={() => onPage(page + 1)}>
          {t("biz.next")}
        </button>
      </div>
    </div>
  );
}

const ProfileContext = createContext<{
  profile: Profile | null;
  reload: () => void;
}>({ profile: null, reload: () => undefined });
export const useProfile = () => useContext(ProfileContext);

/** Authenticated business workspace frame. Route protection here is UX only; the API enforces every permission. */
export function AppFrame({
  children,
  title,
  action,
}: {
  children: React.ReactNode;
  title: string;
  action?: React.ReactNode;
}) {
  const { t } = useTranslation();
  const session = useSession("business");
  const location = useLocation();
  const nav = useNavigate();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [open, setOpen] = useState(false);
  const reload = () => {
    api<Profile>("/api/v1/business/profile", { auth: "business" })
      .then(setProfile)
      .catch(() => setProfile(null));
  };
  useEffect(reload, [session?.user.id]);
  useEffect(() => setOpen(false), [location.pathname]);

  if (!session)
    return (
      <Navigate
        to="/business/login"
        replace
        state={{ from: location.pathname }}
      />
    );
  const isManager = session.user.role !== "STAFF";
  const items = [
    [LayoutDashboard, "dashboard", "/app/dashboard", true],
    [ShoppingBag, "orders", "/app/orders", true],
    [Users, "customers", "/app/customers", true],
    [Package, "services", "/app/services", true],
    [Wallet, "payments", "/app/payments", true],
    [Store, "marketplace", "/app/marketplace", true],
    [Settings, "settings", "/app/settings", isManager],
  ] as const;

  async function signOut() {
    const s = sessions.get("business");
    if (s)
      await api("/api/v1/auth/logout", {
        body: { refresh_token: s.refresh_token },
      }).catch(() => undefined);
    sessions.clear("business");
    nav("/business/login");
  }

  return (
    <ProfileContext.Provider value={{ profile, reload }}>
      <div className="appShell">
        <aside className={`side ${open ? "open" : ""}`}>
          <Link className="logo" to="/">
            <img className="logoMark" src="/brand/launder-symbol.svg" alt="" />
            <b>LAUNDER</b>
          </Link>
          <div className="branchSelect">
            <small>{t("biz.workspace").toUpperCase()}</small>
            <b>{profile?.name ?? "…"}</b>
            <span>{profile?.area || session.user.name}</span>
          </div>
          {items
            .filter((x) => x[3])
            .map(([Icon, key, to]) => (
              <NavLink
                to={to}
                key={to}
                className={({ isActive }) => (isActive ? "sel" : "")}
              >
                <Icon />
                {t(`biz.nav.${key}`)}
              </NavLink>
            ))}
          <button className="logout" onClick={signOut}>
            <LogOut /> {t("biz.signOut")}
          </button>
          <div className="sideLanguage">
            <small>LANGUAGE · LUGHA</small>
            <Lang />
          </div>
        </aside>
        <main className="dash">
          <div className="mobileAppTop">
            <button
              className="iconBtn"
              aria-label={t("biz.menu")}
              aria-expanded={open}
              onClick={() => setOpen(!open)}
            >
              {open ? <X /> : <Menu />}
            </button>
            <b>{profile?.name}</b>
          </div>
          <div className="dashTop">
            <div>
              <p className="kicker">
                {[profile?.name, profile?.area]
                  .filter(Boolean)
                  .join(" · ")
                  .toUpperCase()}
              </p>
              <h1>{title}</h1>
            </div>
            {action}
          </div>
          {children}
        </main>
      </div>
    </ProfileContext.Provider>
  );
}
