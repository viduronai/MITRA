import { NextResponse, type NextRequest } from "next/server";
import { ApiError } from "@/lib/api";
import { getSession } from "@/lib/session";
import { liveApi } from "@/lib/team/api";
import { ID_RE } from "@/lib/team/run";

/**
 * Thin BFF for the live transcript poll: the browser never sees the session token; this
 * route reads the httpOnly cookie and asks core for turns after `after`.
 */
export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const session = await getSession();
  if (!session) return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  if (!ID_RE.test(id)) return NextResponse.json({ error: "invalid" }, { status: 422 });
  const after = Number(request.nextUrl.searchParams.get("after") ?? "0");
  try {
    const detail = await liveApi.detail(session.token, id, Number.isFinite(after) ? after : 0);
    return NextResponse.json(detail, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    const status = error instanceof ApiError && error.status > 0 ? error.status : 502;
    return NextResponse.json({ error: "unavailable" }, { status });
  }
}
