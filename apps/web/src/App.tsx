import { lazy, Suspense, useEffect, useState } from "react";
import {
  Link,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowRight,
  Check,
  Clock3,
  MapPin,
  Menu,
  Search,
  ShieldCheck,
  ShoppingBag,
  Sparkles,
  Star,
  Truck,
  User,
  Wallet,
  X,
} from "lucide-react";
import { api } from "./lib/api";
import { cartTotals, useCart } from "./lib/cart";
import { CardSkeletons, LaundryCard } from "./customer/ui";
import type { LaundryCardData } from "./customer/types";
import Marketplace from "./customer/Marketplace";
import Storefront from "./customer/Storefront";
import CartPage from "./customer/Cart";
import Checkout from "./customer/Checkout";
import Tracking from "./customer/Tracking";
import Account from "./customer/Account";
import { BusinessLanding, Pricing } from "./business/Landing";
import { Lang } from "./business/shell";

// Business and admin workspaces load on demand so marketplace visitors never download them.
const auth = () => import("./business/Auth");
const orders = () => import("./business/Orders");
const customers = () => import("./business/Customers");
const BusinessLogin = lazy(() =>
  auth().then((m) => ({ default: m.BusinessLogin })),
);
const BusinessRegister = lazy(() =>
  auth().then((m) => ({ default: m.BusinessRegister })),
);
const AdminLogin = lazy(() => auth().then((m) => ({ default: m.AdminLogin })));
const Onboarding = lazy(() => import("./business/Onboarding"));
const Dashboard = lazy(() => import("./business/Dashboard"));
const Orders = lazy(() => orders().then((m) => ({ default: m.Orders })));
const walkIn = () => import("./business/WalkIn");
const NewOrder = lazy(() => walkIn().then((m) => ({ default: m.NewOrder })));
const OrderSlip = lazy(() => walkIn().then((m) => ({ default: m.OrderSlip })));
const OrderDetailPage = lazy(() =>
  orders().then((m) => ({ default: m.OrderDetailPage })),
);
const Services = lazy(() => import("./business/Services"));
const MarketplaceBusiness = lazy(() => import("./business/Marketplace"));
const Settings = lazy(() => import("./business/Settings"));
const Customers = lazy(() =>
  customers().then((m) => ({ default: m.Customers })),
);
const Payments = lazy(() => customers().then((m) => ({ default: m.Payments })));
const CustomerProfile = lazy(() =>
  customers().then((m) => ({ default: m.CustomerProfile })),
);
const reports = () => import("./business/Reports");
const ReportsIndex = lazy(() =>
  reports().then((m) => ({ default: m.ReportsIndex })),
);
const ReportPage = lazy(() =>
  reports().then((m) => ({ default: m.ReportPage })),
);
const Admin = lazy(() => import("./admin/Admin"));

function Logo() {
  return (
    <Link className="logo" to="/" aria-label="Launder">
      <img className="logoMark" src="/brand/launder-symbol.svg" alt="" />
      <b>LAUNDER</b>
    </Link>
  );
}

function Header() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  const { count } = cartTotals(useCart());
  useEffect(() => setOpen(false), [pathname]);
  const links = (
    <>
      <Link to="/laundries">{t("nav.find")}</Link>
      <Link to="/how-it-works">{t("nav.how")}</Link>
      <Link to="/for-business">{t("nav.business")}</Link>
      <Link to="/pricing">{t("nav.pricing")}</Link>
    </>
  );
  return (
    <header>
      <Logo />
      <nav aria-label={t("nav.main")}>{links}</nav>
      <div className="headerEnd">
        <Lang />
        <Link className="iconLink" to="/cart" aria-label={t("cart.title")}>
          <ShoppingBag />
          {count > 0 && <span className="badge">{count}</span>}
        </Link>
        <Link className="signin" to="/account">
          <User /> {t("nav.account")}
        </Link>
        <button
          className="menuBtn"
          aria-label={t("biz.menu")}
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          {open ? <X className="hamb" /> : <Menu className="hamb" />}
        </button>
      </div>
      {open && (
        <div className="mobileMenu">
          {links}
          <Link to="/account">{t("nav.account")}</Link>
          <Link to="/business/login">{t("nav.businessSignin")}</Link>
        </div>
      )}
    </header>
  );
}

