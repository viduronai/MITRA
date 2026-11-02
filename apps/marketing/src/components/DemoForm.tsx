"use client";

import { useEffect, useId, useRef, useState } from "react";
import { content, type Copy } from "@/content";
import { normaliseIndianMobile } from "@/lib/phone";
import { apiBase } from "@/lib/site";
import s from "./demo.module.css";
import ss from "./demo-success.module.css";

type LanguageId = Copy["demo"]["languages"][number]["id"];
type IndustryId = Copy["demo"]["industries"][number]["id"];
type Failure = "limited" | "network" | null;

const TIMEOUT_MS = 8000;
// The API names industries like the rest of core (real_estate).
const apiIndustry: Record<string, string> = { realestate: "real_estate" };

type Outcome = { ok: true; simulated: boolean } | { ok: false; failure: Exclude<Failure, null> | "invalid" };

/** POST /v1/demo-calls. Any network error, timeout or 5xx is a "network" failure. */
async function requestDemoCall(body: Record<string, unknown>): Promise<Outcome> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${apiBase}/v1/demo-calls`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    if (res.status === 202) {
      const data = (await res.json().catch(() => ({}))) as { simulated?: boolean };
      return { ok: true, simulated: data.simulated !== false };
    }
    if (res.status === 429) return { ok: false, failure: "limited" };
    if (res.status === 422) return { ok: false, failure: "invalid" };
    return { ok: false, failure: "network" };
  } catch {
    return { ok: false, failure: "network" };
  } finally {
    clearTimeout(timer);
  }
}

export function DemoForm({ copy = content.en }: { copy?: Copy }) {
  const { demo } = copy;
  const ids = useId();
  const [phone, setPhone] = useState("");
  const [touched, setTouched] = useState(false);
  const [consent, setConsent] = useState(false);
  const [consentTouched, setConsentTouched] = useState(false);
  const [language, setLanguage] = useState<LanguageId>(copy.locale === "en" ? "te" : copy.locale);
  const [industry, setIndustry] = useState<IndustryId>("clinic");
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<Failure>(null);
  const [serverInvalid, setServerInvalid] = useState(false);
  const [sent, setSent] = useState<{ simulated: boolean } | null>(null);
  const [stage, setStage] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const consentRef = useRef<HTMLInputElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);

  const valid = normaliseIndianMobile(phone) !== null;
  const showError = (touched && !valid) || serverInvalid;
  const showConsentError = consentTouched && !consent;

  // Progress: real status will stream from the dialer; until then a live
  // request walks the steps on a timer and a simulated one stays at step one.
  useEffect(() => {
    if (!sent) return;
    titleRef.current?.focus();
    if (sent.simulated) return;
    const t1 = setTimeout(() => setStage(1), 1400);
    const t2 = setTimeout(() => setStage(2), 6000);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [sent]);

  const onSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (pending) return;
    setTouched(true);
    setConsentTouched(true);
    setFailure(null);
    setServerInvalid(false);
    const number = normaliseIndianMobile(phone);
    if (!number) {
      inputRef.current?.focus();
      return;
    }
    if (!consent) {
      consentRef.current?.focus();
      return;
    }
    setPending(true);
    const outcome = await requestDemoCall({
      phone: `+91${number}`,
      language,
      industry: apiIndustry[industry] ?? industry,
      consent: true,
    });
    setPending(false);
    if (outcome.ok) {
      setStage(0);
      setSent({ simulated: outcome.simulated });
    } else if (outcome.failure === "invalid") {
      setServerInvalid(true);
      inputRef.current?.focus();
    } else {
      setFailure(outcome.failure);
    }
  };

  const reset = () => {
    setSent(null);
    setPhone("");
    setTouched(false);
    setFailure(null);
    requestAnimationFrame(() => inputRef.current?.focus());
  };

  if (sent) {
    return (
      <div className={ss.success} role="status" aria-live="polite">
        <div className={ss.rings} aria-hidden="true">
          <span className={ss.ringCore} />
        </div>
        <h3 ref={titleRef} tabIndex={-1} className={ss.successTitle}>
          {demo.successTitle}
        </h3>
        <p className={ss.successBody}>{demo.successBody}</p>
        {sent.simulated && <p className={ss.preview}>{demo.simulatedNote}</p>}
        <ol className={ss.steps}>
          {demo.successSteps.map((label, i) => (
            <li
              key={label}
              className={ss.step}
              data-state={i < stage + 1 ? (i === stage && i > 0 ? "active" : "done") : "todo"}
            >
              <span className={ss.dot} aria-hidden="true" />
              {label}
            </li>
          ))}
        </ol>
        <button type="button" className={ss.again} onClick={reset}>
          {demo.again}
        </button>
      </div>
    );
  }

  return (
    <form className={s.form} noValidate onSubmit={onSubmit} action="#" method="post" aria-busy={pending}>
      <div className={s.phoneRow} data-invalid={showError ? "" : undefined}>
        <label htmlFor={`${ids}-phone`} className="sr-only">
          {demo.phoneLabel}
        </label>
        <span className={s.prefix} aria-hidden="true">
          {demo.phonePrefix}
        </span>
        <input
          ref={inputRef}
          id={`${ids}-phone`}
          className={s.input}
          type="tel"
          inputMode="tel"
          autoComplete="tel-national"
          placeholder={demo.phonePlaceholder}
          maxLength={16}
          value={phone}
          onChange={(e) => {
            setPhone(e.target.value.replace(/[^\d\s+-]/g, ""));
            setServerInvalid(false);
          }}
          onBlur={() => phone && setTouched(true)}
          aria-invalid={showError}
          aria-describedby={showError ? `${ids}-err` : undefined}
          required
        />
      </div>
      {showError && (
        <p id={`${ids}-err`} className={s.error} role="alert">
          {demo.phoneError}
        </p>
      )}

      <fieldset className={s.group}>
        <legend className={s.legend}>{demo.languageLabel}</legend>
        <div className={s.chips}>
          {demo.languages.map((l) => (
            <label key={l.id} className={s.option}>
              <input
                type="radio"
                name="language"
                value={l.id}
                checked={language === l.id}
                onChange={() => setLanguage(l.id)}
              />
              <span lang={l.lang}>{l.label}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className={s.group}>
        <legend className={s.legend}>{demo.industryLabel}</legend>
        <div className={s.chips}>
          {demo.industries.map((ind) => (
            <label key={ind.id} className={s.option}>
              <input
                type="radio"
                name="industry"
                value={ind.id}
                checked={industry === ind.id}
                onChange={() => setIndustry(ind.id)}
              />
              <span>{ind.label}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className={s.check} data-invalid={showConsentError ? "" : undefined}>
        <input
          ref={consentRef}
          id={`${ids}-consent`}
          type="checkbox"
          checked={consent}
          onChange={(e) => setConsent(e.target.checked)}
          aria-invalid={showConsentError}
          aria-describedby={showConsentError ? `${ids}-consent-err` : undefined}
          required
        />
        <label htmlFor={`${ids}-consent`}>{demo.consentLabel}</label>
      </div>
      {showConsentError && (
        <p id={`${ids}-consent-err`} className={s.error} role="alert">
          {demo.consentError}
        </p>
      )}

      <div className={s.buttons}>
        <a href="#hear" className={s.ghost}>
          {demo.ghost}
        </a>
        <button type="submit" className={s.solid} disabled={pending}>
          {pending ? demo.sending : demo.submit}
        </button>
      </div>
      {failure && (
        <p className={s.failure} role="alert">
          {failure === "limited" ? demo.errorLimited : demo.errorNetwork}
        </p>
      )}
      <p className={s.consent}>{demo.consent}</p>
    </form>
  );
}
