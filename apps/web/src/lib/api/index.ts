import "server-only";
import type { MitraApi } from "./client";
import { httpApi } from "./http";
import { mockApi } from "./mock";

export { ApiError } from "./client";
export type { MitraApi } from "./client";

/** MITRA_API_MOCK=1 swaps in the in-memory mock (never in production). */
export const isMockApi = process.env.MITRA_API_MOCK === "1" && process.env.NODE_ENV !== "production";

export const api: MitraApi = isMockApi ? mockApi : httpApi;
