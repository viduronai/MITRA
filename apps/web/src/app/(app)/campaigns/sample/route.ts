import { NextResponse, type NextRequest } from "next/server";
import { campaignsApi } from "@/lib/campaigns/api";
import { getSession } from "@/lib/session";

/** Sample list to fill in (CALL-15). */
export async function GET(request: NextRequest) {
  const session = await getSession();
  if (!session) return NextResponse.redirect(new URL("/login", request.url));
  try {
    const csv = await campaignsApi.sampleCsv(session.token);
    return new NextResponse(csv, {
      headers: {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": 'attachment; filename="mitra-campaign-sample.csv"',
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return new NextResponse("Download failed", { status: 502 });
  }
}
