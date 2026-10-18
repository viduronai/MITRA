"use client";

import { Play, Square } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { useSamplePlayback } from "@/hooks/use-sample-playback";
import { cn } from "@/lib/utils";
import { Waveform } from "./waveform";

export interface Voice {
  id: string;
  name: string;
  personality: string;
  languages: string[];
}

interface VoiceCardProps {
  voice: Voice;
  groupName: string;
  selected: boolean;
  playing: boolean;
  onSelect: () => void;
  onTogglePlay: () => void;
  /** e.g. the price tier, shown beside the name. */
  badge?: React.ReactNode;
}

/**
 * One selectable voice. The radio and the play button are siblings (not
 * nested) so both stay valid, separately focusable controls.
 */
export function VoiceCard({ voice, groupName, selected, playing, onSelect, onTogglePlay, badge }: VoiceCardProps) {
  const t = useTranslations("voice");

  return (
    <div className="relative">
      <label
        className={cn(
          "flex cursor-pointer gap-3 rounded-xl border bg-card p-4 pr-20 shadow-xs transition-[border-color,background-color] motion-fast hover:border-brand-500/50 has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-ring md:p-5 md:pr-20",
          selected && "border-brand-500 bg-brand-50 hover:border-brand-500",
        )}
      >
        <input
          type="radio"
          name={groupName}
          value={voice.id}
          checked={selected}
          onChange={onSelect}
          className="sr-only"
        />
        <span
          aria-hidden
          className={cn(
            "mt-0.5 inline-flex size-5 shrink-0 items-center justify-center rounded-full border-2 border-text-subtle transition-colors motion-fast",
            selected && "border-brand-600",
          )}
        >
          {selected && <span className="size-2.5 rounded-full bg-brand-600" />}
        </span>
        <span className="flex min-w-0 flex-col gap-1">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-base leading-6 font-semibold">{voice.name}</span>
            {badge}
          </span>
          <span className="text-sm leading-5 text-text-muted">{voice.personality}</span>
          <span className="mt-2 flex flex-wrap gap-1.5">
            {voice.languages.map((language) => (
              <span
                key={language}
                className="inline-flex h-6 items-center rounded-full border bg-surface px-2.5 text-xs font-medium text-text-muted"
              >
                {language}
              </span>
            ))}
          </span>
        </span>
      </label>
      <div className="absolute top-4 right-4 flex flex-col items-center gap-2 md:top-5 md:right-5">
        <Button
          type="button"
          variant="secondary"
          size="icon"
          className="rounded-full"
          onClick={onTogglePlay}
          aria-pressed={playing}
          aria-label={playing ? t("stop", { name: voice.name }) : t("play", { name: voice.name })}
        >
          {playing ? <Square className="size-4" aria-hidden /> : <Play className="size-5 translate-x-px" aria-hidden />}
        </Button>
        {playing && <Waveform className="h-4 w-11 justify-center gap-[2px]" />}
      </div>
    </div>
  );
}

interface VoiceCardGroupProps {
  voices: Voice[];
  defaultValue?: string;
  onValueChange?: (id: string) => void;
  className?: string;
}

/** Radio group of voices; only one sample plays at a time. */
export function VoiceCardGroup({ voices, defaultValue, onValueChange, className }: VoiceCardGroupProps) {
  const t = useTranslations("voice");
  const groupName = useId();
  const [value, setValue] = useState(defaultValue ?? voices[0]?.id);
  const { playingId, toggle } = useSamplePlayback();

  return (
    <fieldset className={cn("grid grid-cols-1 gap-3", className)}>
      <legend className="sr-only">{t("groupLabel")}</legend>
      {voices.map((voice) => (
        <VoiceCard
          key={voice.id}
          voice={voice}
          groupName={groupName}
          selected={value === voice.id}
          playing={playingId === voice.id}
          onSelect={() => {
            setValue(voice.id);
            onValueChange?.(voice.id);
          }}
          onTogglePlay={() => toggle(voice.id)}
        />
      ))}
    </fieldset>
  );
}
