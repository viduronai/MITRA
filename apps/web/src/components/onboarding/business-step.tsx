"use client";

import { Building2, GraduationCap, Stethoscope, Store, type LucideIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useState, useTransition } from "react";
import { saveBusiness, type StepErrorKey } from "@/app/onboarding/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Industry, Locale } from "@/lib/api/types";
import { HOURS_PRESETS, INDUSTRIES, LANGUAGES, type HoursPreset } from "@/lib/onboarding";
import { Choice, ChoiceTick } from "./choice";
import { StepFooter } from "./step-footer";

const industryIcons: Record<Industry, LucideIcon> = {
  clinic: Stethoscope,
  real_estate: Building2,
  education: GraduationCap,
  other: Store,
};

export interface BusinessStepValues {
  name: string;
  industry: Industry;
  city: string;
  languages: Locale[];
  hours: HoursPreset;
}

function Field({ label, htmlFor, hint, error, children }: { label: string; htmlFor?: string; hint?: string; error?: string | null; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {hint && <p className="text-sm leading-5 text-text-muted">{hint}</p>}
      {error && (
        <p role="alert" className="text-sm leading-5 font-medium text-danger-fg">
          {error}
        </p>
      )}
    </div>
  );
}

export function BusinessStep({ initial }: { initial: BusinessStepValues }) {
  const t = useTranslations("onboarding");
  const tb = useTranslations("onboarding.business");
  const ids = { name: useId(), city: useId(), industry: useId(), languages: useId(), hours: useId() };
  const [values, setValues] = useState(initial);
  const [touched, setTouched] = useState(false);
  const [error, setError] = useState<StepErrorKey | null>(null);
  const [pending, startTransition] = useTransition();

  const nameError = touched && !values.name.trim() ? tb("nameRequired") : null;
  const languagesError = touched && values.languages.length === 0 ? tb("languagesRequired") : null;
  const set = <K extends keyof BusinessStepValues>(key: K, value: BusinessStepValues[K]) =>
    setValues((current) => ({ ...current, [key]: value }));

  function toggleLanguage(language: Locale) {
    const has = values.languages.includes(language);
    set("languages", has ? values.languages.filter((l) => l !== language) : [...values.languages, language].slice(0, 3));
  }

  return (
    <form
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        setTouched(true);
        if (!values.name.trim() || values.languages.length === 0) return;
        setError(null);
        startTransition(async () => {
          const result = await saveBusiness(values);
          if (result && !result.ok) setError(result.error);
        });
      }}
      className="flex flex-col gap-7"
    >
      <Field label={tb("name")} htmlFor={ids.name} error={nameError}>
        <Input
          id={ids.name}
          value={values.name}
          onChange={(event) => set("name", event.target.value)}
          placeholder={tb("namePlaceholder")}
          autoComplete="organization"
          maxLength={120}
          aria-invalid={nameError ? true : undefined}
          required
        />
      </Field>

      <fieldset className="flex flex-col gap-3">
        <legend className="mb-3 text-sm leading-5 font-medium">{tb("industry")}</legend>
        <div className="grid grid-cols-2 gap-3">
          {INDUSTRIES.map((industry) => {
            const Icon = industryIcons[industry];
            const checked = values.industry === industry;
            return (
              <Choice
                key={industry}
                type="radio"
                name={ids.industry}
                value={industry}
                checked={checked}
                onChange={() => set("industry", industry)}
                className="min-h-24 flex-col items-start justify-between p-4"
              >
                <Icon className={checked ? "size-6 text-brand-600" : "size-6 text-text-muted"} strokeWidth={1.75} aria-hidden />
                <span className="leading-5 font-medium">{tb(`industries.${industry}`)}</span>
              </Choice>
            );
          })}
        </div>
      </fieldset>

      <Field label={`${tb("city")} · ${tb("optional")}`} htmlFor={ids.city}>
        <Input
          id={ids.city}
          value={values.city}
          onChange={(event) => set("city", event.target.value)}
          placeholder={tb("cityPlaceholder")}
          autoComplete="address-level2"
          maxLength={80}
        />
      </Field>

      <fieldset aria-describedby={`${ids.languages}-hint`}>
        <legend className="mb-3 text-sm leading-5 font-medium">{tb("languages")}</legend>
        <div className="flex flex-wrap gap-2">
          {LANGUAGES.map((language) => {
            const checked = values.languages.includes(language);
            return (
              <Choice
                key={language}
                type="checkbox"
                name={ids.languages}
                value={language}
                checked={checked}
                onChange={() => toggleLanguage(language)}
                disabled={!checked && values.languages.length >= 3}
                className="h-12 rounded-full px-4"
              >
                <ChoiceTick checked={checked} />
                <span lang={language} className="font-medium">
                  {t(`languages.${language}`)}
                </span>
              </Choice>
            );
          })}
        </div>
        <p id={`${ids.languages}-hint`} className="mt-2 text-sm leading-5 text-text-muted">
          {tb("languagesHint")}
        </p>
        {languagesError && (
          <p role="alert" className="mt-1 text-sm leading-5 font-medium text-danger-fg">
            {languagesError}
          </p>
        )}
      </fieldset>

      <fieldset aria-describedby={`${ids.hours}-hint`}>
        <legend className="mb-1 text-sm leading-5 font-medium">{tb("hours")}</legend>
        <p id={`${ids.hours}-hint`} className="mb-3 text-sm leading-5 text-text-muted">
          {tb("hoursHint")}
        </p>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {HOURS_PRESETS.map((preset) => (
            <Choice
              key={preset}
              type="radio"
              name={ids.hours}
              value={preset}
              checked={values.hours === preset}
              onChange={() => set("hours", preset)}
              className="min-h-12 px-4 py-3"
            >
              <ChoiceTick checked={values.hours === preset} />
              <span className="font-medium">{tb(`hoursPresets.${preset}`)}</span>
            </Choice>
          ))}
        </div>
      </fieldset>

      {error && (
        <p role="alert" className="rounded-lg bg-danger/10 px-4 py-3 text-sm leading-5 font-medium text-danger-fg">
          {t(`errors.${error}`)}
        </p>
      )}

      <StepFooter>
        <Button type="submit" size="lg" className="w-full md:w-auto md:min-w-48" disabled={pending} aria-busy={pending}>
          {pending ? t("saving") : t("continue")}
        </Button>
      </StepFooter>
    </form>
  );
}
