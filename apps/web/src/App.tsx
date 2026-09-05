import { useState } from "react";
import { Routes, Route, Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  MapPin,
  Search,
  Star,
  Sparkles,
  Truck,
  ShieldCheck,
  ArrowRight,
  Plus,
  Minus,
  Check,
  LayoutDashboard,
  ShoppingBag,
  Users,
  Wallet,
  Store,
  Menu,
  Clock3,
} from "lucide-react";
import { laundries, services } from "./data";
import { money } from "./i18n";
import {
  Admin,
  AdminLogin,
  BusinessDashboard,
  BusinessLanding,
  BusinessLogin,
  BusinessRegister,
  GenericModule,
  MarketplaceBusiness,
  NewOrder,
  Onboarding,
  OrderDetail,
  Orders,
  Pricing,
  Services,
} from "./Business";
function Logo() {
  return (
    <Link className="logo" to="/">
      <span className="logoMark">L</span>
      <b>LAUNDER</b>
    </Link>
  );
}
function Lang() {
  const { i18n } = useTranslation();
  return (
    <div className="lang">
      <button
        className={i18n.language === "en" ? "on" : ""}
        onClick={() => i18n.changeLanguage("en")}
      >
        EN
      </button>
      <button
        className={i18n.language === "sw" ? "on" : ""}
        onClick={() => i18n.changeLanguage("sw")}
      >
        SW
      </button>
    </div>
  );
}
function Header() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <header>
      <Logo />
      <nav>
        <Link to="/laundries">{t("nav.find")}</Link>
        <Link to="/how-it-works">{t("nav.how")}</Link>
        <Link to="/for-business">{t("nav.business")}</Link>
        <Link to="/pricing">{t("nav.pricing")}</Link>
      </nav>
      <div className="headerEnd">
        <Lang />
        <Link className="signin" to="/business/login">
          {t("nav.signin")}
        </Link>
        <button className="menuBtn" onClick={() => setOpen(!open)}>
          <Menu className="hamb" />
        </button>
      </div>
      {open && (
        <div className="mobileMenu">
          <Link to="/laundries">{t("nav.find")}</Link>
          <Link to="/how-it-works">{t("nav.how")}</Link>
          <Link to="/for-business">{t("nav.business")}</Link>
          <Link to="/pricing">{t("nav.pricing")}</Link>
          <Link to="/business/login">{t("nav.signin")}</Link>
        </div>
      )}
    </header>
  );
}
function LaundryCard({ l }: { l: (typeof laundries)[0] }) {
  const { t } = useTranslation();
  return (
    <article className="laundryCard">
      <div className="photo" style={{ background: l.color }}>
        <span>{l.initials}</span>
        <div className="pattern" />
        <label>
          <span className="dot" />
          {t("common.open")}
        </label>
      </div>
      <div className="cardBody">
        <div className="spread">
          <div>
            <h3>{l.name}</h3>
            <p>
              <MapPin /> {l.area} · {l.distance} km
            </p>
          </div>
          <strong className="rating">
            <Star /> {l.rating}
          </strong>
        </div>
        <div className="chips">
          <span>Wash & fold</span>
          <span>Dry cleaning</span>
          {l.pickup && (
            <span>
              <Truck /> {t("common.pickup")}
            </span>
          )}
        </div>
        <div className="spread cardFoot">
          <p>
            {t("common.from")} <b>{money(l.price)}</b>
          </p>
          <Link to={"/laundries/" + l.slug}>
            {t("common.view")} <ArrowRight />
          </Link>
        </div>
      </div>
    </article>
  );
}
function Home() {
  const { t } = useTranslation();
  const nav = useNavigate();
  return (
    <>
      <Header />
      <main>
        <section className="hero">
          <div className="sun one" />
          <div className="heroCopy">
            <p className="eyebrow">
              <Sparkles /> {t("hero.eyebrow")}
            </p>
            <h1>{t("hero.title")}</h1>
            <p className="lead">{t("hero.body")}</p>
            <div className="searchBox">
              <MapPin />
              <input placeholder={t("hero.location")} />
              <button onClick={() => nav("/laundries")}>
                <Search />
                {t("hero.search")}
              </button>
            </div>
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
            <div className="arch">
              <div className="washer">
                <div className="washerTop">
                  <i />
                  <i />
                  <i />
                </div>
                <div className="door">
                  <div className="wave">~</div>
                </div>
              </div>
              <span className="leaf l1">*</span>
              <span className="leaf l2">*</span>
            </div>
            <div className="floatCard">
              <Check />
              <div>
                <b>Nguo ziko tayari!</b>
                <small>T-Laundry - Mikocheni</small>
              </div>
            </div>
            <div className="heroStat heroRating">
              <Star />
              <div>
                <b>4.9 / 5</b>
                <small>Trusted local care</small>
              </div>
            </div>
            <div className="heroStat heroTime">
              <Clock3 />
              <div>
                <b>24 hour</b>
                <small>Popular turnaround</small>
              </div>
            </div>
            <div className="heroAreas">
              <span>Masaki</span>
              <span>Mikocheni</span>
              <span>Sinza</span>
              <span>Upanga</span>
            </div>
          </div>
        </section>
        <section className="section">
          <div className="sectionTitle">
            <div>
              <p className="kicker">KARIBU - WELCOME</p>
              <h2>{t("home.popular")}</h2>
              <p>{t("home.popularSub")}</p>
            </div>
            <Link to="/laundries">
              {t("nav.find")} <ArrowRight />
            </Link>
          </div>
          <div className="cards">
            {laundries.map((l) => (
              <LaundryCard key={l.slug} l={l} />
            ))}
          </div>
        </section>
        <section className="how" id="how">
          <p className="kicker">RAHISI - SIMPLE</p>
          <h2>{t("home.steps")}</h2>
          <div className="steps">
            {[
              [Search, "home.discover", "home.discoverText"],
              [ShoppingBag, "home.book", "home.bookText"],
              [Sparkles, "home.track", "home.trackText"],
            ].map(([I, a, b], i) => {
              const Icon = I as typeof Search;
              return (
                <div className="step" key={a as string}>
                  <span>0{i + 1}</span>
                  <Icon />
                  <h3>{t(a as string)}</h3>
                  <p>{t(b as string)}</p>
                </div>
              );
            })}
          </div>
        </section>
        <section className="businessBand">
          <div>
            <p className="kicker">LAUNDER BUSINESS</p>
            <h2>{t("home.bizTitle")}</h2>
            <p>{t("home.bizText")}</p>
            <Link className="lightBtn" to="/business/register">
              {t("home.start")} <ArrowRight />
            </Link>
          </div>
          <div className="miniDash">
            <div className="miniTop">
              <span>T-Laundry</span>
              <b>+24%</b>
            </div>
            <div className="bars">
              {[40, 65, 48, 82, 60, 92, 73].map((h, i) => (
                <i key={i} style={{ height: h + "%" }} />
              ))}
            </div>
          </div>
        </section>
        <section className="finalCta">
          <p className="kicker">SAFI. HARAKA. RAHISI.</p>
          <h2>{t("home.cta")}</h2>
          <p>{t("home.ctaSub")}</p>
          <Link to="/laundries">
            {t("hero.search")} <ArrowRight />
          </Link>
        </section>
      </main>
      <Footer />
    </>
  );
}
function Marketplace() {
  const { t } = useTranslation();
  const [q, setQ] = useState("");
  const list = laundries.filter((l) =>
    (l.name + l.area).toLowerCase().includes(q.toLowerCase()),
  );
  return (
    <>
      <Header />
      <main className="market">
        <div className="marketHead">
          <p className="kicker">DAR ES SALAAM</p>
          <h1>{t("market.title")}</h1>
          <p>{t("market.sub")}</p>
          <div className="marketSearch">
            <Search />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={t("market.search")}
            />
            <button>
              <MapPin />
              {t("market.nearby")}
            </button>
          </div>
        </div>
        <div className="filterrow">
          <button className="active">{t("market.all")}</button>
          <button>Wash & fold</button>
          <button>Dry cleaning</button>
          <button>
            <Truck /> Pickup
          </button>
        </div>
        <p className="resultCount">
          <b>{list.length}</b> {t("market.results")}
        </p>
        <div className="cards">
          {list.map((l) => (
            <LaundryCard key={l.slug} l={l} />
          ))}
        </div>
      </main>
      <Footer />
    </>
  );
}
function Storefront() {
  const { t, i18n } = useTranslation();
  const [cart, setCart] = useState<Record<string, number>>({});
  const nav = useNavigate();
  const total = services.reduce((s, x) => s + (cart[x.id] || 0) * x.price, 0);
  return (
    <>
      <Header />
      <main className="storePage">
        <section className="storeHero">
          <div className="storeLogo">TL</div>
          <div>
            <div className="chips">
              <span>
                <span className="dot" />
                {t("common.open")}
              </span>
              <span>
                <Star />
                4.9 (128)
              </span>
            </div>
            <h1>T-Laundry</h1>
            <p>
              <MapPin /> Mikocheni, Dar es Salaam · 1.2 km
            </p>
            <p>Huduma safi, ya haraka na yenye upendo tangu 2019.</p>
          </div>
        </section>
        <div className="storeGrid">
          <section>
            <p className="kicker">FRESH CARE</p>
            <h2>{t("store.services")}</h2>
            <div className="serviceList">
              {services.map((s) => (
                <div className="service" key={s.id}>
                  <div>
                    <h3>{i18n.language === "sw" ? s.sw : s.name}</h3>
                    <p>
                      {s.time} {t("store.turnaround")}
                    </p>
                    <b>{money(s.price)}</b>
                  </div>
                  <div className="counter">
                    {cart[s.id] > 0 && (
                      <>
                        <button
                          onClick={() =>
                            setCart({ ...cart, [s.id]: cart[s.id] - 1 })
                          }
                        >
                          <Minus />
                        </button>
                        <b>{cart[s.id]}</b>
                      </>
                    )}
                    <button
                      onClick={() =>
                        setCart({ ...cart, [s.id]: (cart[s.id] || 0) + 1 })
                      }
                    >
                      <Plus />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>
          <aside className="cart">
            <h2>{t("store.cart")}</h2>
            {total === 0 ? (
              <div className="empty">
                <ShoppingBag />
                <p>{t("common.empty")}</p>
              </div>
            ) : (
              <>
                {services
                  .filter((s) => cart[s.id])
                  .map((s) => (
                    <div className="spread" key={s.id}>
                      <span>
                        {cart[s.id]} {i18n.language === "sw" ? s.sw : s.name}
                      </span>
                      <b>{money(cart[s.id] * s.price)}</b>
                    </div>
                  ))}
                <hr />
                <div className="spread">
                  <b>{t("common.total")}</b>
                  <strong>{money(total)}</strong>
                </div>
                <button
                  className="primary full"
                  onClick={() => nav("/checkout", { state: { total } })}
                >
                  {t("store.checkout")} <ArrowRight />
                </button>
              </>
            )}
          </aside>
        </div>
      </main>
    </>
  );
}
function Checkout() {
  const { t } = useTranslation();
  const nav = useNavigate();
  return (
    <>
      <Header />
      <main className="checkout">
        <button className="back" onClick={() => nav(-1)}>
          {" "}
          {t("common.back")}
        </button>
        <p className="kicker">T-LAUNDRY · MIKOCHENI</p>
        <h1>{t("checkout.title")}</h1>
        <div className="checkoutGrid">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              nav("/account/orders/LND-24091");
            }}
          >
            <h2>1. {t("checkout.contact")}</h2>
            <label>
              {t("checkout.name")}
              <input required placeholder="Asha Mushi" />
            </label>
            <label>
              {t("checkout.phone")}
              <div className="phone">
                <span>x!x! +255</span>
                <input required placeholder="712 345 678" />
              </div>
            </label>
            <h2>2. {t("checkout.fulfillment")}</h2>
            <div className="choice">
              <label>
                <input type="radio" name="f" defaultChecked /> <Truck /> Pickup
              </label>
              <label>
                <input type="radio" name="f" /> <Store /> Drop-off
              </label>
            </div>
            <label>
              {t("checkout.address")}
              <input required placeholder="Mikocheni B, near Shoppers Plaza" />
            </label>
            <h2>3. {t("checkout.payment")}</h2>
            <div className="choice">
              <label>
                <input type="radio" name="p" defaultChecked /> x{" "}
                {t("checkout.mobile")}
              </label>
              <label>
                <input type="radio" name="p" /> x {t("checkout.cash")}
              </label>
            </div>
            <button className="primary full">
              {t("checkout.place")} <ArrowRight />
            </button>
          </form>
          <aside className="summary">
            <h3>T-Laundry</h3>
            <p>5 Shirt</p>
            <p>2 Trouser</p>
            <hr />
            <div className="spread">
              <b>{t("common.total")}</b>
              <strong>{money(17500)}</strong>
            </div>
            <small>
              <ShieldCheck /> Secure checkout · TZS
            </small>
          </aside>
        </div>
      </main>
    </>
  );
}
function Tracking() {
  const { t } = useTranslation();
  const stages = [
    "received",
    "washing",
    "drying",
    "ironing",
    "quality",
    "ready",
    "delivery",
    "delivered",
  ];
  return (
    <>
      <Header />
      <main className="tracking">
        <div className="successIcon">
          <Check />
        </div>
        <p className="kicker">ORDER LND-24091</p>
        <h1>{t("checkout.success")}</h1>
        <p>{t("checkout.successText")}</p>
        <div className="trackCard">
          <div className="spread">
            <div>
              <small>T-Laundry - Mikocheni</small>
              <h2>{t("orders.track")}</h2>
            </div>
            <span className="status">{t("orders.washing")}</span>
          </div>
          <div className="timeline">
            {stages.map((s, i) => (
              <div className={i <= 1 ? "done" : ""} key={s}>
                <i>{i <= 1 ? <Check /> : i + 1}</i>
                <span>{t("orders." + s)}</span>
              </div>
            ))}
          </div>
        </div>
      </main>
    </>
  );
}
function Footer() {
  const { t } = useTranslation();
  return (
    <footer>
      <Logo />
      <p>{t("footer.tagline")}</p>
      <div className="footerLinks">
        <Link to="/laundries">Marketplace</Link>
        <Link to="/for-business">Business</Link>
        <Link to="/pricing">Pricing</Link>
        <Link to="/admin/login">Admin</Link>
      </div>
      <small>© 2026 Launder · {t("footer.rights")}</small>
    </footer>
  );
}
function PublicPage({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Header />
      {children}
      <Footer />
    </>
  );
}
function CustomerAccount() {
  return (
    <>
      <Header />
      <main className="market">
        <div className="marketHead">
          <p className="kicker">CUSTOMER ACCOUNT</p>
          <h1>Your laundry, all in one place.</h1>
          <p>Track current orders and quickly repeat the services you love.</p>
        </div>
        <section className="orders">
          <div className="spread">
            <div>
              <span className="status">WASHING</span>
              <h2>LND-24091 · T-Laundry</h2>
              <p>5 Shirts, 2 Trousers · Pickup</p>
            </div>
            <div>
              <Link className="outlineBtn" to="/account/orders/LND-24091">
                Track order
              </Link>{" "}
              <Link className="primary" to="/laundries/t-laundry-mikocheni">
                Reorder
              </Link>
            </div>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/how-it-works" element={<Home />} />
      <Route path="/laundries" element={<Marketplace />} />
      <Route path="/marketplace" element={<Marketplace />} />
      <Route path="/laundries/:slug" element={<Storefront />} />
      <Route path="/checkout" element={<Checkout />} />
      <Route path="/account" element={<CustomerAccount />} />
      <Route path="/account/orders" element={<CustomerAccount />} />
      <Route path="/account/orders/:id" element={<Tracking />} />
      <Route
        path="/for-business"
        element={
          <PublicPage>
            <BusinessLanding />
          </PublicPage>
        }
      />
      <Route
        path="/pricing"
        element={
          <PublicPage>
            <Pricing />
          </PublicPage>
        }
      />
      <Route path="/business/login" element={<BusinessLogin />} />
      <Route path="/business/register" element={<BusinessRegister />} />
      <Route path="/business/onboarding" element={<Onboarding />} />
      <Route path="/app" element={<BusinessDashboard />} />
      <Route path="/app/dashboard" element={<BusinessDashboard />} />
      <Route path="/app/orders" element={<Orders />} />
      <Route path="/app/orders/new" element={<NewOrder />} />
      <Route path="/app/orders/:id" element={<OrderDetail />} />
      <Route path="/app/services" element={<Services />} />
      <Route path="/app/marketplace" element={<MarketplaceBusiness />} />
      <Route
        path="/app/customers"
        element={<GenericModule kind="Customers" />}
      />
      <Route path="/app/payments" element={<GenericModule kind="Payments" />} />
      <Route path="/app/settings" element={<GenericModule kind="Settings" />} />
      <Route path="/admin/login" element={<AdminLogin />} />
      <Route path="/admin" element={<Admin />} />
      <Route path="/admin/marketplace-applications" element={<Admin />} />
      <Route path="*" element={<Home />} />
    </Routes>
  );
}
