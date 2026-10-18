"use client";

import { useTranslations } from "next-intl";
import { useRef } from "react";
import { cn } from "@/lib/utils";

const LENGTH = 6;

interface OtpInputProps {
  /** Up to six characters; a space marks an empty box. */
  value: string;
  onChange: (value: string) => void;
  /** Called once all six digits are in (typed, pasted or autofilled). */
  onComplete?: (value: string) => void;
  invalid?: boolean;
  disabled?: boolean;
  describedBy?: string;
  autoFocus?: boolean;
}

/**
 * Six boxes for the SMS code. The first box carries autocomplete="one-time-code"
 * so Android/iOS can fill it; pasting or autofilling any box spreads the digits.
 */
export function OtpInput({ value, onChange, onComplete, invalid, disabled, describedBy, autoFocus }: OtpInputProps) {
  const t = useTranslations("auth");
  const refs = useRef<(HTMLInputElement | null)[]>([]);
  // Empty boxes are kept as spaces so digits never shift position.
  const digits = Array.from({ length: LENGTH }, (_, index) => (value[index] ?? "").trim());
  const emit = (next: string[]) => onChange(next.map((digit) => digit || " ").join("").trimEnd());

  function focus(index: number) {
    refs.current[Math.max(0, Math.min(LENGTH - 1, index))]?.focus();
  }

  function write(index: number, input: string) {
    const incoming = input.replace(/\D/g, "");
    if (!incoming) return;
    const next = digits.slice();
    // A multi-digit input (paste/autofill) into the first box replaces the code.
    const start = incoming.length >= LENGTH ? 0 : index;
    for (let i = 0; i < incoming.length && start + i < LENGTH; i++) next[start + i] = incoming[i];
    emit(next);
    focus(Math.min(start + incoming.length, LENGTH - 1));
    if (next.every(Boolean)) onComplete?.(next.join(""));
  }

  function onKeyDown(index: number, event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Backspace") {
      event.preventDefault();
      const next = digits.slice();
      if (next[index]) {
        next[index] = "";
      } else if (index > 0) {
        next[index - 1] = "";
        focus(index - 1);
      }
      emit(next);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      focus(index - 1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      focus(index + 1);
    }
  }

  return (
    <div role="group" aria-label={t("otpLabel")} aria-describedby={describedBy} className="flex justify-between gap-2 sm:gap-3">
      {digits.map((digit, index) => (
        <input
          key={index}
          ref={(element) => {
            refs.current[index] = element;
          }}
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          autoComplete={index === 0 ? "one-time-code" : "off"}
          // maxLength stays open on the first box so autofill can deliver all six digits.
          maxLength={index === 0 ? LENGTH : 1}
          aria-label={t("digitLabel", { n: index + 1 })}
          aria-invalid={invalid || undefined}
          autoFocus={autoFocus && index === 0}
          disabled={disabled}
          value={digit}
          onChange={(event) => write(index, event.target.value.replace(digit, "") || event.target.value)}
          onKeyDown={(event) => onKeyDown(index, event)}
          onPaste={(event) => {
            event.preventDefault();
            write(0, event.clipboardData.getData("text").slice(0, LENGTH));
          }}
          onFocus={(event) => event.target.select()}
          className={cn(
            "h-14 w-full min-w-0 max-w-14 rounded-lg border border-input bg-surface text-center text-2xl font-semibold tabular-nums shadow-xs transition-[border-color] motion-fast focus-visible:border-ring disabled:opacity-60",
            invalid && "border-danger",
          )}
        />
      ))}
    </div>
  );
}
