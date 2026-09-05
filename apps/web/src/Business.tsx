import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowRight,
  BarChart3,
  Check,
  ChevronRight,
  ClipboardList,
  Clock3,
  CreditCard,
  LayoutDashboard,
  LogOut,
  MapPin,
  Menu,
  Package,
  Plus,
  Save,
  Settings,
  ShieldCheck,
  ShoppingBag,
  Store,
  Trash2,
  Truck,
  Users,
  Wallet,
} from "lucide-react";
import { money } from "./i18n";

export const DEMO = {
  businessEmail: "owner@t-laundry.co.tz",
  businessPassword: "Demo123!",
  adminEmail: "admin@launder.co.tz",
  adminPassword: "Admin123!",
};
const copy = {
  en: {
    dashboard: "Dashboard",
    orders: "Orders",
    customers: "Customers",
    services: "Services & pricing",
    payments: "Payments",
    marketplace: "Marketplace",
    settings: "Settings",
    signout: "Sign out",
    workspace: "Workspace",
    branch: "Mikocheni Branch",
    admin: "Platform administration",
    adminTitle: "Secure admin access",
    signin: "Sign in",
    demo: "Demo access",
    review: "Marketplace review",
    approve: "Approve & activate",
    reject: "Reject",
    approved: "Storefront approved",
    pending: "Ready for your decision",
  },
  sw: {
    dashboard: "Dashibodi",
    orders: "Oda",
    customers: "Wateja",
    services: "Huduma na bei",
    payments: "Malipo",
    marketplace: "Soko",
    settings: "Mipangilio",
    signout: "Toka",
    workspace: "Eneo la kazi",
    branch: "Tawi la Mikocheni",
    admin: "Usimamizi wa jukwaa",
    adminTitle: "Ingia kwa usalama",
    signin: "Ingia",
    demo: "Akaunti za majaribio",
    review: "Ukaguzi wa soko",
    approve: "Idhinisha na anzisha",
    reject: "Kataa",
    approved: "Duka limeidhinishwa",
    pending: "Tayari kwa uamuzi wako",
  },
};
function useCopy() {
  const { i18n } = useTranslation();
  return copy[i18n.language === "sw" ? "sw" : "en"];
}
export function BusinessLang() {
  const { i18n } = useTranslation();
  return (
    <div className="lang" aria-label="Language">
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
type Service = {
  id: number | string;
  name: string;
  model: string;
  price: number;
  turnaround: string;
  active: boolean;
};
const initialServices: Service[] = [
  {
    id: 1,
    name: "Shirt",
    model: "PER_ITEM",
    price: 2000,
    turnaround: "24 hours",
    active: true,
  },
  {
    id: 2,
    name: "Trouser",
    model: "PER_ITEM",
    price: 3000,
    turnaround: "24 hours",
    active: true,
  },
  {
    id: 3,
    name: "Suit",
    model: "PER_ITEM",
    price: 8000,
    turnaround: "48 hours",
    active: true,
  },
  {
    id: 4,
    name: "Wash & Fold",
    model: "PER_KG",
    price: 4000,
    turnaround: "24 hours",
    active: true,
  },
];
const orders = [
  [
    "LND-24091",
    "Neema Juma",
    "0712 334 901",
    "MARKETPLACE",
    "WASHING",
    "18,500",
  ],
  ["LND-24090", "Baraka Said", "0754 102 820", "WALK IN", "READY", "32,000"],
  ["LND-24089", "Zawadi Omar", "0687 551 004", "PHONE", "DELIVERED", "12,500"],
  ["LND-24088", "Amina Ally", "0765 440 122", "MARKETPLACE", "NEW", "26,000"],
  ...Array.from({ length: 42 }, (_, i) => {
    const names = [
      "Rehema Msuya",
      "Juma Bakari",
      "Grace Mrema",
      "Kelvin Mushi",
      "Halima Salum",
      "Daniel Mollel",
      "Farida Hamisi",
      "Peter Kweka",
    ];
    const sources = ["WALK IN", "MARKETPLACE", "PHONE", "WHATSAPP"];
    const statuses = [
      "NEW",
      "ACCEPTED",
      "WASHING",
      "DRYING",
      "IRONING",
      "READY",
      "DELIVERED",
    ];
    return [
      `LND-${24087 - i}`,
      names[i % names.length],
      `07${10 + (i % 8)} ${220 + i} ${410 + i}`,
      sources[i % sources.length],
      statuses[i % statuses.length],
      (10500 + (i % 9) * 2750).toLocaleString("en-US"),
    ];
  }),
];

function Pagination({
  page,
  pages,
  total,
  pageSize,
  onPage,
  onPageSize,
}: {
  page: number;
  pages: number;
  total: number;
  pageSize: number;
  onPage: (page: number) => void;
  onPageSize?: (size: number) => void;
}) {
  return (
    <div className="pagination">
      <span>
        Showing {total ? (page - 1) * pageSize + 1 : 0}-
        {Math.min(page * pageSize, total)} of {total}
      </span>
      {onPageSize && (
        <label>
          Rows{" "}
          <select
            value={pageSize}
            onChange={(e) => onPageSize(Number(e.target.value))}
          >
            <option>5</option>
            <option>10</option>
            <option>20</option>
          </select>
        </label>
      )}
      <div>
        <button disabled={page <= 1} onClick={() => onPage(page - 1)}>
          Previous
        </button>
        {Array.from({ length: Math.min(pages, 5) }, (_, i) => {
          const start = Math.max(1, Math.min(page - 2, pages - 4));
          const p = start + i;
          return p <= pages ? (
            <button
              key={p}
              className={p === page ? "active" : ""}
              onClick={() => onPage(p)}
            >
              {p}
            </button>
          ) : null;
        })}
        <button disabled={page >= pages} onClick={() => onPage(page + 1)}>
          Next
        </button>
      </div>
    </div>
  );
}

export function DemoCard() {
  const c = useCopy();
  return (
    <aside className="demoCard">
      <b>{c.demo}</b>
      <p>Business owner · Mmiliki</p>
      <code>{DEMO.businessEmail}</code>
      <code>{DEMO.businessPassword}</code>
      <p>Platform admin · Msimamizi</p>
      <code>{DEMO.adminEmail}</code>
      <code>{DEMO.adminPassword}</code>
    </aside>
  );
}
export function BusinessLanding() {
  return (
    <>
      <section className="businessHero">
        <div>
          <p className="kicker">LAUNDER BUSINESS</p>
          <h1>
            Run your laundry.
            <br />
            <em>Grow with confidence.</em>
          </h1>
          <p>
            One beautiful workspace for orders, customers, services, payments
            and your online storefront made for laundry businesses in Tanzania.
          </p>
          <div className="heroActions">
            <Link className="primary" to="/business/register">
              Start free <ArrowRight />
            </Link>
            <Link className="outlineBtn" to="/business/login">
              Sign in to demo
            </Link>
          </div>
          <div className="proof">
            <span>
              <Check /> No card required
            </span>
            <span>
              <Check /> Free plan forever
            </span>
            <span>
              <Check /> Marketplace optional
            </span>
          </div>
        </div>
        <div className="businessMock">
          <div className="mockHeader">
            <b>T-Laundry</b>
            <span>Live dashboard</span>
          </div>
          <div className="mockMetrics">
            <div>
              <small>Today</small>
              <b>24 orders</b>
            </div>
            <div>
              <small>Revenue</small>
              <b>TZS 286K</b>
            </div>
          </div>
          <div className="mockOrders">
            <i />
            <i />
            <i />
            <i />
          </div>
        </div>
      </section>
      <section className="featureSection">
        <p className="kicker">BUILT FOR THE WAY YOU WORK</p>
        <h2>From the counter to the customer"s door.</h2>
        <div className="featureGrid">
          {[
            [
              ClipboardList,
              "Every order, organised",
              "Create walk-in, phone and marketplace orders. Follow every garment through your workflow.",
            ],
            [
              Users,
              "Know your customers",
              "Customer history, spend and preferences help you deliver a personal service.",
            ],
            [
              Wallet,
              "Money made clear",
              "Track payments, outstanding balances, commissions and daily revenue.",
            ],
            [
              Store,
              "Your digital storefront",
              "Join the marketplace separately when you are ready to reach nearby customers.",
            ],
            [
              Package,
              "Flexible service pricing",
              "Charge per item, per kilogram or create packages that suit your business.",
            ],
            [
              BarChart3,
              "See what is working",
              "Simple, useful insights without the clutter of old enterprise software.",
            ],
          ].map(([I, h, p]) => {
            const Icon = I as typeof Store;
            return (
              <article key={h as string}>
                <Icon />
                <h3>{h as string}</h3>
                <p>{p as string}</p>
              </article>
            );
          })}
        </div>
      </section>
      <Pricing />
      <section className="businessCta">
        <h2>Ready to make every laundry day run smoothly?</h2>
        <p>Join growing laundry businesses across Tanzania.</p>
        <Link className="lightBtn" to="/business/register">
          Create your free account <ArrowRight />
        </Link>
      </section>
    </>
  );
}
export function Pricing() {
  return (
    <section className="pricingPage" id="pricing">
      <div className="pricingHead">
        <p className="kicker">SIMPLE, HONEST PRICING</p>
        <h1>Start free. Grow when you"re ready.</h1>
        <p>
          Marketplace participation is separate from your business subscription.
          No surprises.
        </p>
      </div>
      <div className="priceGrid">
        <article>
          <span className="planTag">FREE</span>
          <h2>TZS 0</h2>
          <p>per month · forever</p>
          <ul>
            {[
              "Order management",
              "Customer records",
              "Services & pricing",
              "Basic dashboard",
              "Up to 3 staff accounts",
            ].map((x) => (
              <li key={x}>
                <Check />
                {x}
              </li>
            ))}
          </ul>
          <Link className="outlineBtn full" to="/business/register">
            Start for free
          </Link>
        </article>
        <article className="featuredPlan">
          <span className="planTag">PRO · COMING SOON</span>
          <h2>Built to scale</h2>
          <p>For established, growing laundries</p>
          <ul>
            {[
              "Everything in Free",
              "Advanced analytics",
              "Expanded staff controls",
              "Multi-branch insights",
              "Advanced reports",
            ].map((x) => (
              <li key={x}>
                <Check />
                {x}
              </li>
            ))}
          </ul>
          <button className="primary full">Join the waitlist</button>
        </article>
        <article>
          <span className="planTag marketTag">MARKETPLACE</span>
          <h2>Pay as you earn</h2>
          <p>commission on marketplace orders</p>
          <ul>
            {[
              "Public online storefront",
              "Nearby customer discovery",
              "Online orders",
              "Pickup configuration",
              "Reviews and ratings",
            ].map((x) => (
              <li key={x}>
                <Check />
                {x}
              </li>
            ))}
          </ul>
          <Link className="outlineBtn full" to="/business/register">
            Join Launder
          </Link>
        </article>
      </div>
      <p className="pricingNote">
        <ShieldCheck /> Your Business plan never determines whether you can join
        the Marketplace.
      </p>
    </section>
  );
}

function AuthShell({ kind }: { kind: "login" | "register" }) {
  const { i18n } = useTranslation();
  const sw = i18n.language === "sw";
  const nav = useNavigate();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    if (kind === "login") {
      setLoading(true);
      setError("");
      try {
        const response = await fetch(
          "http://127.0.0.1:8000/api/v1/auth/login",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              email: fd.get("email"),
              password: fd.get("password"),
            }),
          },
        );
        const data = await response.json();
        if (!response.ok || data.user?.role !== "BUSINESS_OWNER")
          throw new Error(
            sw
              ? "Barua pepe au nenosiri si sahihi."
              : "Incorrect email or password.",
          );
        localStorage.setItem("launder-access-token", data.access_token);
        localStorage.setItem("launder-demo-auth", "business");
        nav("/app/dashboard");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to sign in.");
      } finally {
        setLoading(false);
      }
      return;
    }
    setLoading(true);
    setError("");
    try {
      const response = await fetch(
        "http://127.0.0.1:8000/api/v1/auth/business/register",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            full_name: fd.get("name"),
            business_name: fd.get("business"),
            phone: fd.get("phone"),
            email: fd.get("email"),
            password: fd.get("password"),
          }),
        },
      );
      const data = await response.json();
      if (!response.ok)
        throw new Error(data.detail || "Unable to create business account.");
      localStorage.setItem("launder-access-token", data.access_token);
      localStorage.setItem("launder-demo-auth", "business");
      nav("/business/onboarding");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to create account.",
      );
    } finally {
      setLoading(false);
    }
  }
  return (
    <main className="authPage">
      <div className="authUtility">
        <BusinessLang />
      </div>
      <Link to="/" className="authLogo">
        <span className="logoMark">L</span>
        <b>LAUNDER</b>
      </Link>
      <section
        className={`authPanel ${kind === "login" ? "soloAuth" : "registerAuth"}`}
      >
        <div>
          <p className="kicker">LAUNDER BUSINESS</p>
          <h1>
            {kind === "login"
              ? sw
                ? "Karibu tena."
                : "Welcome back."
              : sw
                ? "Jenga biashara bora ya laundry."
                : "Build a better laundry business."}
          </h1>
          <p>
            {kind === "login"
              ? sw
                ? "Ingia ili kuendelea kwenye eneo lako la T-Laundry."
                : "Sign in to continue to your T-Laundry workspace."
              : sw
                ? "Anza bure, panga shughuli na ufikie wateja zaidi ukiwa tayari."
                : "Start free, organise your operations and reach more customers when you are ready."}
          </p>
          <form onSubmit={submit}>
            {kind === "register" && (
              <div className="registrationFields">
                <label>
                  {sw ? "Jina kamili" : "Full name"}
                  <input name="name" required placeholder="Asha Mushi" />
                </label>
                <label>
                  {sw ? "Jina la biashara" : "Business name"}
                  <input name="business" required placeholder="T-Laundry" />
                </label>
                <label>
                  {sw ? "Namba ya simu" : "Phone number"}
                  <input name="phone" required placeholder="+255 712 345 678" />
                </label>
              </div>
            )}
            <label>
              {sw ? "Barua pepe" : "Email address"}
              <input
                name="email"
                type="email"
                required
                defaultValue=""
                placeholder="you@business.co.tz"
              />
            </label>
            <label>
              {sw ? "Nenosiri" : "Password"}
              <input
                name="password"
                type="password"
                required
                defaultValue=""
                minLength={8}
              />
            </label>
            {error && <p className="formError">{error}</p>}
            <button className="primary full" disabled={loading}>
              {loading
                ? sw
                  ? "Inaingia..."
                  : "Signing in..."
                : kind === "login"
                  ? sw
                    ? "Ingia"
                    : "Sign in"
                  : sw
                    ? "Fungua akaunti ya biashara"
                    : "Create business account"}{" "}
              <ArrowRight />
            </button>
          </form>
          <p className="authSwap">
            {kind === "login" ? (
              <>
                New to Launder?{" "}
                <Link to="/business/register">Create an account</Link>
              </>
            ) : (
              <>
                Already registered? <Link to="/business/login">Sign in</Link>
              </>
            )}
          </p>
        </div>
        {kind === "register" && (
          <div className="authPromise">
            <ShieldCheck />
            <h3>Your business stays yours.</h3>
            <p>
              Marketplace enrollment is always optional. Use Launder Business
              independently on the Free plan.
            </p>
          </div>
        )}
      </section>
    </main>
  );
}
export const BusinessLogin = () => <AuthShell kind="login" />;
export const BusinessRegister = () => <AuthShell kind="register" />;

