"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { ApiError } from "@/lib/api";
import { campaignsApi } from "@/lib/campaigns/api";
import type { Campaign, CampaignIn, CampaignPatch, ListIn, ListPreview } from "@/lib/campaigns/types";
import { requireSession } from "@/lib/session";

export type CampaignErrorKey =
  | "invalidList"
  | "noValidRows"
  | "forbidden"
  | "conflict"
  | "invalid"
  | "unavailable";

export type Result<T> = { ok: true; data: T } | { ok: false; error: CampaignErrorKey; message?: string };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MAX_TEXT = 2_000_000;
const ACTIONS = new Set(["start", "pause", "resume", "cancel"]);

async function run<T>(action: (token: string) => Promise<T>): Promise<Result<T>> {
  const { token } = await requireSession();
  try {
    return { ok: true, data: await action(token) };
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/login?expired=1");
      if (error.status === 403) return { ok: false, error: "forbidden" };
      if (error.code === "invalid_list") return { ok: false, error: "invalidList", message: error.message };
      if (error.status === 409) return { ok: false, error: "conflict", message: error.message };
      if (error.status === 422) return { ok: false, error: "invalid", message: error.message };
    }
    console.error("[campaigns]", error instanceof Error ? error.message : error);
    return { ok: false, error: "unavailable" };
  }
}

function validList(body: ListIn): boolean {
  return typeof body?.text === "string" && body.text.trim().length > 0 && body.text.length <= MAX_TEXT;
}

export async function previewList(body: ListIn): Promise<Result<ListPreview>> {
  if (!validList(body)) return { ok: false, error: "invalidList" };
  return run((token) => campaignsApi.preview(token, body));
}

export async function createCampaign(body: CampaignIn, start: boolean): Promise<Result<Campaign>> {
  if (!validList(body) || !UUID.test(body.employee_id) || !body.name?.trim()) return { ok: false, error: "invalid" };
  const created = await run((token) => campaignsApi.create(token, { ...body, name: body.name.trim().slice(0, 80) }));
  if (!created.ok) return created;
  let campaign = created.data.campaign;
  if (start) {
    const started = await run((token) => campaignsApi.transition(token, campaign.id, "start"));
    if (started.ok) campaign = started.data;
  }
  revalidatePath("/campaigns");
  return { ok: true, data: campaign };
}

export async function campaignAction(id: string, action: string): Promise<Result<Campaign>> {
  if (!UUID.test(id) || !ACTIONS.has(action)) return { ok: false, error: "invalid" };
  const result = await run((token) =>
    campaignsApi.transition(token, id, action as "start" | "pause" | "resume" | "cancel"),
  );
  revalidatePath(`/campaigns/${id}`);
  revalidatePath("/campaigns");
  return result;
}

export async function editCampaign(id: string, patch: CampaignPatch): Promise<Result<Campaign>> {
  if (!UUID.test(id)) return { ok: false, error: "invalid" };
  const result = await run((token) => campaignsApi.edit(token, id, patch));
  revalidatePath(`/campaigns/${id}`);
  return result;
}

export async function extendCampaign(id: string, body: ListIn): Promise<Result<{ added: number; skipped: number }>> {
  if (!UUID.test(id) || !validList(body)) return { ok: false, error: "invalidList" };
  const result = await run((token) => campaignsApi.extend(token, id, body));
  revalidatePath(`/campaigns/${id}`);
  return result.ok ? { ok: true, data: { added: result.data.added, skipped: result.data.skipped_recent } } : result;
}

export async function setChannels(channels: number): Promise<Result<{ channels: number }>> {
  if (!Number.isInteger(channels) || channels < 1 || channels > 50) return { ok: false, error: "invalid" };
  const result = await run((token) => campaignsApi.setChannels(token, channels));
  revalidatePath("/campaigns");
  return result;
}
