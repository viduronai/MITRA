import { formatLocales, isLocale, TIME_ZONE } from "@/i18n/config";

// Indian formats (docs/06 §10): ₹1,20,000 · 18 Oct · 6:15 pm.
// Call these from Server Components so server and browser never disagree.

function tag(locale: string): string {
  return isLocale(locale) ? formatLocales[locale] : "en-IN";
}

export function formatRupees(amount: number, locale: string): string {
  return new Intl.NumberFormat(tag(locale), {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(amount);
}

export function formatNumber(value: number, locale: string): string {
  return new Intl.NumberFormat(tag(locale)).format(value);
}

/** "Saturday, 18 Oct" */
export function formatLongDate(date: Date, locale: string): string {
  return new Intl.DateTimeFormat(tag(locale), {
    weekday: "long",
    day: "numeric",
    month: "short",
    timeZone: TIME_ZONE,
  }).format(date);
}

/** "6:15 pm" */
export function formatTime(date: Date, locale: string): string {
  return new Intl.DateTimeFormat(tag(locale), {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
    timeZone: TIME_ZONE,
  }).format(date);
}

/** Hour of day (0–23) in India, used for the greeting. */
export function hourInIndia(date: Date): number {
  const hour = new Intl.DateTimeFormat("en-IN", {
    hour: "numeric",
    hourCycle: "h23",
    timeZone: TIME_ZONE,
  }).format(date);
  return Number.parseInt(hour, 10);
}
