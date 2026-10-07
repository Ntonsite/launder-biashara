import { api } from "../lib/api";
import { cart } from "../lib/cart";
import type { Quote } from "./types";

export type ReorderResult = {
  laundry: { slug: string; name: string; pickup_enabled: boolean };
  quote: Quote | null;
  changes: {
    type: "PRICE_CHANGED" | "UNAVAILABLE";
    name: string;
    old_price?: number;
    new_price?: number;
  }[];
};

/** Rebuilds the cart from a past order using the server's current prices. Returns the changes to show the customer. */
export async function reorder(orderId: string): Promise<ReorderResult> {
  const result = await api<ReorderResult>(
    `/api/v1/customer/orders/${orderId}/reorder`,
    { auth: "customer" },
  );
  if (result.quote && result.quote.items.length) {
    cart.replace({
      laundrySlug: result.laundry.slug,
      laundryName: result.laundry.name,
      pickupEnabled: result.laundry.pickup_enabled,
      lines: result.quote.items.map((i) => ({
        serviceId: i.service_id,
        name: i.name,
        pricingModel: i.pricing_model,
        unitPrice: i.unit_price,
        quantity: i.quantity,
      })),
    });
  }
  return result;
}
