"use client";

import { useEffect, useId, useRef, useState } from "react";
import { copy } from "@/content";
import s from "./demo.module.css";
import ss from "./demo-success.module.css";

type LanguageId = (typeof copy.demo.languages)[number]["id"];
type IndustryId = (typeof copy.demo.industries)[number]["id"];

/** Accepts 10 digits starting 6–9, optionally prefixed with +91, 91 or 0. */
export function normaliseIndianMobile(raw: string): string | null {
  let digits = raw.replace(/\D/g, "");
  if (digits.length === 12 && digits.startsWith("91")) digits = digits.slice(2);
  else if (digits.length === 11 && digits.startsWith("0")) digits = digits.slice(1);
  return /^[6-9]\d{9}$/.test(digits) ? digits : null;
}

export function DemoForm() {
  const { demo } = copy;
  const ids = useId();
  const [phone, setPhone] = useState("");
  const [touched, setTouched] = useState(false);
  const [language, setLanguage] = useState<LanguageId>("te");
  const [industry, setIndustry] = useState<IndustryId>("clinic");
  const [sent, setSent] = useState(false);
  const [stage, setStage] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);

  const valid = normaliseIndianMobile(phone) !== null;
  const showError = touched && !valid;

  // Simulated progress until the real call status arrives.
  useEffect(() => {
    if (!sent) return;
    titleRef.current?.focus();
    const t1 = setTimeout(() => setStage(1), 1400);
    const t2 = setTimeout(() => setStage(2), 6000);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [sent]);

  const onSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setTouched(true);
    const number = normaliseIndianMobile(phone);
    if (!number) {
      inputRef.current?.focus();
      return;
    }
    // TODO(backend): POST /v1/demo-calls { phone: `+91${number}`, language, industry }
    // and stream the call status (dialling → connected → ended) into `stage`.
    void { number, language, industry };
    setStage(0);
    setSent(true);
  };

  const reset = () => {
    setSent(false);
    setPhone("");
    setTouched(false);
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
    <form className={s.form} noValidate onSubmit={onSubmit} action="#" method="post">
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
          onChange={(e) => setPhone(e.target.value.replace(/[^\d\s+-]/g, ""))}
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

      <div className={s.buttons}>
        <a href="#hear" className={s.ghost}>
          {demo.ghost}
        </a>
        <button type="submit" className={s.solid}>
          {demo.submit}
        </button>
      </div>
      <p className={s.consent}>{demo.consent}</p>
    </form>
  );
}
