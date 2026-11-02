import "server-only";
import { refresh } from "next/cache";
import { redirect } from "next/navigation";
import { ApiError } from "@/lib/api";
import { requireSession } from "@/lib/session";

/** Result of a team / routines / live server action (inputs validated there; core re-validates). */
export type ActionErrorKey = "generic" | "unreachable" | "invalid" | "forbidden" | "conflict" | "ended";
export type ActionResult<T = null> = { ok: true; data: T } | { ok: false; error: ActionErrorKey };

export const ID_RE = /^[0-9a-f-]{36}$/i;
export const validId = (id: unknown): id is string => typeof id === "string" && ID_RE.test(id);

function fail(error: unknown, scope: string): { ok: false; error: ActionErrorKey } {
  if (error instanceof ApiError) {
    if (error.status === 401) redirect("/login?expired=1");
    if (error.status === 0) return { ok: false, error: "unreachable" };
    if (error.status === 403) return { ok: false, error: "forbidden" };
    if (error.status === 422) return { ok: false, error: "invalid" };
    if (error.status === 409) return { ok: false, error: error.code === "call_ended" ? "ended" : "conflict" };
  }
  console.error(`[${scope}]`, error instanceof Error ? error.message : error);
  return { ok: false, error: "generic" };
}

export async function runAction<T>(
  scope: string,
  load: (token: string) => Promise<T>,
  { revalidate = true }: { revalidate?: boolean } = {},
): Promise<ActionResult<T>> {
  const { token } = await requireSession();
  try {
    const data = await load(token);
    if (revalidate) refresh();
    return { ok: true, data };
  } catch (error) {
    return fail(error, scope);
  }
}
