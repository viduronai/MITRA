"use server";

import { refresh } from "next/cache";
import { redirect } from "next/navigation";
import { ApiError } from "@/lib/api";
import { telephonyApi } from "@/lib/telephony/api";
import type { ForwardingTest, KycDocument, PhoneNumber } from "@/lib/telephony/types";
import { requireSession } from "@/lib/session";

/** Inputs are validated here (system boundary); core re-validates everything. */
export type ConnectErrorKey = "generic" | "unreachable" | "invalid" | "forbidden" | "conflict";
export type ConnectResult<T = null> = { ok: true; data: T } | { ok: false; error: ConnectErrorKey };

const ID_RE = /^[0-9a-f-]{36}$/i;
const DOCUMENTS: KycDocument[] = ["gst", "shop_establishment", "udyam", "pan", "clinic_registration"];

function fail(error: unknown): { ok: false; error: ConnectErrorKey } {
  if (error instanceof ApiError) {
    if (error.status === 401) redirect("/login?expired=1");
    if (error.status === 0) return { ok: false, error: "unreachable" };
    if (error.status === 403) return { ok: false, error: "forbidden" };
    if (error.status === 422) return { ok: false, error: "invalid" };
    if (error.status === 409) return { ok: false, error: "conflict" };
  }
  console.error("[connect]", error instanceof Error ? error.message : error);
  return { ok: false, error: "generic" };
}

async function run<T>(load: (token: string) => Promise<T>): Promise<ConnectResult<T>> {
  const { token } = await requireSession();
  try {
    const data = await load(token);
    refresh();
    return { ok: true, data };
  } catch (error) {
    return fail(error);
  }
}

const validId = (id: unknown): id is string => typeof id === "string" && ID_RE.test(id);

export async function requestNumber(city: string, type: "local" | "mobile_virtual"): Promise<ConnectResult<PhoneNumber>> {
  const name = typeof city === "string" ? city.trim() : "";
  if (!name || name.length > 80 || (type !== "local" && type !== "mobile_virtual")) return { ok: false, error: "invalid" };
  return run((token) => telephonyApi.requestNumber(token, { city: name, type }));
}

/** KYC upload placeholder: only the document type and file name are sent, never the file. */
export async function submitKyc(id: string, document: KycDocument, fileName: string): Promise<ConnectResult<PhoneNumber>> {
  const file = typeof fileName === "string" ? fileName.trim() : "";
  if (!validId(id) || !DOCUMENTS.includes(document) || !file || file.length > 200) return { ok: false, error: "invalid" };
  return run((token) => telephonyApi.submitKyc(token, id, document, file));
}

export async function showMyName(id: string, displayName: string): Promise<ConnectResult<PhoneNumber>> {
  const name = typeof displayName === "string" ? displayName.trim() : "";
  if (!validId(id) || !name || name.length > 60) return { ok: false, error: "invalid" };
  return run(async (token) => {
    await telephonyApi.rename(token, id, name);
    return telephonyApi.startCallerName(token, id);
  });
}

export async function testForwarding(id: string): Promise<ConnectResult<ForwardingTest>> {
  if (!validId(id)) return { ok: false, error: "invalid" };
  return run((token) => telephonyApi.testForwarding(token, id));
}

export async function resumeNumber(id: string): Promise<ConnectResult<PhoneNumber>> {
  if (!validId(id)) return { ok: false, error: "invalid" };
  return run((token) => telephonyApi.resume(token, id));
}
