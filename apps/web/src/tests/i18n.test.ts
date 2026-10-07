import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import en from "../locales/en/translation.json";
import sw from "../locales/sw/translation.json";

function flatten(obj: Record<string, unknown>, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    v && typeof v === "object"
      ? flatten(v as Record<string, unknown>, `${prefix}${k}.`)
      : [`${prefix}${k}`],
  );
}

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory())
      return name === "tests" ? [] : sources(path);
    return /\.tsx?$/.test(name) ? [path] : [];
  });
}

const enKeys = new Set(flatten(en));
const swKeys = new Set(flatten(sw));
const base = (k: string) => k.replace(/_(one|other)$/, "");

describe("translations", () => {
  it("English and Swahili define exactly the same keys", () => {
    expect([...enKeys].filter((k) => !swKeys.has(k))).toEqual([]);
    expect([...swKeys].filter((k) => !enKeys.has(k))).toEqual([]);
  });

  it("no Swahili value is left empty or identical to a long English sentence", () => {
    const flatEn = Object.fromEntries(
      flatten(en).map((k) => [k, k.split(".").reduce((o: any, p) => o[p], en)]),
    );
    const untranslated = flatten(sw).filter((k) => {
      const value = k.split(".").reduce((o: any, p) => o[p], sw) as string;
      return (
        !value.trim() ||
        (value === flatEn[k] &&
          value.split(" ").length > 3 &&
          !k.startsWith("categories"))
      );
    });
    expect(untranslated).toEqual([]);
  });

  it("every literal t('key') used in the app exists", () => {
    const known = new Set([...enKeys].map(base));
    const missing: string[] = [];
    for (const file of sources(join(__dirname, ".."))) {
      const text = readFileSync(file, "utf8");
      for (const m of text.matchAll(/\bt\(\s*["'`]([a-zA-Z][\w.]*)["'`]/g)) {
        if (
          !known.has(m[1]) &&
          ![...known].some((k) => k.startsWith(m[1] + "."))
        )
          missing.push(`${file.split(/[\/]src[\/]/)[1]}: ${m[1]}`);
      }
    }
    expect(missing).toEqual([]);
  });

  it("does not scatter inline language conditionals through components", () => {
    const offenders = sources(join(__dirname, "..")).filter(
      (f) =>
        /language\s*===\s*["']sw["']\s*\?/.test(readFileSync(f, "utf8")) &&
        !f.endsWith("format.ts") &&
        !f.endsWith("i18n.ts"),
    );
    expect(offenders).toEqual([]);
  });
});
