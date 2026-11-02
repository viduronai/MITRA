import { BadgeCheck, Phone, PhoneOff } from "lucide-react";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";

/** "What customers see": an incoming-call screen with the name networks/Truecaller show. */
export function CallerPreview({
  name,
  number,
  verified,
  className,
}: {
  name: string;
  number: string | null;
  verified: boolean;
  className?: string;
}) {
  const t = useTranslations("connect");
  const initial = name.trim().charAt(0).toUpperCase() || "M";

  return (
    <figure className={cn("flex flex-col items-center gap-2", className)}>
      <div
        aria-hidden
        className="w-full max-w-[220px] rounded-[28px] border-[6px] border-foreground/85 bg-gradient-to-b from-brand-700 to-brand-600 px-4 pt-6 pb-5 text-on-brand shadow-md"
      >
        <p className="text-center text-[11px] tracking-wide uppercase opacity-80">{t("previewIncoming")}</p>
        <span className="mx-auto mt-3 flex size-14 items-center justify-center rounded-full bg-white/15 text-2xl font-semibold">
          {initial}
        </span>
        <p className="mt-3 flex items-center justify-center gap-1 text-center text-base leading-6 font-semibold">
          <span className="truncate">{name}</span>
          {verified && <BadgeCheck className="size-4 shrink-0 text-sky-100" />}
        </p>
        <p className="text-center font-mono text-xs opacity-85">{number ?? "040 XXXX XXXX"}</p>
        <p
          className={cn(
            "mx-auto mt-2 w-fit rounded-full px-2 py-0.5 text-[11px] font-medium",
            verified ? "bg-success text-white" : "bg-white/15",
          )}
        >
          {verified ? t("previewVerified") : t("previewUnverified")}
        </p>
        <p className="mt-2 text-center text-[11px] opacity-80">{t("previewReason")}</p>
        <div className="mt-5 flex justify-around">
          <span className="flex size-10 items-center justify-center rounded-full bg-danger text-white">
            <PhoneOff className="size-4" />
          </span>
          <span className="flex size-10 items-center justify-center rounded-full bg-success text-white">
            <Phone className="size-4" />
          </span>
        </div>
      </div>
      <figcaption className="text-sm leading-5 text-text-muted">
        {t("previewTitle")}
        <span className="sr-only">
          {": "}
          {name}, {number ?? ""}, {verified ? t("previewVerified") : t("previewUnverified")}
        </span>
      </figcaption>
    </figure>
  );
}
