import { getTranslations } from "next-intl/server";
import { VoiceTierPicker } from "@/components/billing/voice-tier-picker";
import { PageHeader } from "@/components/shell/page-header";
import { ActivateTeam, HireTeam } from "@/components/team/hire-team";
import { RuleEditor } from "@/components/team/rule-editor";
import { HandoffCards, StaffLadder } from "@/components/team/staff-ladder";
import { TeamMapView } from "@/components/team/team-map";
import { api } from "@/lib/api";
import type { CatalogVoice, Rate } from "@/lib/api/types";
import { getEmployee } from "@/lib/data";
import { requireSession } from "@/lib/session";
import { teamApi } from "@/lib/team/api";
import type { HandoffCard, Staff, TeamMap, TeamTemplate } from "@/lib/team/types";
import { label } from "@/lib/team/i18n";

export async function generateMetadata() {
  const t = await getTranslations("team");
  return { title: t("title") };
}

const EMPTY_MAP: TeamMap = { teams: [], others: [] };

export default async function TeamPage() {
  const [t, tMap, tBilling, employee] = await Promise.all([
    getTranslations("team"),
    getTranslations("teamMap"),
    getTranslations("billing"),
    getEmployee(),
  ]);
  const { token } = await requireSession();
  // Each panel is optional chrome: one failing call never blanks the whole page.
  const [map, templates, staff, cards, rates, voices] = await Promise.all([
    teamApi.map(token).catch((): TeamMap => EMPTY_MAP),
    teamApi.templates(token).catch((): TeamTemplate[] => []),
    teamApi.staff(token).catch((): Staff[] => []), // owner / manager only
    teamApi.cards(token).catch((): HandoffCard[] => []),
    employee ? api.rates(token).catch((): Rate[] => []) : Promise.resolve([] as Rate[]),
    employee ? api.voices(token).catch((): CatalogVoice[] => []) : Promise.resolve([] as CatalogVoice[]),
  ]);
  const team = map.teams[0];
  const hired = new Set(map.teams.map((x) => x.template_id));
  const members = [...map.teams.flatMap((x) => x.members), ...map.others];

  return (
    <>
      <PageHeader
        title={t("title")}
        subtitle={team ? tMap("subtitleTeam") : t("subtitle", { name: employee?.name ?? "Mitra" })}
        actions={team && !team.active ? <ActivateTeam teamId={team.id} /> : undefined}
      />
      <div className="flex flex-col gap-6">
        <HandoffCards cards={cards} />
        {map.teams.map((x) => (
          <section key={x.id} aria-labelledby={`team-${x.id}`} className="flex flex-col gap-3">
            <h2 id={`team-${x.id}`} className="text-lg font-semibold">
              {x.template_id ? label(tMap, `templates.${x.template_id}`, x.name) : x.name}
            </h2>
            <TeamMapView team={x} />
          </section>
        ))}
        {members.length > 0 && (
          <RuleEditor teamId={team?.id ?? null} members={members} rules={map.teams.flatMap((x) => x.rules)} />
        )}
        {templates.some((tpl) => !hired.has(tpl.id)) && (
          <HireTeam templates={templates.filter((tpl) => !hired.has(tpl.id))} />
        )}
        <div className="grid grid-cols-1 items-start gap-4 md:grid-cols-2">
          <StaffLadder staff={staff} />
          {employee && rates.length > 0 && (
            <section aria-labelledby="tier-title" className="rounded-xl border bg-card p-5 shadow-xs md:p-6">
              <h2 id="tier-title" className="font-semibold">
                {tBilling("tiersTitle")}
              </h2>
              <p className="mt-1 mb-3 text-sm text-text-muted">{tBilling("tiersHint")}</p>
              <VoiceTierPicker
                employeeId={employee.id}
                employeeName={employee.name}
                tier={employee.voice_tier}
                rates={Object.fromEntries(rates.map((r) => [r.tier, Math.round(r.inr_per_min * 100)]))}
                voiceName={voices.find((v) => v.id === employee.voice_id)?.name ?? null}
              />
            </section>
          )}
        </div>
      </div>
    </>
  );
}
