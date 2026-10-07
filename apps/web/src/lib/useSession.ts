import { useEffect, useState } from "react";
import { sessions, type Audience } from "./api";

/** Re-renders when a session is created, refreshed or cleared (in this tab or another). */
export function useSession(audience: Audience) {
  const [session, setSession] = useState(() => sessions.get(audience));
  useEffect(() => {
    const update = () => setSession(sessions.get(audience));
    window.addEventListener("launder-session", update);
    window.addEventListener("storage", update);
    return () => {
      window.removeEventListener("launder-session", update);
      window.removeEventListener("storage", update);
    };
  }, [audience]);
  return session;
}
