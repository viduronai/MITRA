"use client";

import { Plus, Trash2, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useState, useTransition } from "react";
import { toast } from "sonner";
import {
  createWebhook,
  deleteWebhook,
  retryDelivery,
  rotateWebhookSecret,
  sendWebhookTest,
  setWebhookEnabled,
  type LeadResult,
} from "@/app/(app)/more/connect/lead-actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { WEBHOOK_EVENTS, type Webhook, type WebhookDelivery, type WebhookEvent } from "@/lib/leads/types";
import { cn } from "@/lib/utils";
import { CopyBlock } from "./copy-block";

function when(iso: string | null): string {
  if (!iso) return "";
  return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" }).format(new Date(iso));
}

function useAction() {
  const t = useTranslations("leads");
  const [pending, startTransition] = useTransition();
  const act = <T,>(action: () => Promise<LeadResult<T>>, onOk?: (data: T) => void) =>
    startTransition(async () => {
      const res = await action();
      if (!res.ok) {
        toast.error(res.message ?? t(`errors.${res.error}`));
        return;
      }
      onOk?.(res.data);
    });
  return { pending, act };
}

function AddWebhook({ onSecret }: { onSecret: (id: string, secret: string) => void }) {
  const t = useTranslations("webhooks");
  const ids = useId();
  const { pending, act } = useAction();
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [events, setEvents] = useState<WebhookEvent[]>(["call.ended", "lead.created"]);
  const [headers, setHeaders] = useState<{ name: string; value: string }[]>([]);

  const submit = () =>
    act(
      () => createWebhook(url, events, name, Object.fromEntries(headers.filter((h) => h.name.trim()).map((h) => [h.name.trim(), h.value]))),
      (hook) => {
        if (hook.secret) onSecret(hook.id, hook.secret);
        toast.success(t("created"));
        setUrl("");
        setName("");
        setHeaders([]);
      },
    );

  return (
    <section aria-labelledby={`${ids}-title`} className="rounded-xl border bg-card p-5 shadow-xs md:p-6">
      <h2 id={`${ids}-title`} className="text-lg font-semibold">
        {t("addTitle")}
      </h2>
      <div className="mt-4 flex flex-col gap-4">
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${ids}-url`}>{t("url")}</Label>
          <Input id={`${ids}-url`} type="url" inputMode="url" placeholder="https://" value={url} onChange={(e) => setUrl(e.target.value)} />
        </div>
        <fieldset>
          <legend className="mb-2 text-sm leading-5 font-medium">{t("events")}</legend>
          <div className="flex flex-col gap-2">
            {WEBHOOK_EVENTS.map((ev) => (
              <label key={ev} className="flex min-h-11 items-center gap-3">
                <input
                  type="checkbox"
                  className="size-5 accent-[var(--color-primary)]"
                  checked={events.includes(ev)}
                  onChange={(e) => setEvents(e.target.checked ? [...events, ev] : events.filter((x) => x !== ev))}
                />
                {t(`eventNames.${ev.replace(".", "_")}` as never)}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${ids}-name`}>{t("name")}</Label>
          <Input id={`${ids}-name`} maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="flex flex-col gap-2">
          <p className="text-sm leading-5 font-medium">{t("headers")}</p>
          {headers.map((h, i) => (
            <div key={i} className="flex gap-2">
              <Input aria-label={t("headerName")} placeholder={t("headerName")} value={h.name} onChange={(e) => setHeaders(headers.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
              <Input aria-label={t("headerValue")} placeholder={t("headerValue")} value={h.value} onChange={(e) => setHeaders(headers.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))} />
              <Button variant="ghost" size="icon" aria-label={t("removeHeader")} onClick={() => setHeaders(headers.filter((_, j) => j !== i))}>
                <X aria-hidden />
              </Button>
            </div>
          ))}
          {headers.length < 10 && (
            <Button variant="secondary" size="sm" className="w-fit" onClick={() => setHeaders([...headers, { name: "", value: "" }])}>
              <Plus aria-hidden />
              {t("addHeader")}
            </Button>
          )}
        </div>
        <Button className="w-full sm:w-fit" disabled={pending || !url.trim() || events.length === 0} aria-busy={pending} onClick={submit}>
          {t("add")}
        </Button>
      </div>
    </section>
  );
}

