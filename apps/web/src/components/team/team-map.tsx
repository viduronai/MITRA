import { ArrowRight, ArrowDown } from "lucide-react";
import { getTranslations } from "next-intl/server";
import { EmployeeAvatar } from "@/components/mitra/employee-avatar";
import { StatusPill } from "@/components/mitra/status-pill";
import type { Team, TeamMember } from "@/lib/team/types";
import { label } from "@/lib/team/i18n";

/** TEAM-03: the team as a left-to-right chain with 7-day counts on each person and arrow. */
export async function TeamMapView({ team }: { team: Team }) {
  const t = await getTranslations("teamMap");
  const members = [...team.members].sort((a, b) => a.position - b.position);

  // Hand-offs between neighbours: the number shown on each arrow.
  const arrow = (from: TeamMember, to: TeamMember) =>
    team.rules
      .filter((r) => r.from_employee_id === from.employee_id && r.to_employee_id === to.employee_id)
      .reduce((sum, r) => sum + r.handoffs_7d, 0);

  return (
    <ol aria-label={t("mapLabel", { name: team.name })} className="flex flex-col items-stretch gap-2 lg:flex-row lg:items-center">
      {members.map((member, i) => (
        <li key={member.employee_id} className="contents">
          <div className="flex-1 rounded-xl border bg-card p-4 shadow-xs">
            <div className="flex items-center gap-3">
              <EmployeeAvatar name={member.name} size="sm" />
              <div className="min-w-0">
                <p className="truncate font-semibold">{member.name}</p>
                <p className="truncate text-sm text-text-muted">{label(t, `roles.${member.team_role}`, member.team_role)}</p>
              </div>
            </div>
            <div className="mt-3">
              <StatusPill status={member.status} />
            </div>
            <dl className="mt-3 grid grid-cols-3 gap-1 text-center text-xs text-text-muted">
              <div>
                <dt>{t("calls")}</dt>
                <dd className="text-base font-semibold text-foreground tabular-nums">{member.calls_7d}</dd>
              </div>
              <div>
                <dt>{t("received")}</dt>
                <dd className="text-base font-semibold text-foreground tabular-nums">{member.received_7d}</dd>
              </div>
              <div>
                <dt>{t("waiting")}</dt>
                <dd className="text-base font-semibold text-foreground tabular-nums">{member.waiting}</dd>
              </div>
            </dl>
          </div>
          {i < members.length - 1 && (
            <div className="flex shrink-0 items-center justify-center gap-1 text-text-muted lg:flex-col" aria-hidden>
              <ArrowDown className="size-5 lg:hidden" />
              <ArrowRight className="hidden size-5 lg:block" />
              <span className="text-xs tabular-nums">{arrow(member, members[i + 1])}</span>
            </div>
          )}
        </li>
      ))}
    </ol>
  );
}
