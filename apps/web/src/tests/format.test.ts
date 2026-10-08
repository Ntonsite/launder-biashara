import { describe, expect, it } from "vitest";
import i18n from "../i18n";
import { itemsSummary, moneyShort, percent, trendTone } from "../lib/format";

describe("business figures", () => {
  it("colours a change by whether it is good news for that metric", () => {
    expect(trendTone(12, "up")).toBe("good");
    expect(trendTone(-12, "up")).toBe("bad");
    // More money outstanding or more late orders is not good news.
    expect(trendTone(12, "down")).toBe("bad");
    expect(trendTone(-5, "down")).toBe("good");
    expect(trendTone(0.4, "up")).toBe("flat");
    expect(trendTone(30, "neutral")).toBe("flat");
    // No comparison (too little history) shows nothing at all.
    expect(trendTone(null, "up")).toBe("none");
  });

  it("shortens large shilling amounts for cards but keeps small ones exact", async () => {
    await i18n.changeLanguage("en");
    expect(moneyShort(4_800_000)).toBe("TZS 4.8M");
    expect(moneyShort(185_000)).toBe("TZS 185K");
    expect(moneyShort(9_000)).toBe("TZS 9,000");
    expect(percent(33.33)).toBe("33.3%");
    expect(percent(null)).toBe("—");
  });

  it("describes items the way staff say them", () => {
    expect(
      itemsSummary([
        { name: "Shirt", quantity: 5, pricing_model: "PER_ITEM" },
        { name: "Wash & Fold", quantity: 2.5, pricing_model: "PER_KG" },
        { name: "Family bag", quantity: 1, pricing_model: "PACKAGE" },
      ]),
    ).toBe("5× Shirt, 2.5 kg Wash & Fold, 1× Family bag");
  });
});
