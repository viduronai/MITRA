/**
 * Session cookie name and an UNVERIFIED read of the JWT payload. Used only
 * for routing decisions (proxy redirects, "has a business yet?"). Every API
 * call still sends the token to services/core, which verifies it.
 * Runtime-agnostic: no Node APIs, so the proxy can import it.
 */

export const SESSION_COOKIE = "mitra_session";

export interface SessionClaims {
  sub: string;
  business_id: string | null;
  exp: number;
}

export function readClaims(token: string | undefined): SessionClaims | null {
  const payload = token?.split(".")[1];
  if (!payload) return null;
  try {
    const base64 = payload.replace(/-/g, "+").replace(/_/g, "/");
    const json = JSON.parse(atob(base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "="))) as Partial<SessionClaims>;
    if (typeof json.sub !== "string" || typeof json.exp !== "number") return null;
    return { sub: json.sub, business_id: typeof json.business_id === "string" ? json.business_id : null, exp: json.exp };
  } catch {
    return null;
  }
}

export function isLive(claims: SessionClaims | null, nowMs = Date.now()): claims is SessionClaims {
  return claims !== null && claims.exp * 1000 > nowMs;
}
