import { PartyPopper } from "lucide-react";
import { cookies } from "next/headers";
import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { BusinessStep } from "@/components/onboarding/business-step";
import { GoLiveStep } from "@/components/onboarding/go-live-step";
import { RoleStep } from "@/components/onboarding/role-step";
import { StepHeader, Stepper } from "@/components/onboarding/stepper";
import { TeachStep } from "@/components/onboarding/teach-step";
import { TestCallStep } from "@/components/onboarding/test-call-step";
import { VoiceStep } from "@/components/onboarding/voice-step";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { Business, CatalogVoice, Employee, OnboardingStepKey, VoiceTier } from "@/lib/api/types";
import { getBusiness, getEmployee, getMe, getProgress, maskPhone } from "@/lib/data";
import { formatList, formatRate } from "@/lib/format";
import {
  DEFAULT_HOURS,
  DEFAULT_ROLE,
  HOURS_COOKIE,
  isHoursPreset,
  isStepKey,
  presetFromHours,
  ROLES,
} from "@/lib/onboarding";
import { requireSession } from "@/lib/session";

type Ctx = { token: string; business: Business | null; employee: Employee | null; locale: string };

async function businessStep({ business, employee }: Ctx) {
  const t = await getTranslations("onboarding.business");
  const stored = (await cookies()).get(HOURS_COOKIE)?.value;
  const hours = presetFromHours(employee?.working_hours) ?? (isHoursPreset(stored) ? stored : DEFAULT_HOURS);
  return (
    <>
      <StepHeader title={t("title")} subtitle={t("subtitle")} />
      <BusinessStep
        initial={{
          name: business?.name ?? "",
          industry: business?.industry ?? "clinic",
          city: business?.city ?? "",
          languages: business?.languages ?? ["te", "en"],
          hours,
        }}
      />
    </>
  );
}

async function roleStep({ token, business, employee }: Ctx) {
  const [t, templates] = await Promise.all([getTranslations("onboarding.role"), api.roleTemplates(token)]);
  const industry = business?.industry ?? "other";
  const known = templates.map((template) => template.id).filter((id) => ROLES.includes(id));
  const recommended = templates.find((template) => template.default_for.includes(industry))?.id ?? DEFAULT_ROLE[industry];
  return (
    <>
      <StepHeader title={t("title")} subtitle={t("subtitle")} />
      <RoleStep roles={known.length ? known : ROLES} recommended={recommended} hiredRole={employee?.role_template ?? null} />
    </>
  );
}

async function teachStep({ token, employee }: Ctx) {
  const [t, sources, facts, gaps] = await Promise.all([
    getTranslations("onboarding.teach"),
    api.listSources(token),
    api.listFacts(token),
    api.listGaps(token),
  ]);
  const name = employee?.name ?? "Mitra";
  return (
    <>
      <StepHeader title={t("title", { name })} subtitle={t("subtitle", { name })} />
      <TeachStep initial={{ sources, facts, gaps }} />
    </>
  );
}

async function voiceStep({ token, business, employee, locale }: Ctx) {
  const languages = business?.languages ?? ["en"];
  const [t, tLang, rates, ...lists] = await Promise.all([
    getTranslations("onboarding.voice"),
    getTranslations("onboarding.languages"),
    api.rates(token),
    ...languages.map((language) => api.voices(token, language)),
  ]);
  const voices = [...new Map((lists as CatalogVoice[][]).flat().map((voice) => [voice.id, voice])).values()];
  const prices = Object.fromEntries(rates.map((rate) => [rate.tier, formatRate(rate.inr_per_min, locale)])) as Partial<Record<VoiceTier, string>>;
  return (
    <>
      <StepHeader title={t("title")} subtitle={t("subtitle", { languages: formatList(languages.map((l) => tLang(l)), locale) })} />
      <VoiceStep voices={voices} prices={prices} initialVoiceId={employee?.voice_id ?? null} initialName={employee?.name ?? ""} />
    </>
  );
}

async function testCallStep({ employee }: Ctx) {
  const [t, me] = await Promise.all([getTranslations("onboarding.test"), getMe()]);
  const name = employee?.name ?? "Mitra";
  return (
    <>
      <StepHeader title={t("title")} subtitle={t("subtitle", { name })} />
      <TestCallStep employeeName={name} maskedPhone={maskPhone(me.user.phone_e164)} />
    </>
  );
}

async function goLiveStep({ employee }: Ctx) {
  const t = await getTranslations("onboarding.live");
  const name = employee?.name ?? "Mitra";
  return (
    <>
      <StepHeader title={t("title")} subtitle={t("subtitle", { name })} />
      <GoLiveStep employeeName={name} />
    </>
  );
}

async function DoneScreen({ employeeName }: { employeeName: string }) {
  const t = await getTranslations("onboarding.live");
  return (
    <div className="mx-auto flex max-w-lg flex-col items-center py-10 text-center md:py-16">
      <span className="relative mb-6 inline-flex size-20 items-center justify-center rounded-full bg-brand-50 text-brand-700">
        <PartyPopper className="size-9" strokeWidth={1.75} aria-hidden />
        <span className="absolute top-2 right-2 size-3 rounded-full bg-sky-400" aria-hidden />
      </span>
      <p className="eyebrow text-text-muted">{t("successEyebrow")}</p>
      <h1 className="mt-2 text-[28px] leading-[34px] font-semibold tracking-tight md:text-4xl md:leading-[42px]">{t("successTitle")}</h1>
      <p className="mt-3 text-[17px] leading-[26px] text-text-muted">{t("successBody", { name: employeeName })}</p>
      <Button asChild size="lg" className="mt-8 w-full sm:w-auto sm:min-w-56">
        <Link href="/">{t("goHome")}</Link>
      </Button>
    </div>
  );
}

const renderers: Record<OnboardingStepKey, (ctx: Ctx) => Promise<React.ReactNode>> = {
  business: businessStep,
  role: roleStep,
  teach: teachStep,
  voice: voiceStep,
  test_call: testCallStep,
  go_live: goLiveStep,
};

export default async function OnboardingPage({ searchParams }: PageProps<"/onboarding">) {
  const [{ step: requested }, { token }, locale] = await Promise.all([searchParams, requireSession(), getLocale()]);
  const [business, employee, progress] = await Promise.all([getBusiness(), getEmployee(), getProgress()]);

  // A step is reachable once what it builds on exists.
  const reachable: Record<OnboardingStepKey, boolean> = {
    business: true,
    role: Boolean(business),
    teach: Boolean(employee),
    voice: Boolean(employee),
    test_call: Boolean(employee),
    go_live: Boolean(employee),
  };
  const done = Object.fromEntries((progress?.steps ?? []).map((s) => [s.key, s.done])) as Partial<Record<OnboardingStepKey, boolean>>;

  if (employee && (requested === "done" || (requested === undefined && progress?.next === null))) {
    return <DoneScreen employeeName={employee.name} />;
  }

  const fallback: OnboardingStepKey = !business ? "business" : !employee ? "role" : (progress?.next ?? "go_live");
  const step = isStepKey(requested) && reachable[requested] ? requested : reachable[fallback] ? fallback : "business";

  return (
    <>
      <Stepper current={step} done={done} reachable={reachable} />
      {await renderers[step]({ token, business, employee, locale })}
    </>
  );
}
