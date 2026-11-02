import { content, type Locale } from "@/content";
import { CallerId } from "./CallerId";
import { CompactHeader } from "./CompactHeader";
import { Demo } from "./Demo";
import { Footer } from "./Footer";
import { HearIt } from "./HearIt";
import { Hero } from "./Hero";
import { Industries } from "./Industries";
import { languageHrefs } from "./LangSwitch";
import { Pricing } from "./Pricing";
import { Team } from "./Team";
import { WhatsApp } from "./WhatsApp";

// Scene order: docs/design/landing-direction.md §2. Same story in every locale.
export function HomePage({ locale }: { locale: Locale }) {
  const copy = content[locale];
  const langHrefs = languageHrefs(locale, copy.homeHref, "/");
  return (
    <>
      <Hero copy={copy} />
      <CompactHeader copy={copy} langHrefs={langHrefs} />
      <main id="main" tabIndex={-1}>
        <Demo copy={copy} />
        <HearIt copy={copy} />
        <Team copy={copy} />
        <WhatsApp copy={copy} />
        <CallerId copy={copy} />
        <Pricing copy={copy} />
        <Industries copy={copy} />
      </main>
      <Footer copy={copy} langHrefs={langHrefs} />
    </>
  );
}