function Footer() {
  const { t } = useTranslation();
  return (
    <footer>
      <Logo />
      <p>{t("footer.tagline")}</p>
      <div className="footerLinks">
        <Link to="/laundries">{t("nav.find")}</Link>
        <Link to="/for-business">{t("nav.business")}</Link>
        <Link to="/business/login">{t("nav.businessSignin")}</Link>
        <Link to="/pricing">{t("nav.pricing")}</Link>
      </div>
      <small>
        © {new Date().getFullYear()} Launder · {t("footer.rights")}
      </small>
    </footer>
  );
}

function Home() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [popular, setPopular] = useState<LaundryCardData[] | null>(null);
  useEffect(() => {
    api<{ items: LaundryCardData[] }>(
      "/api/v1/marketplace/laundries?sort=rating&page_size=3",
    )
      .then((r) => setPopular(r.items))
      .catch(() => setPopular([]));
  }, []);
  return (
    <main>
      <section className="hero">
        <div className="sun one" />
        <div className="heroCopy">
          <p className="eyebrow">
            <Sparkles /> {t("hero.eyebrow")}
          </p>
          <h1>{t("hero.title")}</h1>
          <p className="lead">{t("hero.body")}</p>
          <form
            className="searchBox"
            role="search"
            onSubmit={(e) => {
              e.preventDefault();
              nav(
                q.trim()
                  ? `/laundries?q=${encodeURIComponent(q.trim())}`
                  : "/laundries",
              );
            }}
          >
            <MapPin />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={t("hero.location")}
              aria-label={t("hero.location")}
            />
            <button>
              <Search />
              {t("hero.search")}
            </button>
          </form>
          <div className="proof">
            <span>
              <ShieldCheck />
              {t("hero.trusted")}
            </span>
            <span>
              <Wallet />
              {t("hero.payments")}
            </span>
            <span>
              <Truck />
              {t("hero.pickup")}
            </span>
          </div>
        </div>
        <div className="heroVisual">
          <div className="arch photoArch">
            <img src="/images/hero-ironing.jpg" alt="" />
          </div>
          <div className="floatCard">
            <Check />
            <div>
              <b>{t("hero.cardTitle")}</b>
              <small>{t("hero.cardBody")}</small>
            </div>
          </div>
          <div className="heroStat heroTime">
            <Clock3 />
            <div>
              <b>{t("hero.statTitle")}</b>
              <small>{t("hero.statBody")}</small>
            </div>
          </div>
        </div>
      </section>
      <section className="section">
        <div className="sectionTitle">
          <div>
            <p className="kicker">KARIBU</p>
            <h2>{t("home.popular")}</h2>
            <p>{t("home.popularSub")}</p>
          </div>
          <Link to="/laundries">
            {t("nav.find")} <ArrowRight />
          </Link>
        </div>
        {popular ? (
          <div className="cards">
            {popular.map((l) => (
              <LaundryCard key={l.id} l={l} />
            ))}
          </div>
        ) : (
          <CardSkeletons />
        )}
      </section>
      <section className="how" id="how">
        <p className="kicker">RAHISI</p>
        <h2>{t("home.steps")}</h2>
        <div className="steps">
          {(
            [
              [Search, "discover"],
              [ShoppingBag, "book"],
              [Star, "track"],
            ] as const
          ).map(([Icon, key], i) => (
            <div className="step" key={key}>
              <span>0{i + 1}</span>
              <Icon />
              <h3>{t(`home.${key}`)}</h3>
              <p>{t(`home.${key}Text`)}</p>
            </div>
          ))}
        </div>
      </section>
      <section className="businessBand">
        <div>
          <p className="kicker">LAUNDER BUSINESS</p>
          <h2>{t("home.bizTitle")}</h2>
          <p>{t("home.bizText")}</p>
          <Link className="lightBtn" to="/for-business">
            {t("home.start")} <ArrowRight />
          </Link>
        </div>
      </section>
      <section className="finalCta">
        <h2>{t("home.cta")}</h2>
        <p>{t("home.ctaSub")}</p>
        <Link to="/laundries">
          {t("hero.search")} <ArrowRight />
        </Link>
      </section>
    </main>
  );
}