const onboardingSteps = [
  "Business details",
  "Verification",
  "Branch & location",
  "Services & pricing",
  "Operating hours",
  "Pickup & delivery",
  "Payout details",
  "Marketplace agreement",
  "Submit for review",
];
export function Onboarding() {
  const { i18n } = useTranslation();
  const sw = i18n.language === "sw";
  const displayedSteps = sw
    ? [
        "Maelezo ya biashara",
        "Uthibitishaji",
        "Tawi na eneo",
        "Huduma na bei",
        "Saa za kazi",
        "Kuchukua na kupeleka",
        "Maelezo ya malipo",
        "Makubaliano ya soko",
        "Tuma kwa ukaguzi",
      ]
    : onboardingSteps;
  const [step, setStep] = useState(0);
  const nav = useNavigate();
  useEffect(() => {
    const token = localStorage.getItem("launder-access-token");
    if (!token) return;
    fetch("http://127.0.0.1:8000/api/v1/business/onboarding", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data) setStep(Math.max(0, (data.current_step || 1) - 1));
      });
  }, []);
  const fields = [
    <>
      <label>
        Business name
        <input name="business_name" defaultValue="T-Laundry" />
      </label>
      <label>
        Business description
        <textarea
          name="description"
          defaultValue="Premium, dependable laundry care for busy Dar es Salaam households."
        />
      </label>
      <div className="twoFields">
        <label>
          Business phone
          <input name="business_phone" defaultValue="+255 712 345 678" />
        </label>
        <label>
          Business email
          <input name="business_email" defaultValue="hello@t-laundry.co.tz" />
        </label>
      </div>
    </>,
    <>
      <div className="uploadBox">
        <ShieldCheck />
        <h3>Business verification</h3>
        <p>Upload your BRELA certificate or business licence.</p>
        <button type="button" className="outlineBtn">
          Choose document
        </button>
      </div>
    </>,
    <>
      <label>
        Branch name
        <input name="branch_name" defaultValue="Mikocheni Branch" />
      </label>
      <label>
        Address
        <input name="address" defaultValue="Mikocheni B, Dar es Salaam" />
      </label>
      <div className="mapMock">
        <MapPin />
        <span>T-Laundry · Mikocheni</span>
      </div>
    </>,
    <>
      <p>Add your first services. You can edit full pricing later.</p>
      {initialServices.slice(0, 3).map((s) => (
        <div className="inlineService" key={s.id}>
          <input defaultValue={s.name} />
          <input type="number" defaultValue={s.price} />
          <span>TZS</span>
        </div>
      ))}
    </>,
    <>
      <div className="hoursList">
        {["Monday   Friday", "Saturday", "Sunday"].map((d, i) => (
          <div key={d}>
            <b>{d}</b>
            <input type="time" defaultValue={i === 2 ? "09:00" : "08:00"} />
            <span>to</span>
            <input type="time" defaultValue={i === 2 ? "15:00" : "18:00"} />
          </div>
        ))}
      </div>
    </>,
    <>
      <div className="choice">
        <label>
          <input type="checkbox" defaultChecked />
          <Truck /> Customer pickup
        </label>
        <label>
          <input type="checkbox" defaultChecked />
          <Store /> Customer drop-off
        </label>
      </div>
      <label>
        Pickup radius (km)
        <input type="number" defaultValue="8" />
      </label>
      <label>
        Pickup fee (TZS)
        <input type="number" defaultValue="2500" />
      </label>
    </>,
    <>
      <label>
        Mobile money provider
        <select defaultValue="M-Pesa">
          <option>M-Pesa</option>
          <option>Airtel Money</option>
          <option>Mixx by Yas</option>
        </select>
      </label>
      <label>
        Payout phone
        <input defaultValue="+255 712 345 678" />
      </label>
      <p className="helper">
        Payout details are encrypted and only used for verified settlements.
      </p>
    </>,
    <>
      <div className="agreement">
        <Store />
        <h3>Marketplace is optional</h3>
        <p>
          Submitting makes T-Laundry eligible for review; it will not be
          published until Launder approves and activates the storefront.
        </p>
        <label>
          <input type="checkbox" required /> I agree to the marketplace terms
          and commission schedule.
        </label>
      </div>
    </>,
    <>
      <div className="reviewBox">
        <Check />
        <h2>T-Laundry is ready for review</h2>
        <p>
          We'll review your verification, service quality and pickup area. Your
          Launder Business workspace is ready now.
        </p>
        {onboardingSteps.slice(0, -1).map((x) => (
          <span key={x}>
            <Check />
            {x}
          </span>
        ))}
      </div>
    </>,
  ];
  async function next(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const token = localStorage.getItem("launder-access-token");
    const values = Object.fromEntries(new FormData(e.currentTarget).entries());
    if (token) {
      const response = await fetch(
        "http://127.0.0.1:8000/api/v1/business/onboarding",
        {
          method: "PUT",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            step: step + 1,
            data: values,
            completed: step === 8,
          }),
        },
      );
      if (!response.ok) return;
    }
    if (step === 8) {
      localStorage.setItem("launder-onboarding", "complete");
      nav("/app/dashboard");
    } else setStep(step + 1);
  }
  return (
    <main className="onboarding">
      <aside>
        <Link to="/" className="authLogo">
          <span className="logoMark">L</span>
          <b>LAUNDER</b>
        </Link>
        <p>Business setup</p>
        {displayedSteps.map((s, i) => (
          <button
            className={i === step ? "current" : i < step ? "complete" : ""}
            key={s}
            onClick={() => i <= step && setStep(i)}
          >
            <i>{i < step ? <Check /> : i + 1}</i>
            <span>{s}</span>
          </button>
        ))}
      </aside>
      <section>
        <div className="onboardTop">
          <span>
            {sw ? "Hatua" : "Step"} {step + 1} {sw ? "kati ya" : "of"} 9
          </span>
          <BusinessLang />
          <Link to="/app/dashboard">
            {sw ? "Hifadhi na malizia baadaye" : "Save & finish later"}
          </Link>
        </div>
        <form onSubmit={next}>
          <p className="kicker">SET UP T-LAUNDRY</p>
          <h1>{displayedSteps[step]}</h1>
          <p className="onboardIntro">
            Tell customers and your team what they need to know. You can update
            this anytime.
          </p>
          <div className="onboardStepBody">{fields[step]}</div>
          <div className="formActions">
            {step > 0 && (
              <button
                type="button"
                className="outlineBtn"
                onClick={() => setStep(step - 1)}
              >
                {sw ? "Rudi" : "Back"}
              </button>
            )}
            <button className="primary">
              {step === 8
                ? sw
                  ? "Fungua dashibodi"
                  : "Open my dashboard"
                : sw
                  ? "Hifadhi na endelea"
                  : "Save & continue"}
              <ChevronRight />
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}

