"use client";

import { useEffect, useRef, useState } from "react";
import { content, type Copy, type ChatMessage } from "@/content";
import { useReducedMotion } from "@/lib/useReducedMotion";
import { MitraMark } from "./Wordmark";
import c from "./chat.module.css";
import s from "./whatsapp.module.css";

// Scroll progress at which each message lands.
const AT = [0.04, 0.2, 0.33, 0.43, 0.6, 0.74];
const STEP_OF = [0, 1, 1, 1, 2, 2];
const TIMES = ["8:02 PM", "8:02 PM", "8:03 PM", "8:03 PM", "8:05 PM", "8:05 PM"];
/** Phone pose for scroll progress p: drifts up, turns from -14° to 10°, tips 8° → 3° → 6°. */
function pose(p: number) {
  const rx = p < 0.5 ? 8 - 10 * p : 3 + 6 * (p - 0.5);
  return `translateY(${24 - 48 * p}px) rotateX(${rx}deg) rotateY(${-14 + 24 * p}deg)`;
}

const WAVE = [6, 10, 14, 9, 16, 12, 7, 13, 18, 11, 8, 14, 10, 6, 12, 16, 9, 6, 11, 7];

function Bubble({ msg, time, pressed }: { msg: ChatMessage; time: string; pressed?: string }) {
  if (msg.kind === "owner") {
    return (
      <div className={c.msg} data-side="out">
        {msg.text}
        <span className={c.time}>{time} ✓✓</span>
      </div>
    );
  }
  if (msg.kind === "voice") {
    return (
      <div className={c.msg} data-side="out">
        <div className={c.voice}>
          <svg className={c.playBtn} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M8 5.5v13a1 1 0 0 0 1.5.86l11-6.5a1 1 0 0 0 0-1.72l-11-6.5A1 1 0 0 0 8 5.5Z" />
          </svg>
          <span className={c.wave} aria-hidden="true">
            {WAVE.map((h, i) => (
              <i key={i} style={{ height: `${h}px` }} />
            ))}
          </span>
          <span className={c.time}>{msg.seconds}</span>
        </div>
        <p className={c.vtext}>“{msg.transcript}”</p>
        <span className={c.time}>{time} ✓✓</span>
      </div>
    );
  }
  if (msg.kind === "report") {
    return (
      <div className={c.msg}>
        <p className={c.msgTitle}>{msg.title}</p>
        <dl className={c.rows}>
          {msg.rows.map(([k, v]) => (
            <div key={k} className={c.row}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
        <p className={c.note}>{msg.note}</p>
        <span className={c.time}>{time}</span>
        <div className={c.actions}>
          {msg.actions.map((a) => (
            <span key={a} className={c.action}>
              {a}
            </span>
          ))}
        </div>
      </div>
    );
  }
  return (
    <div className={c.msg}>
      {msg.text}
      <span className={c.time}>{time}</span>
      {msg.actions && (
        <div className={c.actions}>
          {msg.actions.map((a) => (
            <span key={a} className={c.action} data-pressed={pressed === a ? "" : undefined}>
              {a}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function WhatsApp({ copy = content.en }: { copy?: Copy }) {
  const { whatsapp } = copy;
  const messages = whatsapp.messages;
  const ref = useRef<HTMLElement>(null);
  const [scrolled, setScrolled] = useState(1);
  const [typingNow, setTyping] = useState(false);
  const reduced = useReducedMotion();
  // Reduced motion: the whole conversation is visible, nothing is pinned.
  const count = reduced ? messages.length : scrolled;
  const typing = !reduced && typingNow;

  const phoneRef = useRef<HTMLDivElement>(null);
  const barRef = useRef<HTMLSpanElement>(null);

  // Scroll-linked story via motion's scroll(). The library is imported after
  // load + idle so it never weighs on the hero's first paint.
  useEffect(() => {
    const section = ref.current;
    if (reduced || !section) return;
    let cancel: VoidFunction | undefined;
    let idle = 0;
    let disposed = false;
    const onProgress = (p: number) => {
      const n = Math.max(1, AT.filter((at) => p >= at).length);
      setScrolled(n);
      const next = messages[n];
      setTyping(Boolean(next && (next.kind === "bot" || next.kind === "report") && p > AT[n] - 0.07));
      if (phoneRef.current) phoneRef.current.style.transform = pose(p);
      if (barRef.current) barRef.current.style.transform = `scaleX(${Math.min(1, p / 0.95)})`;
    };
    const start = () => {
      import("motion").then(({ scroll }) => {
        if (!disposed) cancel = scroll(onProgress, { target: section, offset: ["start start", "end end"] });
      });
    };
    const schedule = () => {
      if (typeof window.requestIdleCallback === "function") idle = window.requestIdleCallback(start, { timeout: 2000 });
      else start();
    };
    if (document.readyState === "complete") schedule();
    else window.addEventListener("load", schedule, { once: true });
    return () => {
      disposed = true;
      cancel?.();
      window.removeEventListener("load", schedule);
      if (idle) window.cancelIdleCallback(idle);
    };
  }, [reduced, messages]);

  const step = reduced ? -1 : STEP_OF[Math.max(0, count - 1)];
  const approved = count >= 3 ? "Approve" : undefined;

  return (
    <section
      id="whatsapp"
      ref={ref}
      className={`${s.wa} on-chalk offscreen`}
      style={{ "--cis": "340vh" } as React.CSSProperties}
      aria-labelledby="wa-title"
    >
      <div className={s.sticky}>
        <div className={s.copy} data-reveal>
          <p className={`${s.eyebrow} mono-label fade-in`}>{whatsapp.eyebrow}</p>
          <h2 id="wa-title" className={s.title}>
            <span className="mask">
              <span className="mask-in">{whatsapp.title[0]} </span>
            </span>
            <span className="mask">
              <span className="mask-in" style={{ "--i": 1 } as React.CSSProperties}>
                <em className="accent">{whatsapp.title[1]}</em>
              </span>
            </span>
          </h2>
          <ol className={s.steps}>
            {whatsapp.steps.map((st, i) => (
              <li key={st.title} className={s.step} data-active={reduced || step === i ? "" : undefined}>
                <span className={s.stepNo}>{String(i + 1).padStart(2, "0")}</span>
                <h3 className={s.stepTitle}>{st.title}</h3>
                <p className={s.stepBody}>{st.body}</p>
                {i === whatsapp.steps.length - 1 && <span ref={barRef} className={s.bar} aria-hidden="true" />}
              </li>
            ))}
          </ol>
        </div>

        <div className={s.phoneCol}>
          <div ref={phoneRef} className={s.phone} style={reduced ? undefined : { transform: pose(0) }}>
            <div className={s.screen} role="img" aria-label={whatsapp.screenLabel}>
              <span className={s.island} aria-hidden="true" />
              <div className={s.chatHead} aria-hidden="true">
                <svg className={s.back} viewBox="0 0 9 14" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M7.5 1.5 2 7l5.5 5.5" />
                </svg>
                <MitraMark className={s.avatar} />
                <span className={s.contact}>
                  <b>{whatsapp.contact}</b>
                  <span>{typing ? whatsapp.typing : whatsapp.contactStatus}</span>
                </span>
              </div>
              <div className={s.chat} aria-hidden="true">
                <span className={s.day}>{whatsapp.today}</span>
                {messages.slice(0, count).map((m, i) => (
                  <Bubble key={i} msg={m} time={TIMES[i]} pressed={i === 1 ? approved : undefined} />
                ))}
                {typing && (
                  <span className={c.typing}>
                    <i />
                    <i />
                    <i />
                  </span>
                )}
              </div>
              <div className={s.composer} aria-hidden="true">
                <span className={s.field}>{whatsapp.inputPlaceholder}</span>
                <span className={s.mic}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                    <rect x="9" y="3" width="6" height="11" rx="3" />
                    <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
                  </svg>
                </span>
              </div>
            </div>
          </div>
          <div className={s.shadow} aria-hidden="true" />
        </div>
      </div>
    </section>
  );
}
