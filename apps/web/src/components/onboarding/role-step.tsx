"use client";

import { BellRing, IndianRupee, Lock, PhoneIncoming, PhoneOutgoing, Play, Sparkles, Square, type LucideIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useState, useTransition } from "react";
import { chooseRole, type StepErrorKey } from "@/app/onboarding/actions";
import { Waveform } from "@/components/mitra/waveform";
import { Button } from "@/components/ui/button";
import { useSamplePlayback } from "@/hooks/use-sample-playback";
import type { RoleTemplateId } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { StepFooter } from "./step-footer";

const roleIcons: Record<RoleTemplateId, LucideIcon> = {
  receptionist: PhoneIncoming,
  lead_caller: PhoneOutgoing,
  reminder_caller: BellRing,
  payment_caller: IndianRupee,
};

interface RoleStepProps {
  roles: RoleTemplateId[];
  recommended: RoleTemplateId;
  /** Set once the employee is hired: the role can't change in Step 2. */
  hiredRole: RoleTemplateId | null;
}

export function RoleStep({ roles, recommended, hiredRole }: RoleStepProps) {
  const t = useTranslations("onboarding");
  const tr = useTranslations("onboarding.role");
  const group = useId();
  const [selected, setSelected] = useState<RoleTemplateId>(hiredRole ?? recommended);
  const [error, setError] = useState<StepErrorKey | null>(null);
  const [pending, startTransition] = useTransition();
  const { playingId, toggle } = useSamplePlayback();

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        setError(null);
        startTransition(async () => {
          const result = await chooseRole(selected, tr(`defaultNames.${selected}`));
          if (result && !result.ok) setError(result.error);
        });
      }}
    >
      {hiredRole && (
        <p className="mb-4 flex items-start gap-2 rounded-lg bg-surface-2 px-4 py-3 text-sm leading-5 text-text-muted">
          <Lock className="mt-0.5 size-4 shrink-0" aria-hidden />
          {tr("locked", { role: tr(`names.${hiredRole}`) })}
        </p>
      )}
      <fieldset className="grid grid-cols-1 gap-3 md:grid-cols-2 md:gap-4">
        <legend className="sr-only">{tr("title")}</legend>
        {roles.map((role) => {
          const Icon = roleIcons[role];
          const checked = selected === role;
          const playing = playingId === role;
          const disabled = Boolean(hiredRole) && role !== hiredRole;
          return (
            <div key={role} className="relative">
              <label
                className={cn(
                  "flex h-full min-h-40 cursor-pointer flex-col gap-3 rounded-xl border bg-card p-5 shadow-xs transition-[border-color,background-color,transform] motion-fast hover:border-brand-500/50 has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-ring md:p-6",
                  checked && "border-brand-500 bg-brand-50 hover:border-brand-500",
                  disabled && "cursor-not-allowed opacity-50 hover:border-border",
                )}
              >
                <input
                  type="radio"
                  name={group}
                  value={role}
                  checked={checked}
                  disabled={disabled}
                  onChange={() => setSelected(role)}
                  className="sr-only"
                />
                <span className="flex items-center gap-3 pr-14">
                  <span
                    aria-hidden
                    className={cn(
                      "inline-flex size-11 shrink-0 items-center justify-center rounded-full",
                      checked ? "bg-brand-600 text-on-brand" : "bg-surface-2 text-text-muted",
                    )}
                  >
                    <Icon className="size-5" strokeWidth={1.75} />
                  </span>
                  <span className="text-lg leading-[26px] font-semibold">{tr(`names.${role}`)}</span>
                </span>
                <span className="text-text-muted">{tr(`descriptions.${role}`)}</span>
                {role === recommended && (
                  <span className="mt-auto inline-flex h-7 w-fit items-center gap-1.5 rounded-full bg-sky-100 px-2.5 text-[13px] leading-5 font-medium text-sky-ink">
                    <Sparkles className="size-3.5" aria-hidden />
                    {tr("recommended")}
                  </span>
                )}
              </label>
              <div className="absolute top-5 right-5 flex flex-col items-center gap-2 md:top-6 md:right-6">
                <Button
                  type="button"
                  variant="secondary"
                  size="icon"
                  className="rounded-full"
                  onClick={() => toggle(role)}
                  aria-pressed={playing}
                  aria-label={`${playing ? tr("stopSample") : tr("hearSample")} · ${tr(`names.${role}`)}`}
                >
                  {playing ? <Square className="size-4" aria-hidden /> : <Play className="size-5 translate-x-px" aria-hidden />}
                </Button>
                {playing && <Waveform className="h-4 w-11 justify-center gap-[2px]" />}
              </div>
            </div>
          );
        })}
      </fieldset>

      {error && (
        <p role="alert" className="mt-4 rounded-lg bg-danger/10 px-4 py-3 text-sm leading-5 font-medium text-danger-fg">
          {t(`errors.${error}`)}
        </p>
      )}

      <StepFooter backHref="/onboarding?step=business">
        <Button type="submit" size="lg" className="w-full md:w-auto md:min-w-48" disabled={pending} aria-busy={pending}>
          {pending ? t("saving") : t("continue")}
        </Button>
      </StepFooter>
    </form>
  );
}
