import "server-only";
import { notFound, redirect } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { getMe } from "@/lib/data";
import { requireSession } from "@/lib/session";
import { campaignsApi } from "./api";

/** Session token + whether this member may run campaigns (owners and managers; staff view). */
export async function campaignSession(): Promise<{ token: string; canManage: boolean }> {
  const [{ token, claims }, me] = await Promise.all([requireSession(), getMe()]);
  const role = me.memberships.find((m) => m.business_id === claims.business_id)?.role;
  return { token, canManage: role === "owner" || role === "manager" };
}

/** Load from core; 401 -> login, 404 -> not found page, anything else -> null (shown as unavailable). */
export async function load<T>(fn: () => Promise<T>): Promise<T | null> {
  try {
    return await fn();
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login?expired=1");
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) notFound();
    console.error("[campaigns]", error instanceof Error ? error.message : error);
    return null;
  }
}

export async function employeeOptions(token: string): Promise<{ id: string; name: string }[]> {
  const employees = (await load(() => api.listEmployees(token))) ?? [];
  return employees.map((e) => ({ id: e.id, name: e.name }));
}

export { campaignsApi };
