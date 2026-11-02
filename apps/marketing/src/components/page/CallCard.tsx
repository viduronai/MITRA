import type { ScriptLine } from "@/content";
import s from "./page.module.css";

type Props = {
  business: string;
  meta: string;
  liveLabel: string;
  lines: ScriptLine[];
  speakers: { mitra: string; caller: string };
  outcomes?: string[];
  outcomesLabel?: string;
};

/** A static sample call: who, transcript, and what happened after. */
export function CallCard({ business, meta, liveLabel, lines, speakers, outcomes, outcomesLabel }: Props) {
  return (
    <figure className={s.call}>
      <figcaption className={s.callHead}>
        <span className={s.callWho}>
          <span className={s.callAvatar} aria-hidden="true" />
          <span className={s.callText}>
            <span className={s.callName}>{business}</span>
            <span className={s.callMeta}>{meta}</span>
          </span>
        </span>
        <span className={s.live}>{liveLabel}</span>
      </figcaption>
      <ol className={s.lines}>
        {lines.map((l, i) => (
          <li key={i} className={s.lineItem} data-who={l.who}>
            <span className={s.speaker}>{l.who === "mitra" ? speakers.mitra : speakers.caller}</span>
            <p>{l.text}</p>
          </li>
        ))}
      </ol>
      {outcomes && outcomes.length > 0 && (
        <ul className={s.outcomes} aria-label={outcomesLabel}>
          {outcomes.map((o) => (
            <li key={o} className={s.outcome}>
              {o}
            </li>
          ))}
        </ul>
      )}
    </figure>
  );
}
