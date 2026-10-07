import { Link } from "react-router-dom";
import {
  ArrowRight,
  BarChart3,
  Check,
  ClipboardList,
  Package,
  ShieldCheck,
  Store,
  Users,
  Wallet,
} from "lucide-react";

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
              Sign in
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
            <b>Your laundry</b>
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
        <h2>From the counter to the customer’s door.</h2>
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
        <h1>Start free. Grow when you’re ready.</h1>
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
          <a
            className="primary full"
            href="mailto:hello@launder.co.tz?subject=Launder%20Pro%20waitlist"
          >
            Join the waitlist
          </a>
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
