/**
 * One HTTP client for the whole web app. Paths are relative ("/api/v1/...") so the same build works behind the
 * Vite dev proxy and behind nginx in Docker. Set VITE_API_URL only when the API lives on another origin.
 */
const BASE =
  (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ??
  "";

export type Audience = "customer" | "business" | "admin";

export type Session = {
  access_token: string;
  refresh_token: string;
  user: {
    id: string;
    name: string;
    email?: string | null;
    phone?: string | null;
    role: string;
    business_id?: string | null;
    language: string;
  };
};

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: any,
  ) {
    super(message);
  }
}

const KEY = (a: Audience) => `launder-session-${a}`;

export const sessions = {
  get(a: Audience): Session | null {
    try {
      return JSON.parse(localStorage.getItem(KEY(a)) || "null");
    } catch {
      return null;
    }
  },
  set(a: Audience, s: Session) {
    localStorage.setItem(KEY(a), JSON.stringify(s));
    window.dispatchEvent(new Event("launder-session"));
  },
  clear(a: Audience) {
    localStorage.removeItem(KEY(a));
    window.dispatchEvent(new Event("launder-session"));
  },
};

export function mediaUrl(path?: string | null) {
  if (!path) return undefined;
  return path.startsWith("http") ? path : BASE + path;
}

const refreshing: Partial<Record<Audience, Promise<boolean>>> = {};

async function refresh(a: Audience): Promise<boolean> {
  const current = sessions.get(a);
  if (!current) return false;
  // Concurrent 401s share one refresh, otherwise rotation would revoke the family.
  refreshing[a] ??= fetch(`${BASE}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: current.refresh_token }),
  })
    .then(async (r) => {
      if (!r.ok) {
        sessions.clear(a);
        return false;
      }
      sessions.set(a, await r.json());
      return true;
    })
    .catch(() => false)
    .finally(() => delete refreshing[a]);
  return refreshing[a]!;
}

type Options = {
  method?: string;
  body?: unknown;
  auth?: Audience;
  headers?: Record<string, string>;
  signal?: AbortSignal;
};

export async function api<T = any>(
  path: string,
  opts: Options = {},
  retried = false,
): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...opts.headers,
  };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  const session = opts.auth ? sessions.get(opts.auth) : null;
  if (session) headers.Authorization = `Bearer ${session.access_token}`;
  let response: Response;
  try {
    response = await fetch(BASE + path, {
      method: opts.method ?? (opts.body !== undefined ? "POST" : "GET"),
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError(0, "NETWORK", "network");
  }
  if (
    response.status === 401 &&
    opts.auth &&
    session &&
    !retried &&
    (await refresh(opts.auth))
  ) {
    return api<T>(path, opts, true);
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const error = data?.error;
    throw new ApiError(
      response.status,
      error?.code ?? "ERROR",
      error?.message ?? data?.detail ?? "Request failed",
      error?.details,
    );
  }
  return data as T;
}

export function newIdempotencyKey() {
  return crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
