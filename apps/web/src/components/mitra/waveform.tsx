import { cn } from "@/lib/utils";

const bars = [0.5, 0.9, 0.6, 1, 0.7, 0.4, 0.8, 0.55, 0.95, 0.5, 0.75, 0.45];

/** Decorative bars shown only while a sample is playing (docs/06 §7). */
export function Waveform({ className }: { className?: string }) {
  return (
    <span className={cn("flex h-6 items-center gap-[3px]", className)} aria-hidden>
      {bars.map((height, index) => (
        <span
          key={index}
          className="w-[3px] origin-center rounded-full bg-sky-400 motion-safe:animate-wave"
          style={{ height: `${height * 100}%`, animationDelay: `${index * 70}ms` }}
        />
      ))}
    </span>
  );
}
