import { formatLocales, isLocale } from "@/i18n/config";
import type { BonusSlab } from "./types";

/** Pure money helpers shared by server and client components. Amounts are integer paise. */

export const PRESET_TOPUPS_RUPEES = [500, 2_000, 10_000, 25_000] as const;

export function bonusPct(amountPaise: number, slabs: BonusSlab[]): number {
  return slabs.reduce((pct, slab) => (amountPaise >= slab.min_paise ? Math.max(pct, slab.pct) : pct), 0);
}

/** Mirrors services/core billing/rating.py: bonus = amount × pct / 100 (floored), GST 18% half-up. */
export function topupPreview(amountPaise: number, slabs: BonusSlab[], gstRatePct: number) {
  const pct = bonusPct(amountPaise, slabs);
  const bonus = Math.floor((amountPaise * pct) / 100);
  const gst = Math.floor((2 * amountPaise * gstRatePct + 100) / 200);
  return { pct, bonus, gst, total: amountPaise + gst, credits: amountPaise + bonus };
}

/** The next slab above `amountPaise`, to nudge "Add ₹X more for +5%". */
export function nextSlab(amountPaise: number, slabs: BonusSlab[]): BonusSlab | null {
  return [...slabs].sort((a, b) => a.min_paise - b.min_paise).find((s) => s.min_paise > amountPaise) ?? null;
}

export function paiseToRupees(paise: number): number {
  return paise / 100;
}

/** Talk-time "1h 05m" / "12m 30s" from seconds. */
export function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m`;
  return `${m}m ${String(s).padStart(2, "0")}s`;
}

/** ₹ from paise; whole rupees unless `exact` and the amount has paise ("₹0.75"). */
export function formatPaise(paise: number, locale: string, { exact = false }: { exact?: boolean } = {}): string {
  const fraction = exact && paise % 100 !== 0 ? 2 : 0;
  return new Intl.NumberFormat(isLocale(locale) ? formatLocales[locale] : "en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: fraction,
    maximumFractionDigits: fraction,
  }).format(paise / 100);
}
