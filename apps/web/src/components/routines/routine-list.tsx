"use client";

import { Play, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useTransition } from "react";
import { toast } from "sonner";
import { addFromLibrary, deleteRoutine, runRoutineNow, setRoutineEnabled } from "@/app/(app)/routines/actions";
import { Button } from "@/components/ui/button";
import type { LibraryRoutine, Routine } from "@/lib/team/types";
import { useSentence } from "./routine-builder";
import { label } from "@/lib/team/i18n";

export function RoutineList({ routines, employees }: { routines: Routine[]; employees: Record<string, string> }) {
  const t = useTranslations("routines");
  const sentence = useSentence();
  const [pending, start] = useTransition();
  const act = (fn: () => Promise<{ ok: boolean }>, success?: string) =>
    start(async () => {
      const res = await fn();
      if (!res.ok) toast.error(t("error"));
      else if (success) toast.success(success);
    });

  if (routines.length === 0) return <p className="text-text-muted">{t("empty")}</p>;
  return (
    <ul className="flex flex-col gap-3">
      {routines.map((r) => (
        <li key={r.id} className="flex flex-col gap-3 rounded-xl border bg-card p-4 shadow-xs sm:flex-row sm:items-center">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              role="switch"
              className="size-5 accent-brand-600"
              checked={r.enabled}
              disabled={pending}
              aria-label={t("onOff", { name: r.name })}
              onChange={(e) => act(() => setRoutineEnabled(r.id, e.target.checked))}
            />
          </label>
          <div className="min-w-0 flex-1">
            <Link href={`/routines/${r.id}`} className="font-semibold hover:underline">
              {r.name}
            </Link>
            <p className="text-sm text-text-muted">{sentence(r.spec, employees[r.spec.action.employee_id] ?? "—")}</p>
          </div>
          <div className="flex gap-1">
            {r.spec.trigger.type === "schedule" && (
              <Button variant="secondary" size="sm" disabled={pending} onClick={() => act(() => runRoutineNow(r.id), t("ran"))}>
                <Play aria-hidden />
                {t("runNow")}
              </Button>
            )}
            <Button variant="ghost" size="icon" disabled={pending} aria-label={t("delete")} onClick={() => act(() => deleteRoutine(r.id))}>
              <Trash2 aria-hidden />
            </Button>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function RoutineLibrary({ items, existing }: { items: LibraryRoutine[]; existing: string[] }) {
  const t = useTranslations("routines");
  const [pending, start] = useTransition();
  const have = new Set(existing);
  const left = items.filter((i) => !have.has(i.id));
  if (left.length === 0) return null;
  return (
    <section aria-labelledby="library-title">
      <h2 id="library-title" className="mb-3 text-lg font-semibold">
        {t("libraryTitle")}
      </h2>
      <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {left.map((item) => (
          <li key={item.id} className="flex items-center gap-3 rounded-xl border border-dashed p-4">
            <p className="flex-1">{label(t, `library.${item.id}`, item.name)}</p>
            <Button
              variant="secondary"
              size="sm"
              disabled={pending || !item.employee_id}
              onClick={() =>
                start(async () => {
                  const res = await addFromLibrary(item.id);
                  if (res.ok) toast.success(t("added"));
                  else toast.error(t("error"));
                })
              }
            >
              <Plus aria-hidden />
              {t("add")}
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}
