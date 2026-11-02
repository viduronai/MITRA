"use server";

import { liveApi } from "@/lib/team/api";
import { runAction, validId, type ActionResult } from "@/lib/team/run";

/** CALL-18: a private instruction the AI follows for the rest of the call. */
export async function whisper(callId: string, text: string): Promise<ActionResult<null>> {
  const clean = typeof text === "string" ? text.trim() : "";
  if (!validId(callId) || !clean || clean.length > 300) return { ok: false, error: "invalid" };
  return runAction(
    "live",
    async (token) => {
      await liveApi.whisper(token, callId, clean);
      return null;
    },
    { revalidate: false },
  );
}

/** Transfer the call to the signed-in owner/manager's own phone. */
export async function takeOver(callId: string): Promise<ActionResult<{ to_last4: string }>> {
  if (!validId(callId)) return { ok: false, error: "invalid" };
  return runAction("live", (token) => liveApi.takeover(token, callId), { revalidate: false });
}
