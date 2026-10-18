import { PhoneOff } from "lucide-react";
import { useTranslations } from "next-intl";
import { CallRow } from "@/components/mitra/call-row";
import { EmployeeAvatar } from "@/components/mitra/employee-avatar";
import { EmployeeCard } from "@/components/mitra/employee-card";
import { EmptyState } from "@/components/mitra/empty-state";
import { LiveDot } from "@/components/mitra/live-dot";
import { ResultPill } from "@/components/mitra/result-pill";
import { SetupChecklist } from "@/components/mitra/setup-checklist";
import { StatTile } from "@/components/mitra/stat-tile";
import { StatusPill } from "@/components/mitra/status-pill";
import { VoiceCardGroup } from "@/components/mitra/voice-card";
import { Button } from "@/components/ui/button";
import { calls, mockCallDate, requestTime, setupSteps, voices, type CallResult } from "@/lib/mock-data";
import { DsSection, Specimen } from "./ds-section";

const results: CallResult[] = ["booked", "interested", "callBack", "notInterested", "failed"];

export function MitraShowcase() {
  const tSetup = useTranslations("setup");
  const tEmployee = useTranslations("employee");
  const tEmpty = useTranslations("empty");
  const now = requestTime();

  return (
    <DsSection id="mitra" title="Mitra components" description="Product components in src/components/mitra. Copy here follows the selected language.">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Specimen label="<StatTile />" className="lg:col-span-2">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatTile label="Calls today" value="24" trend={{ direction: "up", label: "4 more than yesterday" }} href="#mitra" />
            <StatTile label="Booked" value="9" trend={{ direction: "flat", label: "Same as yesterday" }} />
            <StatTile label="Missed calls rescued" value="6" trend={{ direction: "down", label: "1 fewer than yesterday" }} />
            <StatTile label="Needs you" value="3" highlight />
          </div>
        </Specimen>

        <Specimen label="<ResultPill /> — icon + label, never colour alone">
          <div className="flex flex-wrap gap-2">
            {results.map((result) => (
              <ResultPill key={result} result={result} />
            ))}
          </div>
        </Specimen>

        <Specimen label="<LiveDot /> · <StatusPill /> · <EmployeeAvatar />">
          <div className="flex flex-wrap items-center gap-4">
            <span className="inline-flex items-center gap-2 text-sm">
              <LiveDot /> On a call
            </span>
            <StatusPill status="working" />
            <StatusPill status="paused" />
            <StatusPill status="training" />
          </div>
          <div className="flex items-center gap-4">
            <EmployeeAvatar name="Priya" size="sm" />
            <EmployeeAvatar name="Meena" size="md" />
            <EmployeeAvatar name="Arjun" size="lg" />
            <EmployeeAvatar name="Priya" size="lg" speaking />
          </div>
        </Specimen>

        <Specimen label="<EmployeeCard />">
          <EmployeeCard
            name="Priya"
            role={tEmployee("receptionist")}
            status="working"
            summary={tEmployee("bookedToday", { count: 9 })}
            className="shadow-none"
          />
        </Specimen>

        <Specimen label="<VoiceCardGroup /> — radio select, ▶ sample (UI only)">
          <VoiceCardGroup voices={voices} />
        </Specimen>

        <Specimen label="<CallRow />">
          <ul>
            {calls.slice(0, 3).map((call) => (
              <li key={call.id}>
                <CallRow call={{ ...call, at: mockCallDate(call.at, now) }} href="#mitra" />
              </li>
            ))}
          </ul>
        </Specimen>

        <Specimen label="<SetupChecklist />">
          <SetupChecklist
            title={tSetup("title")}
            steps={setupSteps.map((step) => ({ id: step.key, label: tSetup(step.key, { name: "Priya" }), done: step.done }))}
            action={<Button className="w-full">{tSetup("continue")}</Button>}
            className="shadow-none"
          />
        </Specimen>

        <Specimen label="<EmptyState />" className="lg:col-span-2">
          <EmptyState
            icon={PhoneOff}
            title={tEmpty("callsTitle")}
            description={tEmpty("calls", { name: "Priya" })}
            action={<Button variant="secondary">{tEmpty("callsAction")}</Button>}
          />
        </Specimen>
      </div>
    </DsSection>
  );
}
