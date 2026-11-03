import type { Routine } from "./types";

/** Labels for keys that come from data (role ids, outcomes): fall back to the raw value. */
type Loose = { (key: string): string; has(key: string): boolean };

export function label(t: unknown, key: string, fallback: string): string {
  const translate = t as Loose;
  return translate.has(key) ? translate(key) : fallback;
}

/** Ready-made routines keep their name in the viewer's language; owners' own names as typed. */
export function routineName(t: unknown, routine: Pick<Routine, "name" | "name_is_default" | "library_id">): string {
  return routine.name_is_default && routine.library_id
    ? label(t, `library.${routine.library_id}`, routine.name)
    : routine.name;
}
