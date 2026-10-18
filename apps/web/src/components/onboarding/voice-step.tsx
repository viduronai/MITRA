"use client";

import { useTranslations } from "next-intl";
import { useId, useState, useTransition } from "react";
import { saveVoice, type StepErrorKey } from "@/app/onboarding/actions";
import { VoiceCard } from "@/components/mitra/voice-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useSamplePlayback } from "@/hooks/use-sample-playback";
import type { CatalogVoice, VoiceTier } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { StepFooter } from "./step-footer";

const tierTone: Record<VoiceTier, string> = {
  smart: "bg-surface-2 text-text-muted",
  natural: "bg-brand-50 text-brand-700",
  signature: "bg-sky-100 text-sky-ink",
};

interface VoiceStepProps {
  voices: CatalogVoice[];
  /** Already formatted, e.g. { natural: "₹4.5" }. */
  prices: Partial<Record<VoiceTier, string>>;
  initialVoiceId: string | null;
  initialName: string;
}

export function VoiceStep({ voices, prices, initialVoiceId, initialName }: VoiceStepProps) {
  const t = useTranslations("onboarding");
  const tv = useTranslations("onboarding.voice");
  const group = useId();
  const nameId = useId();
  const [voiceId, setVoiceId] = useState(initialVoiceId ?? voices.find((v) => v.tier === "natural")?.id ?? voices[0]?.id ?? null);
  const [name, setName] = useState(initialName);
  // Until the owner types a name, the name follows the chosen voice.
  const [nameEdited, setNameEdited] = useState(Boolean(initialVoiceId));
  const [touched, setTouched] = useState(false);
  const [error, setError] = useState<StepErrorKey | null>(null);
  const [pending, startTransition] = useTransition();
  const { playingId, toggle } = useSamplePlayback();
  const nameError = touched && !name.trim() ? tv("nameRequired") : null;

  return (
    <form
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        setTouched(true);
        if (!voiceId || !name.trim()) return;
        setError(null);
        startTransition(async () => {
          const result = await saveVoice(voiceId, name.trim());
          if (result && !result.ok) setError(result.error);
        });
      }}
    >
      {voices.length === 0 ? (
        <p className="rounded-xl border border-dashed px-5 py-8 text-center text-text-muted">{tv("noVoices")}</p>
      ) : (
        <fieldset className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <legend className="sr-only">{tv("title")}</legend>
          {voices.map((voice) => (
            <VoiceCard
              key={voice.id}
              voice={{
                id: voice.id,
                name: voice.name,
                personality: [voice.personality, voice.dialect].filter(Boolean).join(" · "),
                languages: voice.languages.map((language) => t(`languages.${language}`)),
              }}
              groupName={group}
              selected={voiceId === voice.id}
              playing={playingId === voice.id}
              onSelect={() => {
                setVoiceId(voice.id);
                if (!nameEdited) setName(voice.name);
              }}
              onTogglePlay={() => toggle(voice.id)}
              badge={
                <span className={cn("inline-flex h-6 items-center rounded-full px-2.5 text-xs font-medium whitespace-nowrap", tierTone[voice.tier])}>
                  {tv(`tiers.${voice.tier}`)}
                  {prices[voice.tier] && ` · ${tv("perMin", { price: prices[voice.tier]! })}`}
                </span>
              }
            />
          ))}
        </fieldset>
      )}
      <p className="mt-3 text-sm leading-5 text-text-muted">{tv("tierHint")}</p>

      <div className="mt-8 flex max-w-md flex-col gap-2">
        <Label htmlFor={nameId}>{tv("nameLabel")}</Label>
        <Input
          id={nameId}
          value={name}
          onChange={(event) => {
            setName(event.target.value);
            setNameEdited(true);
          }}
          maxLength={60}
          autoComplete="off"
          aria-invalid={nameError ? true : undefined}
          aria-describedby={`${nameId}-hint`}
        />
        <p id={`${nameId}-hint`} className="text-sm leading-5 text-text-muted">
          {tv("nameHint")}
        </p>
        {nameError && (
          <p role="alert" className="text-sm leading-5 font-medium text-danger-fg">
            {nameError}
          </p>
        )}
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-lg bg-danger/10 px-4 py-3 text-sm leading-5 font-medium text-danger-fg">
          {t(`errors.${error}`)}
        </p>
      )}

      <StepFooter backHref="/onboarding?step=teach">
        <Button type="submit" size="lg" className="w-full md:w-auto md:min-w-48" disabled={pending || !voiceId} aria-busy={pending}>
          {pending ? t("saving") : t("continue")}
        </Button>
      </StepFooter>
    </form>
  );
}
