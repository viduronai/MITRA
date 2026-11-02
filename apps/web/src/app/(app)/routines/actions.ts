"use server";

import { routinesApi } from "@/lib/team/api";
import { runAction, validId, type ActionResult } from "@/lib/team/run";
import {
  AUDIENCES,
  EVENTS,
  GOALS,
  WEEKDAYS,
  type DryRun,
  type Routine,
  type RoutineRun,
  type RoutineSpec,
} from "@/lib/team/types";

const HHMM = /^([01][0-9]|2[0-3]):[0-5][0-9]$/;

/** Validate the builder's spec here (system boundary); core validates it again. */
function validSpec(spec: RoutineSpec): boolean {
  if (!spec || typeof spec !== "object") return false;
  const { trigger, action } = spec;
  if (!action || !validId(action.employee_id) || !GOALS.includes(action.goal)) return false;
  if (action.verb !== "call" && action.verb !== "whatsapp") return false;
  if (!Number.isInteger(spec.approval_over) || spec.approval_over < 0 || spec.approval_over > 10000) return false;
  if (trigger?.type === "schedule") {
    return (
      Array.isArray(trigger.days) &&
      trigger.days.length > 0 &&
      trigger.days.every((d) => WEEKDAYS.includes(d)) &&
      HHMM.test(trigger.time) &&
      spec.audience !== null &&
      AUDIENCES.includes(spec.audience)
    );
  }
  if (trigger?.type === "event") {
    return (
      EVENTS.includes(trigger.event) &&
      Number.isInteger(trigger.delay_minutes) &&
      trigger.delay_minutes >= 0 &&
      trigger.delay_minutes <= 10080
    );
  }
  return false;
}

export async function dryRun(spec: RoutineSpec): Promise<ActionResult<DryRun>> {
  if (!validSpec(spec)) return { ok: false, error: "invalid" };
  return runAction("routines", (token) => routinesApi.dryRun(token, spec), { revalidate: false });
}

export async function saveRoutine(name: string, spec: RoutineSpec, enabled: boolean): Promise<ActionResult<Routine>> {
  const clean = typeof name === "string" ? name.trim() : "";
  if (!clean || clean.length > 120 || !validSpec(spec)) return { ok: false, error: "invalid" };
  return runAction("routines", (token) => routinesApi.create(token, { name: clean, spec, enabled: Boolean(enabled) }));
}

export async function addFromLibrary(libraryId: string): Promise<ActionResult<Routine>> {
  if (typeof libraryId !== "string" || !/^[a-z_]{1,40}$/.test(libraryId)) return { ok: false, error: "invalid" };
  return runAction("routines", (token) => routinesApi.fromLibrary(token, libraryId));
}

export async function setRoutineEnabled(id: string, enabled: boolean): Promise<ActionResult<Routine>> {
  if (!validId(id) || typeof enabled !== "boolean") return { ok: false, error: "invalid" };
  return runAction("routines", (token) => routinesApi.update(token, id, { enabled }));
}

export async function deleteRoutine(id: string): Promise<ActionResult<null>> {
  if (!validId(id)) return { ok: false, error: "invalid" };
  return runAction("routines", async (token) => {
    await routinesApi.remove(token, id);
    return null;
  });
}

export async function runRoutineNow(id: string): Promise<ActionResult<RoutineRun>> {
  if (!validId(id)) return { ok: false, error: "invalid" };
  return runAction("routines", (token) => routinesApi.runNow(token, id));
}

export async function decideRun(runId: string, approved: boolean): Promise<ActionResult<RoutineRun>> {
  if (!validId(runId) || typeof approved !== "boolean") return { ok: false, error: "invalid" };
  return runAction("routines", (token) => routinesApi.decide(token, runId, approved));
}
