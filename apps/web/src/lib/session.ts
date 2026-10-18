import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { isLive, readClaims, SESSION_COOKIE, type SessionClaims } from "./session-claims";

/**
 * The session JWT lives only in an httpOnly, SameSite=Lax cookie set by server
 * actions. Browser JavaScript never sees it; pages and actions call the API
 * server-side with it (thin BFF).
 */

const DEFAULT_MAX_AGE = 60 * 60 * 24 * 7;

export async function setSession(token: string, expiresIn?: number): Promise<void> {
  (await cookies()).set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: Math.max(60, Math.min(expiresIn ?? DEFAULT_MAX_AGE, DEFAULT_MAX_AGE * 4)),
  });
}

export async function clearSession(): Promise<void> {
  (await cookies()).delete(SESSION_COOKIE);
}

export async function getSession(): Promise<{ token: string; claims: SessionClaims } | null> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const claims = readClaims(token);
  return token && isLive(claims) ? { token, claims } : null;
}

/** For pages and actions behind login. The proxy normally redirects first. */
export async function requireSession(): Promise<{ token: string; claims: SessionClaims }> {
  const session = await getSession();
  if (!session) redirect("/login");
  return session;
}