const navItems = [
  [LayoutDashboard, "Dashboard", "/app/dashboard"],
  [ShoppingBag, "Orders", "/app/orders"],
  [Users, "Customers", "/app/customers"],
  [Package, "Services & pricing", "/app/services"],
  [Wallet, "Payments", "/app/payments"],
  [Store, "Marketplace", "/app/marketplace"],
  [Settings, "Settings", "/app/settings"],
] as const;
export function AppFrame({
  children,
  title,
  action,
}: {
  children: React.ReactNode;
  title: string;
  action?: React.ReactNode;
}) {
  const c = useCopy();
  const localizedNav = [
    [LayoutDashboard, c.dashboard, "/app/dashboard"],
    [ShoppingBag, c.orders, "/app/orders"],
    [Users, c.customers, "/app/customers"],
    [Package, c.services, "/app/services"],
    [Wallet, c.payments, "/app/payments"],
    [Store, c.marketplace, "/app/marketplace"],
    [Settings, c.settings, "/app/settings"],
  ] as const;
  return (
    <div className="appShell">
      <aside className="side">
        <Link className="logo" to="/">
          <span className="logoMark">L</span>
          <b>LAUNDER</b>
        </Link>
        <div className="branchSelect">
          <small>{c.workspace.toUpperCase()}</small>
          <b>T-Laundry</b>
          <span>{c.branch}</span>
        </div>
        {localizedNav.map(([I, s, to]) => {
          const Icon = I;
          return (
            <NavLink
              to={to}
              key={to}
              className={({ isActive }) => (isActive ? "sel" : "")}
            >
              <Icon />
              {s}
            </NavLink>
          );
        })}
        <NavLink to="/business/login" className="logout">
          <LogOut /> {c.signout}
        </NavLink>
        <div className="sideLanguage">
          <small>LANGUAGE · LUGHA</small>
          <BusinessLang />
        </div>
      </aside>
      <main className="dash">
        <div className="mobileAppTop">
          <Menu />
          <b>T-Laundry</b>
        </div>
        <div className="dashTop">
          <div>
            <p className="kicker">T-LAUNDRY · MIKOCHENI</p>
            <h1>{title}</h1>
          </div>
          {action}
        </div>
        {children}
      </main>
    </div>
  );
}
export function BusinessDashboard() {
  const { i18n } = useTranslation();
  const sw = i18n.language === "sw";
  const nav = useNavigate();
  return (
    <AppFrame title={sw ? "Habari za mchana, Asha" : "Good afternoon, Asha"}>
      <p className="dashSub">
        {sw
          ? "Hivi ndivyo T-Laundry inavyoendelea leo."
          : "Here's how T-Laundry is doing today."}
      </p>
      <div className="metrics">
        {[
          [sw ? "Oda za leo" : "Today's orders", "24", "+12%"],
          [sw ? "Mapato ya leo" : "Today's revenue", money(286000), "+18%"],
          [sw ? "Tayari kuchukuliwa" : "Ready for collection", "8", ""],
          [sw ? "Malipo yanayodaiwa" : "Outstanding", money(74000), ""],
        ].map((x) => (
          <div className="metric" key={x[0]}>
            <p>{x[0]}</p>
            <h2>{x[1]}</h2>
            <small>{x[2]}</small>
          </div>
        ))}
      </div>
      <div className="dashGrid">
        <section className="chart">
          <div className="spread">
            <h2>Revenue this week</h2>
            <b>{money(1240000)}</b>
          </div>
          <div className="bigBars">
            {[35, 46, 39, 64, 52, 76, 87].map((x, i) => (
              <div key={i}>
                <i style={{ height: x + "%" }} />
                <span>
                  {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][i]}
                </span>
              </div>
            ))}
          </div>
        </section>
        <section className="quick">
          <h2>Quick actions</h2>
          {[
            ["New walk-in order", "/app/orders/new"],
            ["Add a customer", "/app/customers"],
            ["Add a service", "/app/services"],
            ["Marketplace status", "/app/marketplace"],
          ].map((x) => (
            <button key={x[0]} onClick={() => nav(x[1])}>
              {x[0]}
              <ArrowRight />
            </button>
          ))}
        </section>
      </div>
      <div className="insightGrid">
        <section className="workspaceCard monthChart">
          <div className="spread">
            <div>
              <p className="kicker">
                {sw ? "MWEZI KWA MWEZI" : "MONTH ON MONTH"}
              </p>
              <h2>{sw ? "Ukuaji wa mapato" : "Revenue growth"}</h2>
            </div>
            <span className="growthBadge">+18.4%</span>
          </div>
          <div className="monthBars">
            {[
              ["Apr", 58, 820],
              ["May", 66, 940],
              ["Jun", 61, 890],
              ["Jul", 78, 1110],
              ["Aug", 84, 1240],
              ["Sep", 96, 1468],
            ].map(([m, h, v]) => (
              <div key={m}>
                <b>{money(Number(v) * 1000)}</b>
                <i style={{ height: `${h}%` }} />
                <span>{m}</span>
              </div>
            ))}
          </div>
        </section>
        <section className="workspaceCard sourceMix">
          <p className="kicker">{sw ? "CHANZO CHA ODA" : "ORDER MIX"}</p>
          <h2>{sw ? "Wateja wanatoka wapi" : "Where customers come from"}</h2>
          <div className="donut">
            <strong>
              184<small>{sw ? "oda" : "orders"}</small>
            </strong>
          </div>
          <div className="legend">
            <span>
              <i className="marketplaceDot" /> Marketplace <b>46%</b>
            </span>
            <span>
              <i className="walkinDot" /> Walk-in <b>38%</b>
            </span>
            <span>
              <i className="phoneDot" /> Phone & WhatsApp <b>16%</b>
            </span>
          </div>
        </section>
      </div>
      <section className="eodReport">
        <div>
          <p className="kicker">
            {sw ? "RIPOTI YA MWISHO WA SIKU" : "END-OF-DAY REPORT"}
          </p>
          <h2>{sw ? "Muhtasari wa leo" : "Today's close"}</h2>
          <p>
            {sw
              ? "Takwimu za shughuli hadi saa 18:42"
              : "Operational snapshot through 18:42"}
          </p>
        </div>
        <div className="eodStat">
          <span>{sw ? "Oda zilizokamilika" : "Completed orders"}</span>
          <b>19 / 24</b>
          <small>79% completion</small>
        </div>
        <div className="eodStat">
          <span>{sw ? "Malipo yaliyokusanywa" : "Payments collected"}</span>
          <b>{money(248000)}</b>
          <small>{money(38000)} pending</small>
        </div>
        <div className="eodStat">
          <span>{sw ? "Wastani wa oda" : "Average order"}</span>
          <b>{money(15053)}</b>
          <small>+6.2% vs yesterday</small>
        </div>
        <button className="outlineBtn">
          {sw ? "Tazama ripoti kamili" : "View full report"}
          <ArrowRight />
        </button>
      </section>
      <OrderTable />
    </AppFrame>
  );
}
function OrderTable() {
  const [page, setPage] = useState(1);
  const pageSize = 5;
  const [visible, setVisible] = useState<string[][]>([]);
  const [total, setTotal] = useState(0);
  useEffect(() => {
    const token = localStorage.getItem("launder-access-token");
    fetch(
      `http://127.0.0.1:8000/api/v1/business/orders?page=${page}&page_size=${pageSize}`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data) {
          setTotal(data.total);
          setVisible(
            data.items.map((x: any) => [
              x.order_number,
              x.customer_name,
              x.phone,
              x.source,
              x.status,
              Number(x.total).toLocaleString("en-US"),
            ]),
          );
        }
      });
  }, [page]);
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <section className="orders">
      <div className="spread">
        <h2>Recent orders</h2>
        <Link to="/app/orders">
          View all <ArrowRight />
        </Link>
      </div>
      <div className="tableHead">
        <span>Order</span>
        <span>Customer</span>
        <span>Source</span>
        <span>Status</span>
        <span>Total</span>
      </div>
      {visible.map((r) => (
        <Link to={"/app/orders/" + r[0]} className="order" key={r[0]}>
          <b>{r[0]}</b>
          <span>{r[1]}</span>
          <span>{r[3]}</span>
          <span className={"pill " + r[4].toLowerCase()}>{r[4]}</span>
          <span>TZS {r[5]}</span>
        </Link>
      ))}
      <Pagination
        page={page}
        pages={pages}
        total={total}
        pageSize={pageSize}
        onPage={setPage}
      />
    </section>
  );
}
export function Orders() {
  const c = useCopy();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("ALL");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [visible, setVisible] = useState<string[][]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const token = localStorage.getItem("launder-access-token") || "";
  useEffect(() => {
    const timer = setTimeout(async () => {
      setLoading(true);
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
      });
      if (q) params.set("q", q);
      if (status !== "ALL") params.set("status", status);
      const response = await fetch(
        `http://127.0.0.1:8000/api/v1/business/orders?${params}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (response.ok) {
        const data = await response.json();
        setTotal(data.total);
        setVisible(
          data.items.map((x: any) => [
            x.order_number,
            x.customer_name,
            x.phone,
            x.source,
            x.status,
            Number(x.total).toLocaleString("en-US"),
          ]),
        );
      }
      setLoading(false);
    }, 250);
    return () => clearTimeout(timer);
  }, [q, status, page, pageSize]);
  const pages = Math.max(1, Math.ceil(total / pageSize));
  async function exportOrders() {
    const params = new URLSearchParams({ page: "1", page_size: "100" });
    if (q) params.set("q", q);
    if (status !== "ALL") params.set("status", status);
    const response = await fetch(
      `http://127.0.0.1:8000/api/v1/business/orders?${params}`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    if (!response.ok) return;
    const data = await response.json();
    const list = data.items.map((x: any) => [
      x.order_number,
      x.customer_name,
      x.phone,
      x.source,
      x.status,
      x.total,
    ]);
    const header = [
      "Order",
      "Customer",
      "Phone",
      "Source",
      "Status",
      "Total TZS",
    ];
    const csv = [header, ...list]
      .map((row) =>
        row
          .map((value: unknown) => `"${String(value).replaceAll('"', '""')}"`)
          .join(","),
      )
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `t-laundry-orders-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }
  return (
    <AppFrame
      title={c.orders}
      action={
        <Link className="primary" to="/app/orders/new">
          <Plus /> New order
        </Link>
      }
    >
      <div className="toolbar">
        <input
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
          placeholder="Search order, customer or phone..."
        />
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}
        >
          <option value="ALL">All statuses</option>
          <option value="NEW">New</option>
          <option value="ACCEPTED">Accepted</option>
          <option value="WASHING">Washing</option>
          <option value="DRYING">Drying</option>
          <option value="IRONING">Ironing</option>
          <option value="READY">Ready</option>
          <option value="DELIVERED">Delivered</option>
        </select>
        <button className="outlineBtn exportBtn" onClick={exportOrders}>
          Export CSV
        </button>
      </div>
      <section className="orders">
        <div className="tableHead">
          <span>Order</span>
          <span>Customer</span>
          <span>Source</span>
          <span>Status</span>
          <span>Total</span>
        </div>
        {loading ? (
          <div className="tableLoading">Loading orders...</div>
        ) : (
          visible.map((r) => (
            <Link to={"/app/orders/" + r[0]} className="order" key={r[0]}>
              <b>{r[0]}</b>
              <span>
                {r[1]}
                <small>{r[2]}</small>
              </span>
              <span>{r[3]}</span>
              <span className={"pill " + r[4].toLowerCase()}>{r[4]}</span>
              <b>TZS {r[5]}</b>
            </Link>
          ))
        )}
        <Pagination
          page={page}
          pages={pages}
          total={total}
          pageSize={pageSize}
          onPage={setPage}
          onPageSize={(size) => {
            setPageSize(size);
            setPage(1);
          }}
        />
      </section>
    </AppFrame>
  );
}
export function NewOrder() {
  const { i18n } = useTranslation();
  const sw = i18n.language === "sw";
  const nav = useNavigate();
  const [total, setTotal] = useState(0);
  return (
    <AppFrame title={sw ? "Oda mpya ya dukani" : "New walk-in order"}>
      <form
        className="workspaceForm"
        onSubmit={async (e) => {
          e.preventDefault();
          const fd = new FormData(e.currentTarget);
          const token = localStorage.getItem("launder-access-token");
          const response = await fetch(
            "http://127.0.0.1:8000/api/v1/business/orders",
            {
              method: "POST",
              headers: {
                Authorization: `Bearer ${token}`,
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                customer_name: fd.get("customer_name"),
                phone: fd.get("phone"),
                source: "WALK_IN",
                total,
                notes: fd.get("notes"),
              }),
            },
          );
          if (response.ok) nav("/app/orders");
        }}
      >
        <h2>Customer</h2>
        <div className="twoFields">
          <label>
            Name
            <input name="customer_name" required placeholder="Customer name" />
          </label>
          <label>
            Phone
            <input name="phone" required placeholder="+255 7xx xxx xxx" />
          </label>
        </div>
        <h2>Services</h2>
        {initialServices.map((s) => (
          <label className="selectService" key={s.id}>
            <input
              type="checkbox"
              onChange={(e) =>
                setTotal(total + (e.target.checked ? s.price : -s.price))
              }
            />
            <span>
              <b>{s.name}</b>
              <small>
                {s.model.replace("_", " ")} · {s.turnaround}
              </small>
            </span>
            <strong>{money(s.price)}</strong>
          </label>
        ))}
        <label>
          Order notes
          <textarea
            name="notes"
            placeholder="Stain notes, fabric care instructions..."
          />
        </label>
        <div className="formTotal">
          <span>Total</span>
          <b>{money(total)}</b>
        </div>
        <button className="primary">
          Create order <ArrowRight />
        </button>
      </form>
    </AppFrame>
  );
}
export function OrderDetail() {
  const [status, setStatus] = useState("WASHING");
  const flow = [
    "NEW",
    "ACCEPTED",
    "RECEIVED",
    "WASHING",
    "DRYING",
    "IRONING",
    "QUALITY CHECK",
    "READY",
    "DELIVERED",
    "COMPLETED",
  ];
  return (
    <AppFrame title="Order LND-24091">
      <div className="detailGrid">
        <section className="workspaceCard">
          <div className="spread">
            <div>
              <p className="kicker">NEEMA JUMA · MARKETPLACE</p>
              <h2>5 Shirts, 2 Trousers</h2>
            </div>
            <span className="pill washing">{status}</span>
          </div>
          <div className="orderTimeline">
            {flow.map((s, i) => (
              <button
                key={s}
                className={flow.indexOf(status) >= i ? "done" : ""}
                onClick={() => setStatus(s)}
              >
                <i>{flow.indexOf(status) >= i ? <Check /> : i + 1}</i>
                <span>{s}</span>
              </button>
            ))}
          </div>
        </section>
        <aside className="workspaceCard">
          <h3>Order summary</h3>
          <p className="spread">
            <span>5 Shirt</span>
            <b>{money(10000)}</b>
          </p>
          <p className="spread">
            <span>2 Trouser</span>
            <b>{money(6000)}</b>
          </p>
          <p className="spread">
            <span>Pickup</span>
            <b>{money(2500)}</b>
          </p>
          <hr />
          <p className="spread">
            <b>Total</b>
            <strong>{money(18500)}</strong>
          </p>
          <button
            className="primary full"
            onClick={() =>
              setStatus(
                flow[Math.min(flow.indexOf(status) + 1, flow.length - 1)],
              )
            }
          >
            Move to next status
          </button>
        </aside>
      </div>
    </AppFrame>
  );
}
export function Services() {
  const c = useCopy();
  const [list, setList] = useState(() => {
    try {
      return (
        JSON.parse(localStorage.getItem("launder-services") || "null") ||
        initialServices
      );
    } catch {
      return initialServices;
    }
  });
  const [editing, setEditing] = useState<Service | null>(null);
  const serviceToken = localStorage.getItem("launder-access-token") || "";
  useEffect(() => {
    fetch("http://127.0.0.1:8000/api/v1/business/services", {
      headers: { Authorization: `Bearer ${serviceToken}` },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data)
          setList(
            data.map((x: any) => ({
              id: x.id,
              name: x.name,
              model: x.pricing_model,
              price: x.price,
              turnaround: `${x.turnaround_hours} hours`,
              active: x.active,
            })),
          );
      });
  }, []);
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const row = {
      id: editing?.id || Date.now(),
      name: String(fd.get("name")),
      model: String(fd.get("model")),
      price: Number(fd.get("price")),
      turnaround: String(fd.get("turnaround")),
      active: true,
    };
    const payload = {
      name: row.name,
      description: "",
      pricing_model: row.model,
      price: row.price,
      turnaround_hours: parseInt(row.turnaround) || 24,
      active: row.active,
    };
    const isExisting = typeof editing?.id === "string";
    const response = await fetch(
      `http://127.0.0.1:8000/api/v1/business/services${isExisting ? `/${editing?.id}` : ""}`,
      {
        method: isExisting ? "PUT" : "POST",
        headers: {
          Authorization: `Bearer ${serviceToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      },
    );
    if (!response.ok) return;
    const saved = await response.json();
    row.id = saved.id;
    const next = isExisting
      ? list.map((x: Service) => (x.id === editing?.id ? row : x))
      : [...list, row];
    setList(next);
    localStorage.setItem("launder-services", JSON.stringify(next));
    setEditing(null);
  }
  return (
    <AppFrame
      title={c.services}
      action={
        <button
          className="primary"
          onClick={() =>
            setEditing({
              id: 0,
              name: "",
              model: "PER_ITEM",
              price: 0,
              turnaround: "24 hours",
              active: true,
            })
          }
        >
          <Plus /> Add service
        </button>
      }
    >
      <p className="dashSub">
        Set what you offer and exactly how customers are charged.
      </p>
      {editing && (
        <form className="inlineEditor" onSubmit={save}>
          <div className="spread">
            <h2>{editing.id ? "Edit service" : "New service"}</h2>
            <button
              type="button"
              className="iconBtn"
              onClick={() => setEditing(null)}
            >
              {" "}
            </button>
          </div>
          <div className="fourFields">
            <label>
              Service name
              <input name="name" required defaultValue={editing.name} />
            </label>
            <label>
              Pricing model
              <select name="model" defaultValue={editing.model}>
                <option value="PER_ITEM">Per item</option>
                <option value="PER_KG">Per kilogram</option>
                <option value="PACKAGE">Package</option>
              </select>
            </label>
            <label>
              Price (TZS)
              <input
                name="price"
                required
                type="number"
                min="0"
                defaultValue={editing.price}
              />
            </label>
            <label>
              Turnaround
              <input name="turnaround" defaultValue={editing.turnaround} />
            </label>
          </div>
          <button className="primary">
            <Save /> Save service
          </button>
        </form>
      )}
      <section className="serviceTable">
        <div className="tableHead serviceCols">
          <span>Service</span>
          <span>Pricing model</span>
          <span>Turnaround</span>
          <span>Price</span>
          <span>Status</span>
          <span></span>
        </div>
        {list.map((s: Service) => (
          <div className="serviceRow serviceCols" key={s.id}>
            <b>{s.name}</b>
            <span>{s.model.replace("_", " ")}</span>
            <span>{s.turnaround}</span>
            <strong>{money(s.price)}</strong>
            <button
              className={"toggle " + (s.active ? "on" : "")}
              onClick={() => {
                const next = list.map((x: Service) =>
                  x.id === s.id ? { ...x, active: !x.active } : x,
                );
                setList(next);
                localStorage.setItem("launder-services", JSON.stringify(next));
                if (typeof s.id === "string")
                  fetch(
                    `http://127.0.0.1:8000/api/v1/business/services/${s.id}`,
                    {
                      method: "PUT",
                      headers: {
                        Authorization: `Bearer ${serviceToken}`,
                        "Content-Type": "application/json",
                      },
                      body: JSON.stringify({
                        name: s.name,
                        description: "",
                        pricing_model: s.model,
                        price: s.price,
                        turnaround_hours: parseInt(s.turnaround) || 24,
                        active: !s.active,
                      }),
                    },
                  );
              }}
            >
              <i />
            </button>
            <div>
              <button className="textBtn" onClick={() => setEditing(s)}>
                Edit
              </button>
              <button
                className="iconBtn danger"
                aria-label="Delete"
                onClick={() => {
                  const next = list.filter((x: Service) => x.id !== s.id);
                  setList(next);
                  if (typeof s.id === "string")
                    fetch(
                      `http://127.0.0.1:8000/api/v1/business/services/${s.id}`,
                      {
                        method: "DELETE",
                        headers: { Authorization: `Bearer ${serviceToken}` },
                      },
                    );
                  localStorage.setItem(
                    "launder-services",
                    JSON.stringify(next),
                  );
                }}
              >
                <Trash2 />
              </button>
            </div>
          </div>
        ))}
      </section>
    </AppFrame>
  );
}
export function MarketplaceBusiness() {
  const c = useCopy();
  const [state, setState] = useState("PENDING_REVIEW");
  const [loading, setLoading] = useState(true);
  async function refreshStatus() {
    const token = localStorage.getItem("launder-access-token");
    try {
      const response = await fetch(
        "http://127.0.0.1:8000/api/v1/business/marketplace",
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (response.ok) {
        const data = await response.json();
        setState(data.status);
      }
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    refreshStatus();
  }, []);
  return (
    <AppFrame title={c.marketplace}>
      <section className="marketStatus">
        <div className="marketStatusIcon">
          <Store />
        </div>
        <div>
          <span className={"status " + state.toLowerCase()}>
            {loading ? "LOADING" : state.replaceAll("_", " ")}
          </span>
          <h2>
            {state === "ACTIVE"
              ? "Your storefront is live"
              : state === "PENDING_REVIEW"
                ? "Your application is under review"
                : "Get discovered near your business"}
          </h2>
          <p>
            {state === "ACTIVE"
              ? "Customers can find T-Laundry, view services and place online orders."
              : "Marketplace is separate from Launder Business. Your workspace remains active while we review your storefront."}
          </p>
        </div>
      </section>
      {state === "ACTIVE" ? (
        <div className="metrics">
          <div className="metric">
            <p>Marketplace orders</p>
            <h2>38</h2>
          </div>
          <div className="metric">
            <p>Marketplace revenue</p>
            <h2>{money(612000)}</h2>
          </div>
          <div className="metric">
            <p>Commission</p>
            <h2>{money(30600)}</h2>
          </div>
          <div className="metric">
            <p>Storefront</p>
            <Link to="/laundries/t-laundry-mikocheni">View live </Link>
          </div>
        </div>
      ) : (
        <section className="workspaceCard reviewProgress">
          <Clock3 />
          <h3>Submitted 4 September 2026</h3>
          <p>
            All onboarding sections are complete. Launder administrators will
            review the application.
          </p>
          <button className="outlineBtn" onClick={refreshStatus}>
            Refresh status
          </button>
        </section>
      )}
    </AppFrame>
  );
}
export function GenericModule({ kind }: { kind: string }) {
  return (
    <AppFrame title={kind}>
      <section className="workspaceCard emptyModule">
        <div className="marketStatusIcon">
          {kind === "Customers" ? (
            <Users />
          ) : kind === "Payments" ? (
            <CreditCard />
          ) : (
            <Settings />
          )}
        </div>
        <h2>{kind} workspace</h2>
        <p>
          Your T-Laundry demo data is ready. Use the navigation to manage
          orders, pricing and marketplace status.
        </p>
        <button className="primary">
          <Plus /> Add {kind.toLowerCase().replace(/s$/, "")}
        </button>
      </section>
    </AppFrame>
  );
}
export function AdminLogin() {
  const c = useCopy();
  const nav = useNavigate();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  return (
    <main className="authPage">
      <div className="authUtility">
        <BusinessLang />
      </div>
      <Link className="authLogo" to="/">
        <span className="logoMark">L</span>
        <b>LAUNDER</b>
      </Link>
      <section className="authPanel compactAuth soloAuth">
        <div>
          <p className="kicker">PLATFORM ADMIN</p>
          <h1>{c.adminTitle}</h1>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setLoading(true);
              setError("");
              const fd = new FormData(e.currentTarget);
              try {
                const response = await fetch(
                  "http://127.0.0.1:8000/api/v1/auth/login",
                  {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                      email: fd.get("email"),
                      password: fd.get("password"),
                    }),
                  },
                );
                const data = await response.json();
                if (
                  !response.ok ||
                  !["ADMIN", "SUPER_ADMIN"].includes(data.user?.role)
                )
                  throw new Error("Incorrect email or password.");
                localStorage.setItem("launder-access-token", data.access_token);
                localStorage.setItem("launder-demo-auth", "admin");
                nav("/admin");
              } catch (err) {
                setError(
                  err instanceof Error ? err.message : "Unable to sign in.",
                );
              } finally {
                setLoading(false);
              }
            }}
          >
            <label>
              Email
              <input name="email" type="email" required autoComplete="email" />
            </label>
            <label>
              Password
              <input
                name="password"
                type="password"
                required
                autoComplete="current-password"
              />
            </label>
            {error && (
              <p className="formError" role="alert">
                {error}
              </p>
            )}
            <button className="primary full" disabled={loading}>
              {loading ? "Signing in..." : c.signin} <ArrowRight />
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}
export function Admin() {
  const c = useCopy();
  const [tab, setTab] = useState("dashboard");
  const [stats, setStats] = useState<Record<string, number>>({});
  const [applications, setApplications] = useState<any[]>([]);
  const [rows, setRows] = useState<any[]>([]);
  const [tablePage, setTablePage] = useState(1);
  const adminPageSize = 10;
  const [notice, setNotice] = useState("");
  const token = localStorage.getItem("launder-access-token") || "";
  const headers = { Authorization: `Bearer ${token}` };
  async function load() {
    try {
      const [dashboard, apps] = await Promise.all([
        fetch("http://127.0.0.1:8000/api/v1/admin/dashboard", { headers }),
        fetch("http://127.0.0.1:8000/api/v1/admin/marketplace-applications", {
          headers,
        }),
      ]);
      if (dashboard.status === 401 || dashboard.status === 403) {
        location.href = "/admin/login";
        return;
      }
      setStats(await dashboard.json());
      setApplications(await apps.json());
    } catch {
      setNotice(
        "The admin API is unavailable. Start the local API on port 8000.",
      );
    }
  }
  useEffect(() => {
    load();
  }, []);
  async function openTab(next: string) {
    setTab(next);
    setTablePage(1);
    setNotice("");
    if (["orders", "customers", "reviews"].includes(next)) {
      const response = await fetch(
        `http://127.0.0.1:8000/api/v1/admin/${next}`,
        { headers },
      );
      setRows(response.ok ? await response.json() : []);
    }
  }
  async function decide(id: string, decision: string) {
    const response = await fetch(
      `http://127.0.0.1:8000/api/v1/admin/marketplace-applications/${id}/${decision}`,
      {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({
          reason:
            decision === "reject"
              ? "Application requires updated verification"
              : null,
        }),
      },
    );
    if (response.ok) {
      setNotice(
        decision === "approve"
          ? "T-Laundry is now active on the Marketplace."
          : `Application ${decision}d.`,
      );
      await load();
    }
  }
  return (
    <main className="adminPage">
      <div className="adminTop">
        <Link className="logo" to="/">
          <span className="logoMark">L</span>
          <b>LAUNDER</b>
        </Link>
        <span>{c.admin}</span>
        <BusinessLang />
        <Link
          to="/admin/login"
          onClick={() => localStorage.removeItem("launder-access-token")}
        >
          {c.signout}
        </Link>
      </div>
      <div className="adminShell">
        <aside className="adminNav">
          {[
            ["dashboard", "Overview"],
            ["applications", "Marketplace applications"],
            ["businesses", "Businesses"],
            ["orders", "Orders"],
            ["customers", "Customers"],
            ["reviews", "Reviews"],
          ].map(([id, label]) => (
            <button
              className={tab === id ? "active" : ""}
              onClick={() => openTab(id)}
              key={id}
            >
              {label}
            </button>
          ))}
        </aside>
        <section className="adminContent">
          <div className="spread">
            <div>
              <p className="kicker">LAUNDER CONTROL CENTRE</p>
              <h1>
                {tab === "dashboard"
                  ? "Platform overview"
                  : tab[0].toUpperCase() + tab.slice(1)}
              </h1>
            </div>
            <BusinessLang />
          </div>
          {notice && <div className="adminNotice">{notice}</div>}
          {tab === "dashboard" && (
            <>
              <div className="metrics">
                {[
                  ["Businesses", stats.businesses || 0],
                  ["Pending approvals", stats.pending_applications || 0],
                  ["Customers", stats.customers || 0],
                  ["Orders", stats.orders || 0],
                  ["GMV", money(stats.gmv || 0)],
                  ["Platform revenue", money(stats.platform_revenue || 0)],
                ].map((x) => (
                  <div className="metric" key={x[0]}>
                    <p>{x[0]}</p>
                    <h2>{x[1]}</h2>
                  </div>
                ))}
              </div>
              <div className="adminGrid">
                <article className="workspaceCard monthChart">
                  <h2>Platform GMV</h2>
                  <div className="monthBars">
                    {[42, 55, 48, 67, 76, 91].map((h, i) => (
                      <div key={i}>
                        <i style={{ height: h + "%" }} />
                        <span>
                          {["Apr", "May", "Jun", "Jul", "Aug", "Sep"][i]}
                        </span>
                      </div>
                    ))}
                  </div>
                </article>
                <article className="workspaceCard">
                  <h2>Attention needed</h2>
                  <p className="spread">
                    <span>Marketplace applications</span>
                    <b>{stats.pending_applications || 0}</b>
                  </p>
                  <p className="spread">
                    <span>Payment exceptions</span>
                    <b>0</b>
                  </p>
                  <p className="spread">
                    <span>Reported reviews</span>
                    <b>0</b>
                  </p>
                  <button
                    className="primary full"
                    onClick={() => openTab("applications")}
                  >
                    Review applications
                  </button>
                </article>
              </div>
            </>
          )}
          {tab === "applications" && (
            <div className="adminList">
              {applications.map((a) => (
                <article className="workspaceCard" key={a.id}>
                  <div className="spread">
                    <div>
                      <span className={`status ${a.status.toLowerCase()}`}>
                        {a.status.replaceAll("_", " ")}
                      </span>
                      <h2>{a.business_name}</h2>
                      <p>
                        {a.area} · {a.pickup_radius_km} km pickup radius ·{" "}
                        {a.commission_rate}% commission
                      </p>
                    </div>
                    <div className="adminActions">
                      <button
                        className="primary"
                        onClick={() => decide(a.id, "approve")}
                      >
                        <Check /> Approve
                      </button>
                      <button
                        className="outlineBtn"
                        onClick={() => decide(a.id, "reject")}
                      >
                        Reject
                      </button>
                      <button
                        className="textBtn"
                        onClick={() => decide(a.id, "suspend")}
                      >
                        Suspend
                      </button>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}
          {tab === "businesses" && (
            <div className="adminList">
              {applications.map((a) => (
                <article className="workspaceCard spread" key={a.business_id}>
                  <div>
                    <h2>{a.business_name}</h2>
                    <p>{a.area}</p>
                  </div>
                  <span className={`status ${a.status.toLowerCase()}`}>
                    {a.status}
                  </span>
                </article>
              ))}
            </div>
          )}
          {["orders", "customers", "reviews"].includes(tab) && (
            <section className="orders adminData">
              <div className="tableHead">
                <span>ID / Name</span>
                <span>Contact / Source</span>
                <span>Status</span>
                <span>Total</span>
                <span></span>
              </div>
              {rows.length ? (
                rows
                  .slice(
                    (tablePage - 1) * adminPageSize,
                    tablePage * adminPageSize,
                  )
                  .map((r, i) => (
                    <div className="order" key={r.id || i}>
                      <b>{r.order_number || r.name || `Review ${i + 1}`}</b>
                      <span>{r.phone || r.source || r.comment}</span>
                      <span className="pill">
                        {r.status || r.payment_status || "ACTIVE"}
                      </span>
                      <b>
                        {r.total
                          ? money(r.total)
                          : r.rating
                            ? `${r.rating}/5`
                            : "—"}
                      </b>
                      <button className="textBtn">View</button>
                    </div>
                  ))
              ) : (
                <div className="empty">
                  <p>No {tab} found.</p>
                </div>
              )}
              {rows.length > 0 && (
                <Pagination
                  page={tablePage}
                  pages={Math.ceil(rows.length / adminPageSize)}
                  total={rows.length}
                  pageSize={adminPageSize}
                  onPage={setTablePage}
                />
              )}
            </section>
          )}
        </section>
      </div>
    </main>
  );
}
