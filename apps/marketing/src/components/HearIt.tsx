"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { content, type Copy, type Scenario } from "@/content";
import { useReducedMotion } from "@/lib/useReducedMotion";
import type { VoiceSignal } from "./VoiceSphere";
import s from "./hear.module.css";

const VoiceSphere = dynamic(() => import("./VoiceSphere"), { ssr: false });

const CHARS_PER_SEC = 24;
const LINE_GAP_MS = 750;
const LEAD_IN_MS = 500;

type Slot = { start: number; end: number };

function timeline(scenario: Scenario) {
  let cursor = LEAD_IN_MS;
  const slots: Slot[] = scenario.lines.map((line) => {
    const start = cursor;
    const end = start + (line.text.length / CHARS_PER_SEC) * 1000;
    cursor = end + LINE_GAP_MS;
    return { start, end };
  });
  return { slots, total: cursor };
}

function seconds(label: string) {
  const [m, sec] = label.split(":").map(Number);
  return m * 60 + sec;
}

const clock = (sec: number) => `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, "0")}`;

/**
 * Simulated voice envelope: syllable-rate bumps on a phrase-rate swell.
 * Replace with an AnalyserNode reading of real audio once samples exist.
 */
function envelope(ms: number) {
  const t = ms / 1000;
  const syll = Math.abs(Math.sin(t * 10.7)) * (0.6 + 0.4 * Math.sin(t * 2.3 + 1.1));
  return Math.min(1, 0.35 + 0.65 * syll * (0.75 + 0.25 * Math.sin(t * 0.9)));
}

