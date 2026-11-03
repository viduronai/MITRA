"use client";

import { Download, Pause, Play, Plus, Settings2, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useId, useState, useTransition } from "react";
import { toast } from "sonner";
import { campaignAction, editCampaign, extendCampaign, type CampaignErrorKey } from "@/app/(app)/campaigns/actions";
import { ConsentCheck } from "@/components/campaigns/consent-check";
import { ListInput } from "@/components/campaigns/list-input";
import { ScheduleFields, type Schedule } from "@/components/campaigns/schedule-fields";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { Campaign } from "@/lib/campaigns/types";

type Action = "start" | "pause" | "resume" | "cancel";

function useErrorToast() {
  const t = useTranslations("campaigns.errors");
  return (error: CampaignErrorKey | "tooBig", message?: string) =>
    toast.error(message && error !== "unavailable" ? `${t(error)} (${message})` : t(error));
}

/** Start / pause / resume / cancel, edit the schedule, add people, export (CALL-15). */
export function CampaignControls({
  campaign,
  canManage,
  consentText,
  language,
}: {
  campaign: Campaign;
  canManage: boolean;
  /** Core's exact attestation words for this campaign's kind of list, in the owner's language. */
  consentText: string;
  language: "en" | "hi" | "te";
}) {
  const t = useTranslations("campaigns.detail");
  const router = useRouter();
  const showError = useErrorToast();
  const [pending, startTransition] = useTransition();
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [editing, setEditing] = useState(false);
  const [extending, setExtending] = useState(false);
  const [confirmStart, setConfirmStart] = useState(false);
  const [attested, setAttested] = useState(false);
  const { status } = campaign;
  const promotional = campaign.purpose === "promotional";
  const open = status !== "completed" && status !== "cancelled";

  const act = (action: Action, tick = false) =>
    startTransition(async () => {
      const consent = tick ? { consent_attested: true, consent_language: language } : undefined;
      const res = await campaignAction(campaign.id, action, consent);
      if (!res.ok) {
        showError(res.error, res.message);
        return;
      }
      toast.success(t(`done.${action}`));
      setConfirmCancel(false);
      setConfirmStart(false);
      router.refresh();
    });

  return (
    <div className="flex flex-wrap gap-2">
      {canManage && status === "draft" && (
        <Button size="sm" disabled={pending} onClick={() => (campaign.consent ? act("start") : setConfirmStart(true))}>
          <Play aria-hidden />
          {t("start")}
        </Button>
      )}
      {canManage && status === "running" && (
        <Button size="sm" variant="secondary" disabled={pending} onClick={() => act("pause")}>
          <Pause aria-hidden />
          {t("pause")}
        </Button>
      )}
      {canManage && status === "paused" && (
        <Button size="sm" disabled={pending} onClick={() => act("resume")}>
          <Play aria-hidden />
          {t("resume")}
        </Button>
      )}
      {canManage && status !== "cancelled" && (
        <Button size="sm" variant="secondary" disabled={pending} onClick={() => setExtending(true)}>
          <Plus aria-hidden />
          {t("addPeople")}
        </Button>
      )}
      {canManage && open && (
        <Button size="sm" variant="secondary" disabled={pending} onClick={() => setEditing(true)}>
          <Settings2 aria-hidden />
          {t("edit")}
        </Button>
      )}
      {canManage && (
        <Button asChild size="sm" variant="ghost">
          <a href={`/campaigns/${campaign.id}/export`} download>
            <Download aria-hidden />
            {t("export")}
          </a>
        </Button>
      )}
      {canManage && open && (
        <Button size="sm" variant="ghost" disabled={pending} onClick={() => setConfirmCancel(true)}>
          <X aria-hidden />
          {t("cancel")}
        </Button>
      )}

      <Dialog open={confirmStart} onOpenChange={setConfirmStart}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("startTitle")}</DialogTitle>
            <DialogDescription>{t("startBody")}</DialogDescription>
          </DialogHeader>
          <ConsentCheck text={consentText} checked={attested} onChange={setAttested} promotional={promotional} />
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="secondary">{t("notNow")}</Button>
            </DialogClose>
            <Button disabled={pending || !attested} onClick={() => act("start", true)}>
              <Play aria-hidden />
              {t("start")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={confirmCancel} onOpenChange={setConfirmCancel}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("cancelTitle")}</DialogTitle>
            <DialogDescription>{t("cancelBody")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="secondary">{t("keep")}</Button>
            </DialogClose>
            <Button variant="danger" disabled={pending} onClick={() => act("cancel")}>
              {t("cancelConfirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Sheet open={editing} onOpenChange={setEditing}>
        <SheetContent className="overflow-y-auto sm:max-w-lg">
          <SheetHeader>
            <SheetTitle>{t("editTitle")}</SheetTitle>
            <SheetDescription>{t("editBody")}</SheetDescription>
          </SheetHeader>
          {editing && <EditForm campaign={campaign} onDone={() => setEditing(false)} />}
        </SheetContent>
      </Sheet>

      <Sheet open={extending} onOpenChange={setExtending}>
        <SheetContent className="overflow-y-auto sm:max-w-lg">
          <SheetHeader>
            <SheetTitle>{t("addTitle")}</SheetTitle>
            <SheetDescription>{t("addBody")}</SheetDescription>
          </SheetHeader>
          {extending && (
            <ExtendForm
              campaignId={campaign.id}
              needsTick={status !== "draft"}
              consentText={consentText}
              promotional={promotional}
              language={language}
              onDone={() => setExtending(false)}
            />
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}

function EditForm({ campaign, onDone }: { campaign: Campaign; onDone: () => void }) {
  const t = useTranslations("campaigns.detail");
  const router = useRouter();
  const showError = useErrorToast();
  const ids = { name: useId(), avg: useId() };
  const [name, setName] = useState(campaign.name);
  const [avg, setAvg] = useState(campaign.avg_call_seconds);
  const [schedule, setSchedule] = useState<Schedule>({
    calling_days: campaign.calling_days,
    holidays: campaign.holidays,
    ends_on: campaign.ends_on,
    retry_ladder: campaign.retry_ladder,
  });
  const [pending, startTransition] = useTransition();

  return (
    <form
      className="flex flex-col gap-5 px-4 pb-6"
      onSubmit={(e) => {
        e.preventDefault();
        startTransition(async () => {
          const res = await editCampaign(campaign.id, {
            name: name.trim() || campaign.name,
            avg_call_seconds: avg,
            ...schedule,
          });
          if (!res.ok) {
        showError(res.error, res.message);
        return;
      }
          toast.success(t("saved"));
          onDone();
          router.refresh();
        });
      }}
    >
      <div className="flex flex-col gap-2">
        <Label htmlFor={ids.name}>{t("name")}</Label>
        <Input id={ids.name} value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor={ids.avg}>{t("avgCall")}</Label>
        <Input
          id={ids.avg}
          type="number"
          min={15}
          max={1800}
          value={avg}
          onChange={(e) => setAvg(Math.min(1800, Math.max(15, Number(e.target.value) || 90)))}
          className="sm:max-w-40"
        />
        <p className="text-[13px] leading-5 text-text-muted">{t("avgCallHint")}</p>
      </div>
      <ScheduleFields value={schedule} onChange={setSchedule} />
      <Button type="submit" disabled={pending} aria-busy={pending}>
        {t("save")}
      </Button>
    </form>
  );
}

function ExtendForm({
  campaignId,
  needsTick,
  consentText,
  promotional,
  language,
  onDone,
}: {
  campaignId: string;
  /** People added to a list that already calls are vouched for again (docs/08 §8.5). */
  needsTick: boolean;
  consentText: string;
  promotional: boolean;
  language: "en" | "hi" | "te";
  onDone: () => void;
}) {
  const t = useTranslations("campaigns.detail");
  const router = useRouter();
  const showError = useErrorToast();
  const [text, setText] = useState("");
  const [attested, setAttested] = useState(false);
  const [pending, startTransition] = useTransition();
  return (
    <form
      className="flex flex-col gap-5 px-4 pb-6"
      onSubmit={(e) => {
        e.preventDefault();
        startTransition(async () => {
          const consent = attested ? { consent_attested: true, consent_language: language } : undefined;
          const res = await extendCampaign(campaignId, { text }, consent);
          if (!res.ok) {
        showError(res.error, res.message);
        return;
      }
          toast.success(t("added", { added: res.data.added, skipped: res.data.skipped }));
          onDone();
          router.refresh();
        });
      }}
    >
      <ListInput value={text} onChange={setText} onTooBig={() => showError("tooBig")} />
      {needsTick && (
        <ConsentCheck text={consentText} checked={attested} onChange={setAttested} promotional={promotional} />
      )}
      <Button type="submit" disabled={pending || !text.trim() || (needsTick && !attested)} aria-busy={pending}>
        <Plus aria-hidden />
        {t("addCta")}
      </Button>
    </form>
  );
}
