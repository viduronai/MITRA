export const locales = ["en", "te", "hi"] as const;
export type Locale = (typeof locales)[number];

export const defaultLocale: Locale = "en";
export const LOCALE_COOKIE = "MITRA_LOCALE";

/** Labels are always shown in their own script so owners can find them. */
export const localeLabels: Record<Locale, { abbr: string; short: string; name: string }> = {
  en: { abbr: "EN", short: "EN", name: "English" },
  te: { abbr: "తె", short: "తెలుగు", name: "తెలుగు" },
  hi: { abbr: "हि", short: "हिंदी", name: "हिंदी" },
};

/** BCP 47 tags used for Indian number, currency and date formats. */
export const formatLocales: Record<Locale, string> = {
  en: "en-IN",
  te: "te-IN",
  hi: "hi-IN",
};

export const TIME_ZONE = "Asia/Kolkata";

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (locales as readonly string[]).includes(value);
}
