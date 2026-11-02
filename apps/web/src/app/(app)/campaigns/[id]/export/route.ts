import { NextResponse, type NextRequest } from "next/server";
import { ApiError } from "@/lib/api";
import { campaignsApi } from "@/lib/campaigns/api";
import { getSession } from "@/lib/session";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Campaign results as CSV: proxies core with the session token (owner / manager only). */
export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await getSession();
  if (!session) return NextResponse.redirect(new URL("/login", request.url));
  const { id } = await params;
  if (!UUID.test(id)) return new NextResponse("Not found", { status: 404 });
  try {
    const csv = await campaignsApi.exportCsv(session.token, id);
    return new NextResponse(csv, {
      headers: {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": `attachment; filename="mitra-campaign-${id.slice(0, 8)}.csv"`,
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    const status = error instanceof ApiError && error.status >= 400 ? error.status : 502;
    if (status === 401) return NextResponse.redirect(new URL("/login?expired=1", request.url));
    return new NextResponse("Export failed", { status });
  }
}
