import "server-only";
import { redirect } from "next/navigation";
import { cache } from "react";
import { api, ApiError } from "./api";
import type { Business, Employee, MeOut, OnboardingProgress } from "./api/types";
import { requireSession } from "./session";

/**
 * Per-request cached reads for Server Components. A rejected token sends the
 * owner back to login (the proxy clears the stale cookie on ?expired=1).
 */

async function guard<T>(load: () => Promise<T>): Promise<T> {
  try {
    return await load();
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login?expired=1");
    throw error;
  }
}

export const getMe = cache(async (): Promise<MeOut> => {
  const { token } = await requireSession();
  return guard(() => api.me(token));
});

export const getBusiness = cache(async (): Promise<Business | null> => {
  const { token, claims } = await requireSession();
  if (!claims.business_id) return null;
  return guard(() => api.currentBusiness(token));
});

/** Phase 1 has one AI employee per business: the first one hired. */
export const getEmployee = cache(async (): Promise<Employee | null> => {
  const { token, claims } = await requireSession();
  if (!claims.business_id) return null;
  const employees = await guard(() => api.listEmployees(token));
  return employees[0] ?? null;
});

export const getProgress = cache(async (): Promise<OnboardingProgress | null> => {
  const { token, claims } = await requireSession();
  if (!claims.business_id) return null;
  return guard(() => api.progress(token));
});

/** "+919876543210" → "••••3210" */
export function maskPhone(phone: string): string {
  return `••••${phone.replace(/\D/g, "").slice(-4)}`;
}
