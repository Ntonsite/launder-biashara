import { useEffect, useState, useSyncExternalStore } from "react";
import {
  Link,
  NavLink,
  Navigate,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  BarChart3,
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
  role: string;
  capabilities: string[];
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

/**
 * The signed-in business's profile (with the caller's role and capabilities), shared by every business page.
 * A module store rather than context so pages can read it outside <AppFrame>, which is where most of them need it.
 */
let current: { userId: string | null; profile: Profile | null } = {
  userId: null,
  profile: null,
};
const listeners = new Set<() => void>();
const profileStore = {
  get: () => current,
  set(next: typeof current) {
    current = next;
    listeners.forEach((l) => l());
  },
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};

function loadProfile(userId: string) {
  api<Profile>("/api/v1/business/profile", { auth: "business" })
    .then((profile) => profileStore.set({ userId, profile }))
    .catch(() => profileStore.set({ userId, profile: null }));
}

export function useProfile() {
  const session = useSession("business");
  const state = useSyncExternalStore(profileStore.subscribe, profileStore.get);
  const userId = session?.user.id ?? null;
  // A profile cached for a different user (sign-out, another account) is never shown.
  const profile = state.userId === userId ? state.profile : null;
  return { profile, reload: () => userId && loadProfile(userId) };
}

/** Authenticated business workspace frame. Route protection here is UX only; the API enforces every permission. */
export function AppFrame({
  children,
  title,
  action,
  kicker,
}: {
  children: React.ReactNode;
  title: string;
  action?: React.ReactNode;
  kicker?: string;
}) {
  const { t } = useTranslation();
  const session = useSession("business");
  const location = useLocation();
  const nav = useNavigate();
  const { profile } = useProfile();
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const userId = session?.user.id;
    if (userId && profileStore.get().userId !== userId) {
      profileStore.set({ userId, profile: null });
      loadProfile(userId);
    }
  }, [session?.user.id]);
  useEffect(() => setOpen(false), [location.pathname]);

  if (!session)
    return (
      <Navigate
        to="/business/login"
        replace
        state={{ from: location.pathname }}
      />
    );
  // Navigation follows the role's capabilities from the API; the API enforces them on every request.
  const caps = new Set(profile?.capabilities ?? ["orders.view"]);
  const items = [
    [LayoutDashboard, "dashboard", "/app/dashboard", true],
    [ShoppingBag, "orders", "/app/orders", caps.has("orders.view")],
    [Users, "customers", "/app/customers", caps.has("customers.view")],
    [Wallet, "payments", "/app/payments", caps.has("money.view")],
    [BarChart3, "reports", "/app/reports", caps.has("reports.operational")],
    [Package, "services", "/app/services", caps.has("services.manage")],
    [Store, "marketplace", "/app/marketplace", caps.has("marketplace.view")],
    [Settings, "settings", "/app/settings", caps.has("settings.manage")],
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
    <>
      <div className="appShell">
        <aside className={`side ${open ? "open" : ""}`}>
          <Link className="logo" to="/">
            <img className="logoMark" src="/brand/launder-symbol.svg" alt="" />
            <b>LAUNDER</b>
          </Link>
          <div className="branchSelect">
            <small>{t("biz.workspace").toUpperCase()}</small>
            <b>{profile?.name ?? "…"}</b>
            <span>
              {session.user.name} · {t(`biz.role.${session.user.role}`)}
            </span>
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
                {(
                  kicker ??
                  [profile?.name, profile?.area].filter(Boolean).join(" · ")
                ).toUpperCase()}
              </p>
              <h1>{title}</h1>
            </div>
            {action}
          </div>
          {children}
        </main>
      </div>
    </>
  );
}
