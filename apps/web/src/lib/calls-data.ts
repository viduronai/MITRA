import "server-only";
import { notFound, redirect } from "next/navigation";
import { api, ApiError } from "./api";
import type { CallDetail, CallFilters, CallList, CustomerDetail, CustomerList, HomeSummary } from "./api/types";
import { requireSession } from "./session";

/**
 * Reads for Calls, Customers and Home. 401 → login; 404 → the page's not-found.
 * Returns null when the API is unreachable, so pages can show an error state.
 */
async function load<T>(read: (token: string) => Promise<T>): Promise<T | null> {
  const { token, claims } = await requireSession();
  if (!claims.business_id) return null;
  try {
    return await read(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login?expired=1");
    if (error instanceof ApiError && error.status === 404) notFound();
    console.error("[calls-data]", error instanceof Error ? error.message : error);
    return null;
  }
}

export const getHomeSummary = (): Promise<HomeSummary | null> => load((t) => api.homeSummary(t));
export const getCalls = (filters: CallFilters): Promise<CallList | null> => load((t) => api.listCalls(t, filters));
export const getCall = (id: string): Promise<CallDetail | null> => load((t) => api.getCall(t, id));
export const getCustomers = (q?: string): Promise<CustomerList | null> => load((t) => api.listCustomers(t, q));
export const getCustomer = (id: string): Promise<CustomerDetail | null> => load((t) => api.getCustomer(t, id));

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Path ids are validated before they reach the API. */
export function validId(id: string): string {
  if (!UUID.test(id)) notFound();
  return id;
}
