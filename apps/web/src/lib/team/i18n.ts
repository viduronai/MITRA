/** Labels for keys that come from data (role ids, outcomes): fall back to the raw value. */
type Loose = { (key: string): string; has(key: string): boolean };

export function label(t: unknown, key: string, fallback: string): string {
  const translate = t as Loose;
  return translate.has(key) ? translate(key) : fallback;
}
