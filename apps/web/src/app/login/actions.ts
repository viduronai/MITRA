"use server";

import { redirect } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { setSession } from "@/lib/session";

export type AuthErrorKey = "phoneInvalid" | "codeIncomplete" | "codeWrong" | "codeExpired" | "tooMany" | "unreachable" | "generic";

export type OtpRequestResult =
  | { ok: true; requestId: string; resendIn: number; devCode?: string }
  | { ok: false; error: AuthErrorKey };

const PHONE_10 = /^[6-9]\d{9}$/;
const CODE_6 = /^\d{6}$/;

function authError(error: unknown, fallback: AuthErrorKey): AuthErrorKey {
  if (!(error instanceof ApiError)) return "generic";
  if (error.status === 0) return "unreachable";
  if (error.status === 429 || /rate|attempt/.test(error.code)) return "tooMany";
  if (/expired/.test(error.code) || error.status === 410) return "codeExpired";
  if (error.status >= 500) return "generic";
  return fallback;
}

/** `phone` is the 10-digit Indian mobile number; +91 is added here. */
export async function requestOtp(phone: string): Promise<OtpRequestResult> {
  const digits = typeof phone === "string" ? phone.replace(/\D/g, "") : "";
  if (!PHONE_10.test(digits)) return { ok: false, error: "phoneInvalid" };
  try {
    const out = await api.requestOtp(`+91${digits}`);
    return {
      ok: true,
      requestId: out.request_id,
      resendIn: out.resend_in,
      // The API only sends dev_code when it runs locally; never forward it from a production build.
      devCode: process.env.NODE_ENV !== "production" ? out.dev_code : undefined,
    };
  } catch (error) {
    return { ok: false, error: authError(error, "phoneInvalid") };
  }
}

export async function verifyOtp(requestId: string, code: string): Promise<{ ok: false; error: AuthErrorKey }> {
  if (typeof code !== "string" || !CODE_6.test(code)) return { ok: false, error: "codeIncomplete" };
  if (typeof requestId !== "string" || requestId.length === 0 || requestId.length > 200) {
    return { ok: false, error: "codeExpired" };
  }
  let next: string;
  try {
    const out = await api.verifyOtp(requestId, code);
    await setSession(out.access_token, out.expires_in);
    next = out.memberships.length > 0 ? "/" : "/onboarding";
  } catch (error) {
    return { ok: false, error: authError(error, "codeWrong") };
  }
  redirect(next);
}
