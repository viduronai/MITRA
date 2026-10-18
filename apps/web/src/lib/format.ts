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

/**
 * "6:15 pm" in every locale. ICU writes "AM"/"PM" for te-IN and other casings
 * elsewhere, so the clock is built from parts with one lowercase style.
 */
export function formatTime(date: Date, locale: string): string {
  const parts = new Intl.DateTimeFormat("en-IN", {
    hour: "numeric",
    minute: "2-digit",
    hourCycle: "h12",
    timeZone: TIME_ZONE,
  }).formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes) => Number(parts.find((p) => p.type === type)?.value ?? 0);
  const digits = new Intl.NumberFormat(tag(locale), { minimumIntegerDigits: 2 });
  const period = hourInIndia(date) < 12 ? "am" : "pm";
  return `${part("hour")}:${digits.format(part("minute"))} ${period}`;
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

/** Per-minute rates keep one decimal: "₹4.5". */
export function formatRate(amount: number, locale: string): string {
  return new Intl.NumberFormat(tag(locale), {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  }).format(amount);
}

/** ["Telugu", "English"] → "Telugu and English" in the UI language. */
export function formatList(items: string[], locale: string): string {
  return new Intl.ListFormat(tag(locale), { style: "long", type: "conjunction" }).format(items);
}
