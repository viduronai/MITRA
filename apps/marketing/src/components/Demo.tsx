import { content, type Copy } from "@/content";
import { media } from "@/lib/media";
import { DemoForm } from "./DemoForm";
import { LazyVideo } from "./LazyVideo";
import s from "./demo.module.css";

export function Demo({ copy = content.en }: { copy?: Copy }) {
  const { demo } = copy;
  const chip = demo.chip.replace(/^\[\s*|\s*\]$/g, "");
  return (
    <section id="demo" className={`${s.demo} grain offscreen`} aria-labelledby="demo-title">
      <div className={s.media} aria-hidden="true">
        <LazyVideo className={s.video} src={media.demoFace} poster={media.demoFacePoster} />
      </div>
      <div className={s.scrim} aria-hidden="true" />

      <div className={s.body}>
        <div className={s.panel} data-reveal>
          <p className={`${s.chip} fade-in`}>
            <b aria-hidden="true">[</b> {chip} <b aria-hidden="true">]</b>
          </p>
          <h2 id="demo-title" className={s.title}>
            <span className="mask">
              <span className="mask-in" style={{ "--d": "80ms" } as React.CSSProperties}>
                {demo.title}
              </span>
            </span>
          </h2>
          <p className={`${s.tagline} fade-in`} style={{ "--i": 2 } as React.CSSProperties}>
            {demo.tagline}
          </p>
          <DemoForm copy={copy} />
        </div>
      </div>

      <p className={s.legal}>
        {demo.legal.before}
        <a href="/privacy">{demo.legal.privacy}</a>
        {demo.legal.middle}
        <a href="/terms">{demo.legal.terms}</a>
        {demo.legal.after}
      </p>
    </section>
  );
}