function DeliveryRow({ d }: { d: WebhookDelivery }) {
  const t = useTranslations("webhooks");
  const { pending, act } = useAction();
  return (
    <li className="flex flex-col gap-1 py-3 sm:flex-row sm:items-center sm:gap-4">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">
          <span className={cn(d.status === "succeeded" ? "text-success-fg" : d.status === "failed" ? "text-danger-fg" : "text-warning-fg")}>
            {t(`deliveryStatus.${d.status}`)}
          </span>{" "}
          · <span className="font-mono">{d.event}</span>
          {d.response_status !== null && ` · HTTP ${d.response_status}`}
        </p>
        <p className="text-xs leading-5 text-text-muted">
          {when(d.created_at)} · {t("attempts", { count: d.attempts })}
          {d.next_attempt_at && ` · ${t("nextTry", { time: when(d.next_attempt_at) })}`}
          {d.error && ` · ${d.error}`}
        </p>
      </div>
      {d.status !== "succeeded" && (
        <Button variant="secondary" size="xs" disabled={pending} onClick={() => act(() => retryDelivery(d.id))}>
          {t("retry")}
        </Button>
      )}
    </li>
  );
}

function WebhookCard({ hook, deliveries, secret, onSecret }: { hook: Webhook; deliveries: WebhookDelivery[]; secret: string | null; onSecret: (id: string, s: string) => void }) {
  const t = useTranslations("webhooks");
  const { pending, act } = useAction();

  return (
    <li className="rounded-xl border bg-card p-5 shadow-xs">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="font-semibold break-all">{hook.description || hook.url}</p>
          {hook.description && <p className="text-sm break-all text-text-muted">{hook.url}</p>}
          <p className="mt-1 text-sm text-text-muted">{hook.events.map((e) => t(`eventNames.${e.replace(".", "_")}` as never)).join(" · ")}</p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={hook.enabled}
          aria-label={t("toggle", { url: hook.url })}
          disabled={pending}
          onClick={() => act(() => setWebhookEnabled(hook.id, !hook.enabled))}
          className={cn("focus-ring relative inline-flex h-7 w-12 shrink-0 items-center rounded-full transition-colors motion-fast disabled:opacity-60", hook.enabled ? "bg-primary" : "bg-border")}
        >
          <span className={cn("inline-block size-5 rounded-full bg-white shadow-xs transition-transform motion-fast", hook.enabled ? "translate-x-6" : "translate-x-1")} />
        </button>
      </div>
      {hook.consecutive_failures >= 3 && (
        <p role="status" className="mt-3 rounded-lg bg-danger/10 px-3 py-2 text-sm leading-5 font-medium text-danger-fg">
          {t("failing", { count: hook.consecutive_failures })}
        </p>
      )}
      {secret ? (
        <CopyBlock className="mt-3" label={t("secret")} value={secret} />
      ) : (
        <p className="mt-3 text-sm text-text-muted">
          {t("secret")}: <span className="font-mono">{hook.secret_hint}…</span>
        </p>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          variant="secondary"
          size="sm"
          disabled={pending}
          onClick={() =>
            act(
              () => sendWebhookTest(hook.id),
              (d) => (d.status === "succeeded" ? toast.success(t("testOk", { status: d.response_status ?? "" })) : toast.error(t("testFailed", { error: d.error ?? "" }))),
            )
          }
        >
          {t("test")}
        </Button>
        <Button variant="secondary" size="sm" disabled={pending} onClick={() => act(() => rotateWebhookSecret(hook.id), (h) => h.secret && onSecret(h.id, h.secret))}>
          {t("rotate")}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          disabled={pending}
          onClick={() => {
            if (window.confirm(t("deleteConfirm"))) act(() => deleteWebhook(hook.id));
          }}
        >
          <Trash2 aria-hidden />
          {t("delete")}
        </Button>
      </div>
      <h3 className="mt-4 text-sm font-semibold">{t("log")}</h3>
      {deliveries.length === 0 ? (
        <p className="text-sm text-text-muted">{t("logEmpty")}</p>
      ) : (
        <ul className="divide-y">
          {deliveries.map((d) => (
            <DeliveryRow key={d.id} d={d} />
          ))}
        </ul>
      )}
    </li>
  );
}

/** Webhooks settings (INT-13): endpoints, one-time signing secrets, test event, delivery log. */
export function WebhooksManager({ hooks, deliveries }: { hooks: Webhook[]; deliveries: Record<string, WebhookDelivery[]> }) {
  const t = useTranslations("webhooks");
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const remember = (id: string, secret: string) => setSecrets((s) => ({ ...s, [id]: secret }));

  return (
    <div className="flex flex-col gap-4">
      {hooks.length === 0 ? (
        <p className="rounded-xl border border-dashed px-5 py-6 text-center text-text-muted">{t("empty")}</p>
      ) : (
        <ul className="flex flex-col gap-4">
          {hooks.map((hook) => (
            <WebhookCard key={hook.id} hook={hook} deliveries={deliveries[hook.id] ?? []} secret={secrets[hook.id] ?? null} onSecret={remember} />
          ))}
        </ul>
      )}
      <p className="text-sm leading-5 text-text-muted">{t.raw("signatureHelp")}</p>
      <AddWebhook onSecret={remember} />
    </div>
  );
}
