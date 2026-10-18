import { NextResponse, type NextRequest } from "next/server";
import { isLive, readClaims, SESSION_COOKIE } from "@/lib/session-claims";

/**
 * Routing guard (not the security boundary — services/core verifies every
 * token). Logged out → /login. Logged in without a business → /onboarding.
 * Logged in on /login → onwards.
 */
export function proxy(request: NextRequest) {
  const { pathname, searchParams } = request.nextUrl;
  const claims = readClaims(request.cookies.get(SESSION_COOKIE)?.value);
  const live = isLive(claims);
  const to = (path: string) => NextResponse.redirect(new URL(path, request.url));

  if (pathname === "/login") {
    // ?expired=1: the API rejected the token, so drop it and show login.
    if (searchParams.has("expired") || (claims && !live)) {
      const response = NextResponse.next();
      response.cookies.delete(SESSION_COOKIE);
      return response;
    }
    if (live) return to(claims.business_id ? "/" : "/onboarding");
    return NextResponse.next();
  }

  if (!live) {
    const response = to("/login");
    if (claims) response.cookies.delete(SESSION_COOKIE);
    return response;
  }
  if (!claims.business_id && pathname !== "/onboarding") return to("/onboarding");
  return NextResponse.next();
}

export const config = {
  // App routes only: skip Next internals, files with an extension and the
  // internal /design-system reference.
  matcher: ["/((?!_next/|design-system|favicon\\.ico|.*\\.[a-zA-Z0-9]+$).*)"],
};
