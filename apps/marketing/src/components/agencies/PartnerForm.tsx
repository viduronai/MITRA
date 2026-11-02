"use client";

import { useId, useState } from "react";
import type { agencies } from "@/content/pages/agencies";
import { normaliseIndianMobile } from "@/lib/phone";
import s from "./agencies.module.css";

type Copy = (typeof agencies)["form"];
type Field = "name" | "agency" | "city" | "phone" | "email" | "clients" | "message";
const REQUIRED: Field[] = ["name", "agency", "city", "phone", "email", "clients"];
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

/**
 * Partner application. TODO(backend): POST to a partner-applications endpoint
 * once it exists; until then the success state says plainly that nothing was sent.
 */
export function PartnerForm({ t }: { t: Copy }) {
  const ids = useId();
  const [values, setValues] = useState<Record<Field, string>>({
    name: "",
    agency: "",
    city: "",
    phone: "",
    email: "",
    clients: "",
    message: "",
  });
  const [consent, setConsent] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [done, setDone] = useState(false);

  const errorFor = (f: Field): string | null => {
    const v = values[f].trim();
    if (REQUIRED.includes(f) && !v) return t.errors.required;
    if (f === "phone" && v && !normaliseIndianMobile(v)) return t.errors.phone;
    if (f === "email" && v && !EMAIL.test(v)) return t.errors.email;
    return null;
  };
  const errors = Object.fromEntries((Object.keys(values) as Field[]).map((f) => [f, errorFor(f)])) as Record<
    Field,
    string | null
  >;
  const consentError = consent ? null : t.errors.consent;

  const onSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setSubmitted(true);
    const firstBad = REQUIRED.concat("message").find((f) => errors[f]);
    if (firstBad || consentError) {
      const target = firstBad ? `${ids}-${firstBad}` : `${ids}-consent`;
      document.getElementById(target)?.focus();
      return;
    }
    setDone(true);
  };

  if (done) {
    return (
      <div className={s.done} role="status" aria-live="polite">
        <p className={s.doneTitle}>{t.successTitle.replace("{name}", values.name.trim().split(" ")[0])}</p>
        <p className={s.doneBody}>{t.successBody}</p>
        <p className={s.previewNote}>{t.previewNote}</p>
        <button type="button" className={s.linkBtn} onClick={() => setDone(false)}>
          {t.again}
        </button>
      </div>
    );
  }

  const field = (f: Field, type = "text", extra: React.InputHTMLAttributes<HTMLInputElement> = {}) => {
    const err = submitted ? errors[f] : null;
    return (
      <div className={s.field} data-invalid={err ? "" : undefined}>
        <label htmlFor={`${ids}-${f}`} className={s.fieldLabel}>
          {t.fields[f]}
        </label>
        <input
          id={`${ids}-${f}`}
          className={s.input}
          type={type}
          value={values[f]}
          onChange={(e) => setValues((v) => ({ ...v, [f]: e.target.value }))}
          aria-invalid={Boolean(err)}
          aria-describedby={err ? `${ids}-${f}-err` : undefined}
          required={REQUIRED.includes(f)}
          {...extra}
        />
        {err && (
          <p id={`${ids}-${f}-err`} className={s.err}>
            {err}
          </p>
        )}
      </div>
    );
  };

  const clientsErr = submitted ? errors.clients : null;

  return (
    <form className={s.form} noValidate onSubmit={onSubmit}>
      <div className={s.row}>
        {field("name", "text", { autoComplete: "name", maxLength: 80 })}
        {field("agency", "text", { autoComplete: "organization", maxLength: 80 })}
      </div>
      <div className={s.row}>
        {field("city", "text", { autoComplete: "address-level2", maxLength: 60 })}
        {field("phone", "tel", { autoComplete: "tel-national", inputMode: "tel", maxLength: 16 })}
      </div>
      {field("email", "email", { autoComplete: "email", maxLength: 120 })}
      <fieldset className={s.field} data-invalid={clientsErr ? "" : undefined}>
        <legend className={s.fieldLabel}>{t.fields.clients}</legend>
        <div className={s.pills}>
          {t.clientOptions.map((o, i) => (
            <label key={o} className={s.pill}>
              <input
                id={i === 0 ? `${ids}-clients` : undefined}
                type="radio"
                name="clients"
                value={o}
                checked={values.clients === o}
                onChange={() => setValues((v) => ({ ...v, clients: o }))}
                aria-describedby={clientsErr ? `${ids}-clients-err` : undefined}
              />
              <span>{o}</span>
            </label>
          ))}
        </div>
        {clientsErr && (
          <p id={`${ids}-clients-err`} className={s.err}>
            {clientsErr}
          </p>
        )}
      </fieldset>
      <div className={s.field}>
        <label htmlFor={`${ids}-message`} className={s.fieldLabel}>
          {t.fields.message}
        </label>
        <textarea
          id={`${ids}-message`}
          className={s.input}
          rows={3}
          maxLength={800}
          value={values.message}
          onChange={(e) => setValues((v) => ({ ...v, message: e.target.value }))}
        />
      </div>
      <div className={s.check} data-invalid={submitted && consentError ? "" : undefined}>
        <input
          id={`${ids}-consent`}
          type="checkbox"
          checked={consent}
          onChange={(e) => setConsent(e.target.checked)}
          aria-invalid={Boolean(submitted && consentError)}
          aria-describedby={submitted && consentError ? `${ids}-consent-err` : undefined}
        />
        <label htmlFor={`${ids}-consent`}>{t.consent}</label>
      </div>
      {submitted && consentError && (
        <p id={`${ids}-consent-err`} className={s.err}>
          {consentError}
        </p>
      )}
      <button type="submit" className="btn btn-blue btn-chamfer">
        {t.submit}
        <span className="trail" aria-hidden="true" />
      </button>
    </form>
  );
}
