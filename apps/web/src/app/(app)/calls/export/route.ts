import { NextResponse, type NextRequest } from "next/server";
import { api, ApiError } from "@/lib/api";
import type { CallFilters } from "@/lib/api/types";
import { isLocale } from "@/i18n/config";
import { isApiResult } from "@/lib/calls";
import { getSession } from "@/lib/session";

/** CSV export (REP-06): proxies core with the session token, same filters as /calls. */
export async function GET(request: NextRequest) {
  const session = await getSession();
  if (!session) return NextResponse.redirect(new URL("/login", request.url));
  const params = request.nextUrl.searchParams;
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
  const result = params.get("result") ?? "";
  const language = params.get("language");
  const filters: CallFilters = {
    result: isApiResult(result) ? [result] : undefined,
    language: isLocale(language) ? language : undefined,
    q: params.get("q")?.trim().slice(0, 100) || undefined,
    date_from: params.get("when") === "today" ? today : undefined,
    date_to: params.get("when") === "today" ? today : undefined,
  };
  try {
    const csv = await api.exportCalls(session.token, filters);
    return new NextResponse(csv, {
      headers: {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": `attachment; filename="mitra-calls-${today}.csv"`,
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    const status = error instanceof ApiError && error.status >= 400 ? error.status : 502;
    if (status === 401) return NextResponse.redirect(new URL("/login?expired=1", request.url));
    return new NextResponse("Export failed", { status });
  }
}
