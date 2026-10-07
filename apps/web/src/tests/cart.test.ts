import { beforeEach, describe, expect, it } from "vitest";
import { cart, cartTotals } from "../lib/cart";

const freshwash = {
  slug: "freshwash",
  name: "FreshWash Laundry",
  pickup_enabled: true,
};
const shirt = {
  serviceId: "s1",
  name: "Shirt",
  pricingModel: "PER_ITEM",
  unitPrice: 2000,
};
const trouser = {
  serviceId: "s2",
  name: "Trouser",
  pricingModel: "PER_ITEM",
  unitPrice: 3000,
};
const fold = {
  serviceId: "s3",
  name: "Wash & Fold",
  pricingModel: "PER_KG",
  unitPrice: 4000,
};

describe("cart", () => {
  beforeEach(() => cart.clear());

  it("totals 5 shirts and 2 trousers", () => {
    cart.setQuantity(freshwash, shirt, 5);
    cart.setQuantity(freshwash, trouser, 2);
    expect(cartTotals(cart.get())).toEqual({ count: 7, subtotal: 16000 });
  });

  it("counts a per-kg line as one item and prices half kilos exactly", () => {
    cart.setQuantity(freshwash, fold, 2.5);
    expect(cartTotals(cart.get())).toEqual({ count: 1, subtotal: 10000 });
  });

  it("removes a line at zero and empties the cart", () => {
    cart.setQuantity(freshwash, shirt, 1);
    cart.setQuantity(freshwash, shirt, 0);
    expect(cart.get()).toBeNull();
  });

  it("starting at another laundry replaces the cart instead of mixing laundries", () => {
    cart.setQuantity(freshwash, shirt, 3);
    cart.setQuantity(
      { slug: "safi", name: "Safi Laundry", pickup_enabled: true },
      trouser,
      1,
    );
    expect(cart.get()?.laundrySlug).toBe("safi");
    expect(cart.get()?.lines).toHaveLength(1);
  });

  it("persists across reloads", () => {
    cart.setQuantity(freshwash, shirt, 2);
    expect(
      JSON.parse(localStorage.getItem("launder-cart")!).lines[0].quantity,
    ).toBe(2);
  });
});