export function HearIt({ copy = content.en }: { copy?: Copy }) {
  const { hear } = copy;
  const scenarios = hear.scenarios;
  const [index, setIndex] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [soundOn, setSoundOn] = useState(false);
  const [near, setNear] = useState(false);
  const reduced = useReducedMotion();
  const sectionRef = useRef<HTMLElement>(null);
  const inViewRef = useRef(false);
  const signal = useRef<VoiceSignal>({ amp: 0, who: null });

  const scenario = scenarios[index];
  const { slots, total } = useMemo(() => timeline(scenario), [scenario]);
  // Reduced motion shows the whole transcript at once.
  const at = reduced ? total : elapsed;
  const done = at >= total;

  // Visibility: mount the sphere when near, play while the scene is in view.
  useEffect(() => {
    const el = sectionRef.current;
    if (!el) return;
    const rm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const nearIo = new IntersectionObserver(([e]) => e.isIntersecting && setNear(true), { rootMargin: "100% 0px" });
    const viewIo = new IntersectionObserver(
      ([e]) => {
        inViewRef.current = e.isIntersecting;
        setPlaying(e.isIntersecting && !rm);
      },
      { threshold: 0.35 },
    );
    nearIo.observe(el);
    const stickyEl = el.firstElementChild;
    if (stickyEl) viewIo.observe(stickyEl);
    return () => {
      nearIo.disconnect();
      viewIo.disconnect();
    };
  }, []);

  // Industry cards ask for a scenario via a window event.
  useEffect(() => {
    const onPick = (e: Event) => {
      const id = (e as CustomEvent<string>).detail;
      const i = scenarios.findIndex((sc) => sc.id === id);
      if (i >= 0) {
        setIndex(i);
        setElapsed(0);
      }
    };
    window.addEventListener("mitra:play-scenario", onPick);
    return () => window.removeEventListener("mitra:play-scenario", onPick);
  }, [scenarios]);

  // Playback clock.
  useEffect(() => {
    if (!playing || done) {
      signal.current = { amp: 0, who: null };
      return;
    }
    let raf = 0;
    let last = performance.now();
    let acc = elapsed;
    let lastCommit = 0;
    const tick = (now: number) => {
      acc += now - last;
      last = now;
      const slot = slots.findIndex((sl) => acc >= sl.start && acc < sl.end);
      signal.current =
        slot >= 0
          ? {
              amp: envelope(acc) * (scenario.lines[slot].who === "mitra" ? 1 : 0.7),
              who: scenario.lines[slot].who,
            }
          : { amp: 0, who: null };
      if (now - lastCommit > 40) {
        lastCommit = now;
        setElapsed(acc);
      }
      if (acc < total) raf = requestAnimationFrame(tick);
      else setElapsed(total);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // `elapsed` is read once as the resume point on purpose.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, done, slots, total, scenario]);

  const choose = useCallback(
    (i: number) => {
      setIndex(i);
      setElapsed(0);
      setPlaying(inViewRef.current && !reduced);
    },
    [reduced],
  );

  const replay = () => {
    setElapsed(0);
    setPlaying(true);
  };

  // TODO(audio): when real samples exist, play `scenario.audio` here while
  // soundOn is true and drive `signal.amp` from an AnalyserNode.
  const toggleSound = () => setSoundOn((v) => !v);

  const callSec = Math.min(1, at / total) * seconds(scenario.duration);
  const titleParts = hear.title;

  return (
    <section
      id="hear"
      ref={sectionRef}
      className={`${s.hear} grain offscreen`}
      style={{ "--cis": "220vh" } as React.CSSProperties}
      aria-labelledby="hear-title"
    >
      <div className={s.sticky}>
        <div className={s.copy} data-reveal>
          <p className={`${s.eyebrow} mono-label fade-in`}>{hear.eyebrow}</p>
          <h2 id="hear-title" className={s.title}>
            {titleParts.map((line, i) => (
              <span className="mask" key={line}>
                <span className="mask-in" style={{ "--i": i } as React.CSSProperties}>
                  {line.split(hear.titleAccent).map((chunk, j, arr) => (
                    <span key={j}>
                      {chunk}
                      {j < arr.length - 1 && <em className="accent">{hear.titleAccent}</em>}
                    </span>
                  ))}
                </span>
              </span>
            ))}
          </h2>
          <p className={`${s.body} fade-in`} style={{ "--i": 2 } as React.CSSProperties}>
            {hear.body}
          </p>

          <div
            className={`${s.segments} fade-in`}
            style={
              {
                "--idx": index,
                "--n": scenarios.length,
                "--i": 3,
              } as React.CSSProperties
            }
            role="group"
            aria-label={hear.switchLabel}
          >
            <span className={s.thumb} aria-hidden="true" />
            {scenarios.map((sc, i) => (
              <button
                key={sc.id}
                type="button"
                className={s.segment}
                aria-pressed={i === index}
                onClick={() => choose(i)}
              >
                <span className={s.segLong}>{sc.label}</span>
                <span className={s.segShort}>{sc.short}</span>
              </button>
            ))}
          </div>

          <div className={s.controls}>
            <button
              type="button"
              className={s.control}
              aria-pressed={soundOn}
              aria-label={hear.soundOn}
              onClick={toggleSound}
            >
              <svg viewBox="0 0 16 16" aria-hidden="true">
                <path d="M2.5 6v4h2.6L8.5 13V3L5.1 6Z" />
                {soundOn ? (
                  <path d="M11 5.5a3.5 3.5 0 0 1 0 5M12.8 3.6a6 6 0 0 1 0 8.8" />
                ) : (
                  <path d="m11 6 3.5 4M14.5 6 11 10" />
                )}
              </svg>
              <span aria-hidden="true">{hear.soundOn}</span>
            </button>
            <button type="button" className={s.control} onClick={replay} disabled={reduced} aria-label={hear.replay}>
              <svg viewBox="0 0 16 16" aria-hidden="true">
                <path d="M3 8a5 5 0 1 0 1.6-3.7M3 2.5v2.5h2.5" />
              </svg>
              <span aria-hidden="true">{hear.replay}</span>
            </button>
            {soundOn && (
              <p className={s.note} role="status">
                {hear.soundSoon}
              </p>
            )}
          </div>
        </div>

        <div className={s.stage}>
          <div className={s.sphereWrap}>
            <div className={s.spherePoster} aria-hidden="true" />
            {near && <VoiceSphere signal={signal} className={s.sphere} />}
          </div>

          <div className={s.transcript} aria-live="off">
            <div className={s.callHead}>
              <span className={s.live} data-idle={done || !playing ? "" : undefined} aria-hidden="true" />
              <span className={s.business}>
                <span className={s.businessName}>{scenario.business}</span>
                <span className={s.meta}>
                  {hear.live} · {scenario.language}
                </span>
              </span>
              <span className={s.timer} aria-label={`${clock(callSec)} of ${scenario.duration}`}>
                {clock(callSec)} / {scenario.duration}
              </span>
            </div>
            <ol className={s.lines}>
              {scenario.lines.map((line, i) => {
                const slot = slots[i];
                if (at < slot.start) return null;
                const typing = at < slot.end;
                const shown = typing
                  ? line.text.slice(0, Math.floor(((at - slot.start) / (slot.end - slot.start)) * line.text.length))
                  : line.text;
                const active = typing || (i === scenario.lines.length - 1 && !done);
                return (
                  <li
                    key={`${scenario.id}-${i}`}
                    className={s.line}
                    data-who={line.who}
                    data-past={active ? undefined : ""}
                  >
                    <span className={s.who}>{line.who === "mitra" ? hear.speakerMitra : hear.speakerCaller}</span>
                    <span>
                      <span className="sr-only">{line.text}</span>
                      <span aria-hidden="true">
                        {shown}
                        {typing && <span className={s.caret} />}
                      </span>
                    </span>
                  </li>
                );
              })}
            </ol>
          </div>
        </div>
      </div>
    </section>
  );
}
