"use server";

import { teamApi } from "@/lib/team/api";
import { runAction, validId, type ActionResult } from "@/lib/team/run";
import {
  CHANNELS,
  RULE_RESULTS,
  TASKS,
  type HandoffRule,
  type RuleIn,
  type Staff,
  type TeamChannel,
  type TeamTask,
} from "@/lib/team/types";

const TEMPLATES = ["real_estate", "clinic", "coaching"];
const E164 = /^\+[1-9][0-9]{7,14}$/;

export async function hireTeam(templateId: string): Promise<ActionResult<null>> {
  if (!TEMPLATES.includes(templateId)) return { ok: false, error: "invalid" };
  return runAction("team", async (token) => {
    await teamApi.hire(token, templateId);
    return null;
  });
}

export async function activateTeam(teamId: string): Promise<ActionResult<null>> {
  if (!validId(teamId)) return { ok: false, error: "invalid" };
  return runAction("team", async (token) => {
    await teamApi.activate(token, teamId);
    return null;
  });
}

function validRule(rule: RuleIn): boolean {
  return (
    validId(rule.from_employee_id) &&
    (rule.to_employee_id === null || validId(rule.to_employee_id)) &&
    (rule.team_id == null || validId(rule.team_id)) &&
    RULE_RESULTS.includes(rule.when_result) &&
    TASKS.includes(rule.task as TeamTask) &&
    CHANNELS.includes(rule.channel as TeamChannel) &&
    Number.isInteger(rule.delay_minutes) &&
    rule.delay_minutes >= 0 &&
    rule.delay_minutes <= 10080 &&
    (rule.to_employee_id !== null || rule.task === "brief_staff")
  );
}

export async function addRule(rule: RuleIn): Promise<ActionResult<HandoffRule>> {
  if (!rule || !validRule(rule)) return { ok: false, error: "invalid" };
  return runAction("team", (token) => teamApi.createRule(token, rule));
}

export async function setRuleEnabled(id: string, enabled: boolean): Promise<ActionResult<HandoffRule>> {
  if (!validId(id) || typeof enabled !== "boolean") return { ok: false, error: "invalid" };
  return runAction("team", (token) => teamApi.updateRule(token, id, { enabled }));
}

export async function removeRule(id: string): Promise<ActionResult<null>> {
  if (!validId(id)) return { ok: false, error: "invalid" };
  return runAction("team", async (token) => {
    await teamApi.deleteRule(token, id);
    return null;
  });
}

export async function addStaff(input: {
  name: string;
  phone: string;
  role: string;
  ladder: number | null;
  owner: boolean;
}): Promise<ActionResult<Staff>> {
  const name = typeof input?.name === "string" ? input.name.trim() : "";
  const phone = typeof input?.phone === "string" ? input.phone.replace(/[\s-]/g, "") : "";
  const role = typeof input?.role === "string" ? input.role.trim() : "";
  const ladder = input?.ladder;
  if (!name || name.length > 60 || !E164.test(phone) || role.length > 60) return { ok: false, error: "invalid" };
  if (ladder !== null && (!Number.isInteger(ladder) || ladder < 1 || ladder > 9)) return { ok: false, error: "invalid" };
  return runAction("team", (token) =>
    teamApi.addStaff(token, {
      name,
      phone_e164: phone,
      role_label: role || undefined,
      ladder_position: ladder,
      receives_briefs: true,
      is_owner: Boolean(input.owner),
    }),
  );
}

export async function removeStaff(id: string): Promise<ActionResult<null>> {
  if (!validId(id)) return { ok: false, error: "invalid" };
  return runAction("team", async (token) => {
    await teamApi.deleteStaff(token, id);
    return null;
  });
}

export async function resolveCard(id: string): Promise<ActionResult<null>> {
  if (!validId(id)) return { ok: false, error: "invalid" };
  return runAction("team", async (token) => {
    await teamApi.resolveCard(token, id);
    return null;
  });
}
