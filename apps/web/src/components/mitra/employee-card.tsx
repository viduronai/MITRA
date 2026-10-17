"use client";

import { Play, Square } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { useSamplePlayback } from "@/hooks/use-sample-playback";
import { cn } from "@/lib/utils";
import { EmployeeAvatar } from "./employee-avatar";
import { StatusPill, type EmployeeStatus } from "./status-pill";
import { Waveform } from "./waveform";

interface EmployeeCardProps {
  name: string;
  initials?: string;
  /** Translated role, e.g. "Receptionist". */
  role: string;
  status: EmployeeStatus;
  /** Optional one-liner about today, e.g. "9 booked today". */
  summary?: string;
  className?: string;
}

export function EmployeeCard({ name, initials, role, status, summary, className }: EmployeeCardProps) {
  const t = useTranslations("employee");
  const { playingId, toggle } = useSamplePlayback();
  const playing = playingId === "sample";

  return (
    <article
      className={cn(
        "flex flex-col gap-5 rounded-xl border bg-card p-5 text-card-foreground shadow-xs md:p-6",
        className,
      )}
    >
      <div className="flex items-start gap-4">
        <EmployeeAvatar name={name} initials={initials} size="lg" speaking={playing} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h3 className="text-lg leading-[26px] font-semibold md:text-xl md:leading-7">{name}</h3>
            <StatusPill status={status} />
          </div>
          <p className="text-text-muted">{role}</p>
          {summary && <p className="mt-1 text-sm leading-5 text-text-muted">{summary}</p>}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-4">
        <Button variant="secondary" onClick={() => toggle("sample")} aria-pressed={playing}>
          {playing ? <Square aria-hidden /> : <Play aria-hidden />}
          {playing ? t("stopSample") : t("hearSample")}
        </Button>
        {playing && <Waveform />}
      </div>
    </article>
  );
}
