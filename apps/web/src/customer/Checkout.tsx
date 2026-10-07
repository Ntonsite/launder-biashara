import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft,
  ArrowRight,
  Banknote,
  Check,
  Smartphone,
  Store,
  Truck,
} from "lucide-react";
import { api, ApiError, newIdempotencyKey, sessions } from "../lib/api";
import { cart, useCart } from "../lib/cart";
import { dateTime, errorMessage, money, time } from "../lib/format";
import { useSession } from "../lib/useSession";
import SignIn from "./SignIn";
import { EmptyState, Notice } from "./ui";
import type { OrderDetail, Quote } from "./types";

type Address = {
  id: string;
  label: string;
  line: string;
  area: string;
  notes: string;
  latitude: number | null;
  longitude: number | null;
};
type Slot = { start: string; end: string };
type StepName = "fulfilment" | "address" | "schedule" | "payment" | "review";

export default function Checkout() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const current = useCart();
  const session = useSession("customer");
  const [fulfilment, setFulfilment] = useState<"PICKUP" | "DROP_OFF">(
    current?.pickupEnabled ? "PICKUP" : "DROP_OFF",
  );
  const [addresses, setAddresses] = useState<Address[]>([]);
  const [addressId, setAddressId] = useState<string>("");
  const [newAddress, setNewAddress] = useState({
    line: "",
    area: "",
    notes: "",
  });
  const [slots, setSlots] = useState<Slot[] | null>(null);
  const [slot, setSlot] = useState("");
  const [payment, setPayment] = useState<"CASH" | "MOBILE_MONEY">("CASH");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [step, setStep] = useState<StepName>("fulfilment");
  const [error, setError] = useState("");
  const [placing, setPlacing] = useState(false);
  // One key per checkout attempt: retries and double clicks can never create two orders.
  const idempotencyKey = useRef(newIdempotencyKey());

  const steps = useMemo<StepName[]>(
    () =>
      fulfilment === "PICKUP"
        ? ["fulfilment", "address", "schedule", "payment", "review"]
        : ["fulfilment", "payment", "review"],
    [fulfilment],
  );

  useEffect(() => {
    if (!session) return;
    api<{ items: Address[] }>("/api/v1/customer/addresses", {
      auth: "customer",
    })
      .then((r) => {
        setAddresses(r.items);
        if (r.items[0]) setAddressId(r.items[0].id);
      })
      .catch(() => setAddresses([]));
  }, [session?.user.id]);

  useEffect(() => {
    if (!current || fulfilment !== "PICKUP") return;
    api<{ slots: Slot[] }>(
      `/api/v1/marketplace/laundries/${current.laundrySlug}/pickup-slots?days=3`,
    )
      .then((r) => setSlots(r.slots))
      .catch((err) => setError(errorMessage(err)));
  }, [current?.laundrySlug, fulfilment]);

  useEffect(() => {
    if (!current) return;
    const items = current.lines.map((l) => ({
      service_id: l.serviceId,
      quantity: l.quantity,
    }));
    api<Quote>(`/api/v1/marketplace/laundries/${current.laundrySlug}/quote`, {
      body: { items, fulfillment: fulfilment },
    })
      .then(setQuote)
      .catch((err) => setError(errorMessage(err)));
  }, [JSON.stringify(current), fulfilment]);

  if (!current)
    return (
      <main className="checkout narrow">
        <EmptyState
          icon={<Store />}
          title={t("cart.emptyTitle")}
          action={
            <Link className="primary" to="/laundries">
              {t("nav.find")}
            </Link>
          }
        />
      </main>
    );

  if (!session?.user.name)
    return (
      <main className="checkout narrow">
        <p className="kicker">{current.laundryName}</p>
        <h1>{t("checkout.title")}</h1>
        <SignIn onDone={() => setStep("fulfilment")} />
      </main>
    );

  const index = steps.indexOf(step);
  const next = () => setStep(steps[Math.min(index + 1, steps.length - 1)]);
  const back = () => (index > 0 ? setStep(steps[index - 1]) : nav("/cart"));
  const selectedAddress = addresses.find((a) => a.id === addressId);
  const addressReady =
    fulfilment !== "PICKUP" ||
    !!selectedAddress ||
    newAddress.line.trim().length >= 3;
  const slotLabel = (s: Slot) => `${dateTime(s.start)} – ${time(s.end)}`;

  async function place() {
    if (placing || !current) return;
    setPlacing(true);
    setError("");
    try {
      let chosenAddressId = addressId || undefined;
      if (fulfilment === "PICKUP" && !selectedAddress) {
        const saved = await api<Address>("/api/v1/customer/addresses", {
          auth: "customer",
          body: { label: "Home", ...newAddress },
        });
        chosenAddressId = saved.id;
      }
      const order = await api<OrderDetail>("/api/v1/customer/orders", {
        auth: "customer",
        headers: { "Idempotency-Key": idempotencyKey.current },
        body: {
          laundry_slug: current.laundrySlug,
          items: current.lines.map((l) => ({
            service_id: l.serviceId,
            quantity: l.quantity,
          })),
          fulfillment: fulfilment,
          address_id: fulfilment === "PICKUP" ? chosenAddressId : undefined,
          pickup_window_start: fulfilment === "PICKUP" ? slot : undefined,
          payment_method: payment,
          expected_total: quote?.total,
        },
      });
      cart.clear();
      nav(`/account/orders/${order.id}?placed=1`, { replace: true });
    } catch (err) {
      if (
        err instanceof ApiError &&
        err.code === "PRICE_CHANGED" &&
        err.details?.quote
      ) {
        setQuote(err.details.quote);
        idempotencyKey.current = newIdempotencyKey();
      }
      if (err instanceof ApiError && err.code === "PICKUP_SLOT_UNAVAILABLE")
        setStep("schedule");
      if (err instanceof ApiError && err.status === 401)
        sessions.clear("customer");
      setError(errorMessage(err));
    } finally {
      setPlacing(false);
    }
  }

  return (
    <main className="checkout narrow">
      <button className="back" onClick={back}>
        <ArrowLeft /> {t("common.back")}
      </button>
      <p className="kicker">{current.laundryName}</p>
      <h1>{t(`checkout.steps.${step}`)}</h1>
      <ol className="stepper" aria-label={t("checkout.progress")}>
        {steps.map((s, i) => (
          <li
            key={s}
            className={i < index ? "done" : i === index ? "current" : ""}
            aria-current={i === index ? "step" : undefined}
          >
            {t(`checkout.stepShort.${s}`)}
          </li>
        ))}
      </ol>
      {error && <Notice>{error}</Notice>}

      <section className="panel">
        {step === "fulfilment" && (
          <div className="optionList" role="radiogroup">
            <Option
              selected={fulfilment === "PICKUP"}
              disabled={!current.pickupEnabled}
              onSelect={() => setFulfilment("PICKUP")}
              icon={<Truck />}
              title={t("checkout.pickup")}
              body={
                current.pickupEnabled
                  ? t("checkout.pickupBody")
                  : t("checkout.pickupUnavailable")
              }
            />
            <Option
              selected={fulfilment === "DROP_OFF"}
              onSelect={() => setFulfilment("DROP_OFF")}
              icon={<Store />}
              title={t("checkout.dropOff")}
              body={t("checkout.dropOffBody")}
            />
          </div>
        )}

        {step === "address" && (
          <>
            {addresses.length > 0 && (
              <div className="optionList" role="radiogroup">
                {addresses.map((a) => (
                  <Option
                    key={a.id}
                    selected={addressId === a.id}
                    onSelect={() => setAddressId(a.id)}
                    title={a.label}
                    body={[a.line, a.area].filter(Boolean).join(", ")}
                  />
                ))}
                <Option
                  selected={!addressId}
                  onSelect={() => setAddressId("")}
                  title={t("checkout.newAddress")}
                />
              </div>
            )}
            {!selectedAddress && (
              <div className="fields">
                <label>
                  {t("checkout.address")}
                  <input
                    value={newAddress.line}
                    onChange={(e) =>
                      setNewAddress({ ...newAddress, line: e.target.value })
                    }
                    placeholder={t("checkout.addressHint")}
                    required
                  />
                </label>
                <label>
                  {t("checkout.area")}
                  <input
                    value={newAddress.area}
                    onChange={(e) =>
                      setNewAddress({ ...newAddress, area: e.target.value })
                    }
                    placeholder="Mikocheni"
                  />
                </label>
                <label>
                  {t("checkout.directions")}
                  <input
                    value={newAddress.notes}
                    onChange={(e) =>
                      setNewAddress({ ...newAddress, notes: e.target.value })
                    }
                    placeholder={t("checkout.directionsHint")}
                  />
                </label>
              </div>
            )}
          </>
        )}

        {step === "schedule" &&
          (slots === null ? (
            <div className="shimmer line w60" />
          ) : slots.length === 0 ? (
            <p>{t("checkout.noSlots")}</p>
          ) : (
            <div className="slotGrid" role="radiogroup">
              {slots.slice(0, 12).map((s) => (
                <button
                  key={s.start}
                  role="radio"
                  aria-checked={slot === s.start}
                  className={slot === s.start ? "slot on" : "slot"}
                  onClick={() => setSlot(s.start)}
                >
                  {slotLabel(s)}
                </button>
              ))}
            </div>
          ))}

        {step === "payment" && (
          <div className="optionList" role="radiogroup">
            <Option
              selected={payment === "CASH"}
              onSelect={() => setPayment("CASH")}
              icon={<Banknote />}
              title={t("checkout.cash")}
              body={t("checkout.cashBody")}
            />
            <Option
              selected={payment === "MOBILE_MONEY"}
              onSelect={() => setPayment("MOBILE_MONEY")}
              icon={<Smartphone />}
              title={t("checkout.mobile")}
              body={t("checkout.mobileBody")}
            />
          </div>
        )}

        {step === "review" && quote && (
          <div className="reviewList">
            {quote.items.map((i) => (
              <div className="spread" key={i.service_id}>
                <span>
                  {i.pricing_model === "PER_KG"
                    ? `${i.quantity} kg`
                    : `${i.quantity} ×`}{" "}
                  {i.name}
                </span>
                <b>{money(i.line_total)}</b>
              </div>
            ))}
            <hr />
            <div className="spread">
              <span>
                {fulfilment === "PICKUP"
                  ? t("checkout.pickup")
                  : t("checkout.dropOff")}
              </span>
              <span>
                {fulfilment === "PICKUP"
                  ? slotLabel(slots!.find((s) => s.start === slot)!)
                  : current.laundryName}
              </span>
            </div>
            {fulfilment === "PICKUP" && (
              <div className="spread">
                <span>{t("checkout.address")}</span>
                <span>
                  {selectedAddress ? selectedAddress.line : newAddress.line}
                </span>
              </div>
            )}
            <div className="spread">
              <span>{t("checkout.payment")}</span>
              <span>
                {payment === "CASH" ? t("checkout.cash") : t("checkout.mobile")}
              </span>
            </div>
            <hr />
            <div className="spread">
              <span>{t("cart.subtotal")}</span>
              <span>{money(quote.subtotal)}</span>
            </div>
            {quote.delivery_fee > 0 && (
              <div className="spread">
                <span>{t("checkout.pickupFee")}</span>
                <span>{money(quote.delivery_fee)}</span>
              </div>
            )}
            <div className="spread totalRow">
              <b>{t("common.total")}</b>
              <strong>{money(quote.total)}</strong>
            </div>
          </div>
        )}

        {step === "review" ? (
          <button
            className="primary full"
            onClick={place}
            disabled={placing || !quote}
          >
            {placing ? t("checkout.placing") : t("checkout.place")}{" "}
            {!placing && <Check />}
          </button>
        ) : (
          <button
            className="primary full"
            onClick={next}
            disabled={
              (step === "address" && !addressReady) ||
              (step === "schedule" && !slot)
            }
          >
            {t("common.continue")} <ArrowRight />
          </button>
        )}
      </section>
    </main>
  );
}

function Option(props: {
  selected: boolean;
  onSelect: () => void;
  title: string;
  body?: string;
  icon?: React.ReactNode;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={props.selected}
      disabled={props.disabled}
      className={`option ${props.selected ? "on" : ""}`}
      onClick={props.onSelect}
    >
      {props.icon && <span className="optionIcon">{props.icon}</span>}
      <span>
        <b>{props.title}</b>
        {props.body && <small>{props.body}</small>}
      </span>
      <i aria-hidden="true" />
    </button>
  );
}