function Public({
  children,
  footer = true,
}: {
  children: React.ReactNode;
  footer?: boolean;
}) {
  return (
    <>
      <Header />
      {children}
      {footer && <Footer />}
    </>
  );
}

export default function App() {
  const { pathname } = useLocation();
  useEffect(() => window.scrollTo(0, 0), [pathname]);
  return (
    <Suspense fallback={<div className="tableLoading" aria-busy="true" />}>
      <Routes>
        <Route
          path="/"
          element={
            <Public>
              <Home />
            </Public>
          }
        />
        <Route
          path="/how-it-works"
          element={
            <Public>
              <Home />
            </Public>
          }
        />
        <Route
          path="/laundries"
          element={
            <Public>
              <Marketplace />
            </Public>
          }
        />
        <Route
          path="/marketplace"
          element={
            <Public>
              <Marketplace />
            </Public>
          }
        />
        <Route
          path="/laundries/:slug"
          element={
            <Public footer={false}>
              <Storefront />
            </Public>
          }
        />
        <Route
          path="/cart"
          element={
            <Public footer={false}>
              <CartPage />
            </Public>
          }
        />
        <Route
          path="/checkout"
          element={
            <Public footer={false}>
              <Checkout />
            </Public>
          }
        />
        <Route
          path="/account"
          element={
            <Public>
              <Account />
            </Public>
          }
        />
        <Route
          path="/account/orders"
          element={
            <Public>
              <Account />
            </Public>
          }
        />
        <Route
          path="/account/orders/:id"
          element={
            <Public>
              <Tracking />
            </Public>
          }
        />
        <Route
          path="/for-business"
          element={
            <Public>
              <BusinessLanding />
            </Public>
          }
        />
        <Route
          path="/pricing"
          element={
            <Public>
              <Pricing />
            </Public>
          }
        />
        <Route path="/business/login" element={<BusinessLogin />} />
        <Route path="/business/register" element={<BusinessRegister />} />
        <Route path="/business/onboarding" element={<Onboarding />} />
        <Route path="/app" element={<Dashboard />} />
        <Route path="/app/dashboard" element={<Dashboard />} />
        <Route path="/app/orders" element={<Orders />} />
        <Route path="/app/orders/new" element={<NewOrder />} />
        <Route path="/app/orders/:id" element={<OrderDetailPage />} />
        <Route path="/app/orders/:id/slip" element={<OrderSlip />} />
        <Route path="/app/services" element={<Services />} />
        <Route path="/app/marketplace" element={<MarketplaceBusiness />} />
        <Route path="/app/customers" element={<Customers />} />
        <Route path="/app/customers/:id" element={<CustomerProfile />} />
        <Route path="/app/reports" element={<ReportsIndex />} />
        <Route path="/app/reports/:kind" element={<ReportPage />} />
        <Route path="/app/payments" element={<Payments />} />
        <Route path="/app/settings" element={<Settings />} />
        <Route path="/admin/login" element={<AdminLogin />} />
        <Route path="/admin" element={<Admin />} />
        <Route
          path="*"
          element={
            <Public>
              <Home />
            </Public>
          }
        />
      </Routes>
    </Suspense>
  );
}
