import { CalendarDays, Cable, FlaskConical, Hash, MessageCircle, PhoneForwarded, Plug, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { LeadsSection } from "@/components/leads/leads-section";
import { PageHeader } from "@/components/shell/page-header";
import { ForwardingCodes } from "@/components/telephony/forwarding-codes";
import { RequestNumberForm } from "@/components/telephony/request-number";
import { TrustedCallerCard } from "@/components/telephony/trusted-caller-card";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { getBusiness } from "@/lib/data";
import { requireSession } from "@/lib/session";
import { liveForwarding, telephonyApi } from "@/lib/telephony/api";
import { cn } from "@/lib/utils";

export async function generateMetadata() {
  const t = await getTranslations("connect");
  return { title: t("title") };
}

function Section({
  id,
  icon: Icon,
  title,
  description,
  children,
  className,
}: {
  id: string;
  icon: LucideIcon;
  title: string;
  description: string;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <section aria-labelledby={id} className={cn("rounded-xl border bg-card p-5 shadow-xs md:p-6", className)}>
      <div className="flex items-start gap-4">
        <span aria-hidden className="inline-flex size-11 shrink-0 items-center justify-center rounded-full bg-brand-50 text-brand-700">
          <Icon className="size-5" strokeWidth={1.75} />
        </span>
        <div className="min-w-0 flex-1">
          <h2 id={id} className="text-lg leading-[26px] font-semibold md:text-xl">
            {title}
          </h2>
          <p className="mt-0.5 text-text-muted">{description}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

export default async function ConnectPage() {
  const { token } = await requireSession();
  const [t, tLeads, business] = await Promise.all([getTranslations("connect"), getTranslations("leads"), getBusiness()]);

  let numbers;
  try {
    numbers = await telephonyApi.list(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login?expired=1");
    return (
      <>
        <PageHeader title={t("title")} />
        <p role="alert" className="rounded-xl border border-dashed px-5 py-8 text-center text-text-muted">
          {t("loadError")}
        </p>
      </>
    );
  }
  const forwarding = await liveForwarding(token, numbers.items);
  const live = numbers.items.find((n) => n.id === forwarding?.phone_number_id) ?? null;
  const support = process.env.MITRA_SUPPORT_EMAIL;
  const soon: { key: "calendar" | "whatsapp"; icon: LucideIcon }[] = [
    { key: "calendar", icon: CalendarDays },
    { key: "whatsapp", icon: MessageCircle },
  ];

  return (
    <>
      <PageHeader title={t("title")} />
      <p className="-mt-2 mb-5 text-text-muted">{t("subtitle")}</p>
      <div className="flex flex-col gap-4">
        <Section id="numbers" icon={Hash} title={t("numbersTitle")} description={t("numbersDesc")}>
          {numbers.simulated && (
            <p className="mt-4 flex items-start gap-2 rounded-lg bg-sky-100 px-4 py-3 text-sm leading-5 text-sky-ink">
              <FlaskConical aria-hidden className="mt-0.5 size-4 shrink-0" />
              {t("simulated")}
            </p>
          )}
          <div className="mt-4 flex flex-col gap-4">
            {numbers.items.map((n) => (
              <TrustedCallerCard key={n.id} number={n} businessName={numbers.business_name} />
            ))}
          </div>
          {numbers.items.length === 0 && (
            <>
              <h3 className="mt-5 font-medium">{t("requestTitle")}</h3>
              <p className="text-sm leading-5 text-text-muted">{t("requestDesc")}</p>
              <RequestNumberForm defaultCity={business?.city ?? ""} />
            </>
          )}
        </Section>

        <Section
          id="forwarding"
          icon={PhoneForwarded}
          title={t("forwardTitle")}
          description={t("forwardDesc", { target: forwarding?.target ?? t("yourMitraNumber") })}
        >
          <div className="mt-5">
            <ForwardingCodes codes={forwarding?.operators ?? null} numberId={live?.id ?? null} testedAt={live?.forwarding_tested_at ?? null} />
          </div>
        </Section>

        <Section id="byo" icon={Cable} title={t("byoTitle")} description={t("byoDesc")}>
          <Button asChild variant="secondary" className="mt-4 w-full sm:w-fit">
            {support ? (
              <a href={`mailto:${support}?subject=${encodeURIComponent(t("byoSubject"))}`}>{t("byoCta")}</a>
            ) : (
              <Link href="/more">{t("byoCta")}</Link>
            )}
          </Button>
        </Section>

        <Section id="leads" icon={Plug} title={tLeads("title")} description={tLeads("desc")}>
          <LeadsSection token={token} businessName={numbers.business_name} />
        </Section>

        <div className="grid gap-4 md:grid-cols-2">
          {soon.map(({ key, icon }) => (
            <Section
              key={key}
              id={key}
              icon={icon}
              title={t(`soon.${key}`)}
              description={t("comingSoon")}
              className="border-dashed bg-card/60 shadow-none"
            />
          ))}
        </div>
      </div>
    </>
  );
}
