import { useCallback, useState } from "react";

export type Place = {
  label: string;
  lat: number;
  lng: number;
  source: "gps" | "area";
};
type Status = "idle" | "locating" | "denied" | "unavailable";

const KEY = "launder-place";

function stored(): Place | null {
  try {
    return JSON.parse(localStorage.getItem(KEY) || "null");
  } catch {
    return null;
  }
}

/** The customer's search location: GPS when allowed, otherwise a neighbourhood they pick. Remembered per browser. */
export function usePlace() {
  const [place, setPlaceState] = useState<Place | null>(stored);
  const [status, setStatus] = useState<Status>("idle");

  const setPlace = useCallback((p: Place | null) => {
    setPlaceState(p);
    try {
      if (p) localStorage.setItem(KEY, JSON.stringify(p));
      else localStorage.removeItem(KEY);
    } catch {
      /* ignore */
    }
  }, []);

  const locate = useCallback(
    (label: string) => {
      if (!("geolocation" in navigator)) {
        setStatus("unavailable");
        return;
      }
      setStatus("locating");
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          setStatus("idle");
          setPlace({
            label,
            lat: pos.coords.latitude,
            lng: pos.coords.longitude,
            source: "gps",
          });
        },
        (err) =>
          setStatus(
            err.code === err.PERMISSION_DENIED ? "denied" : "unavailable",
          ),
        { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 },
      );
    },
    [setPlace],
  );

  return { place, setPlace, locate, status };
}
