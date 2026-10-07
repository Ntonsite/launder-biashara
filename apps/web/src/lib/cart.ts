import { useSyncExternalStore } from "react";

/** Cart lines carry display prices for the UI only; the server re-prices everything at quote and order time. */
export type CartLine = {
  serviceId: string;
  name: string;
  pricingModel: string;
  unitPrice: number;
  quantity: number;
};
export type Cart = {
  laundrySlug: string;
  laundryName: string;
  pickupEnabled: boolean;
  lines: CartLine[];
} | null;

const KEY = "launder-cart";
const listeners = new Set<() => void>();
let current: Cart = read();

function read(): Cart {
  try {
    return JSON.parse(localStorage.getItem(KEY) || "null");
  } catch {
    return null;
  }
}

function write(next: Cart) {
  current = next && next.lines.length ? next : null;
  try {
    if (current) localStorage.setItem(KEY, JSON.stringify(current));
    else localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: cart still works for this tab */
  }
  listeners.forEach((l) => l());
}

export const cart = {
  get: () => current,
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  /** Starting a cart at another laundry replaces the old one; the caller confirms with the user first. */
  setQuantity(
    laundry: { slug: string; name: string; pickup_enabled: boolean },
    line: Omit<CartLine, "quantity">,
    quantity: number,
  ) {
    const base =
      current && current.laundrySlug === laundry.slug
        ? current
        : {
            laundrySlug: laundry.slug,
            laundryName: laundry.name,
            pickupEnabled: laundry.pickup_enabled,
            lines: [],
          };
    const others = base.lines.filter((l) => l.serviceId !== line.serviceId);
    const lines = quantity > 0 ? [...others, { ...line, quantity }] : others;
    const order = base.lines.map((l) => l.serviceId);
    lines.sort(
      (a, b) =>
        (order.indexOf(a.serviceId) + 1 || 999) -
        (order.indexOf(b.serviceId) + 1 || 999),
    );
    write({ ...base, lines });
  },
  replace(next: Cart) {
    write(next);
  },
  clear() {
    write(null);
  },
};

export function useCart() {
  return useSyncExternalStore(cart.subscribe, cart.get, cart.get);
}

export const cartTotals = (c: Cart) => ({
  count:
    c?.lines.reduce(
      (n, l) => n + (l.pricingModel === "PER_KG" ? 1 : l.quantity),
      0,
    ) ?? 0,
  subtotal:
    c?.lines.reduce((n, l) => n + Math.round(l.unitPrice * l.quantity), 0) ?? 0,
});
