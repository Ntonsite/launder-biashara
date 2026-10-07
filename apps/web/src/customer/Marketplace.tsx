import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { LocateFixed, MapPin, Search, SearchX } from "lucide-react";
import { api } from "../lib/api";
import { errorMessage } from "../lib/format";
import { usePlace } from "../lib/location";
import { CardSkeletons, EmptyState, LaundryCard, Notice } from "./ui";
import type { LaundryCardData, Page } from "./types";

type Area = { name: string; latitude: number; longitude: number };
const SERVICES = ["Wash & Iron", "Wash & Fold", "Dry Cleaning", "Household"];

export default function Marketplace() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const { place, setPlace, locate, status } = usePlace();
  const [areas, setAreas] = useState<Area[]>([]);
  const [data, setData] = useState<Page<LaundryCardData> | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState(params.get("q") ?? "");

  const q = params.get("q") ?? "";
  const filters = {
    open_now: params.get("open_now") === "1",
    pickup: params.get("pickup") === "1",
    top: params.get("top") === "1",
  };
  const service = params.get("service") ?? "";
  const sort = params.get("sort") ?? "";

  useEffect(() => {
    api<{ items: Area[] }>("/api/v1/marketplace/areas")
      .then((r) => setAreas(r.items))
      .catch(() => setAreas([]));
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const search = new URLSearchParams({ page_size: "24" });
    if (place) {
      search.set("lat", String(place.lat));
      search.set("lng", String(place.lng));
      search.set("radius_km", "15");
    }
    if (q) search.set("q", q);
    if (service) search.set("service", service);
    if (filters.open_now) search.set("open_now", "true");
    if (filters.pickup) search.set("pickup", "true");
    if (filters.top) search.set("min_rating", "4.5");
    if (sort) search.set("sort", sort);
    setData(null);
    setError("");
    api<Page<LaundryCardData>>(`/api/v1/marketplace/laundries?${search}`, {
      signal: controller.signal,
    })
      .then(setData)
      .catch((err) => err.name !== "AbortError" && setError(errorMessage(err)));
    return () => controller.abort();
  }, [
    place?.lat,
    place?.lng,
    q,
    service,
    filters.open_now,
    filters.pickup,
    filters.top,
    sort,
  ]);

  function toggle(key: string) {
    const next = new URLSearchParams(params);
    if (next.get(key) === "1") next.delete(key);
    else next.set(key, "1");
    setParams(next, { replace: true });
  }

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  return (
    <main className="market">
      <div className="marketHead">
        <p className="kicker">DAR ES SALAAM</p>
        <h1>{t("market.title")}</h1>
        <p>{t("market.sub")}</p>
        <form
          className="marketSearch"
          role="search"
          onSubmit={(e) => {
            e.preventDefault();
            setParam("q", query.trim());
          }}
        >
          <Search />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("market.search")}
            aria-label={t("market.search")}
          />
          <button type="submit">{t("market.searchButton")}</button>
        </form>
        <div className="locationRow">
          <button
            type="button"
            className="chipBtn"
            onClick={() => locate(t("market.nearMe"))}
            disabled={status === "locating"}
          >
            <LocateFixed />{" "}
            {status === "locating" ? t("market.locating") : t("market.nearMe")}
          </button>
          <label className="areaSelect">
            <MapPin />
            <select
              aria-label={t("market.chooseArea")}
              value={place?.source === "area" ? place.label : ""}
              onChange={(e) => {
                const a = areas.find((x) => x.name === e.target.value);
                setPlace(
                  a
                    ? {
                        label: a.name,
                        lat: a.latitude,
                        lng: a.longitude,
                        source: "area",
                      }
                    : null,
                );
              }}
            >
              <option value="">
                {place?.source === "gps"
                  ? t("market.usingLocation")
                  : t("market.chooseArea")}
              </option>
              {areas.map((a) => (
                <option key={a.name}>{a.name}</option>
              ))}
            </select>
          </label>
        </div>
        {(status === "denied" || status === "unavailable") && (
          <Notice kind="info">
            {t(
              status === "denied"
                ? "market.locationDenied"
                : "market.locationUnavailable",
            )}
          </Notice>
        )}
      </div>

      <div className="filterrow" role="group" aria-label={t("market.filters")}>
        <button
          className={filters.open_now ? "active" : ""}
          aria-pressed={filters.open_now}
          onClick={() => toggle("open_now")}
        >
          {t("market.openNow")}
        </button>
        <button
          className={filters.pickup ? "active" : ""}
          aria-pressed={filters.pickup}
          onClick={() => toggle("pickup")}
        >
          {t("market.pickup")}
        </button>
        <button
          className={filters.top ? "active" : ""}
          aria-pressed={filters.top}
          onClick={() => toggle("top")}
        >
          {t("market.topRated")}
        </button>
        <select
          aria-label={t("market.service")}
          value={service}
          onChange={(e) => setParam("service", e.target.value)}
        >
          <option value="">{t("market.all")}</option>
          {SERVICES.map((s) => (
            <option key={s} value={s}>
              {t(`categories.${s}`, { defaultValue: s })}
            </option>
          ))}
        </select>
        <select
          aria-label={t("market.sort")}
          value={sort}
          onChange={(e) => setParam("sort", e.target.value)}
        >
          <option value="">
            {place ? t("market.sortDistance") : t("market.sortRating")}
          </option>
          {place && <option value="rating">{t("market.sortRating")}</option>}
          <option value="price">{t("market.sortPrice")}</option>
        </select>
      </div>

      {error && <Notice>{error}</Notice>}
      {!data && !error && <CardSkeletons count={6} />}
      {data && (
        <>
          <p className="resultCount" aria-live="polite">
            {place
              ? t("market.resultsNear", {
                  count: data.total,
                  place: place.label,
                })
              : t("market.results", { count: data.total })}
          </p>
          {data.items.length ? (
            <div className="cards">
              {data.items.map((l) => (
                <LaundryCard key={l.id} l={l} />
              ))}
            </div>
          ) : (
            <EmptyState
              icon={<SearchX />}
              title={t("market.emptyTitle")}
              body={t("market.emptyBody")}
              action={
                <button
                  className="outlineBtn"
                  onClick={() => setParams({}, { replace: true })}
                >
                  {t("market.clearFilters")}
                </button>
              }
            />
          )}
        </>
      )}
    </main>
  );
}
