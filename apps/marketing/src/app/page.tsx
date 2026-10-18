import { CallerId } from "@/components/CallerId";
import { CompactHeader } from "@/components/CompactHeader";
import { Demo } from "@/components/Demo";
import { Footer } from "@/components/Footer";
import { HearIt } from "@/components/HearIt";
import { Hero } from "@/components/Hero";
import { Industries } from "@/components/Industries";
import { Pricing } from "@/components/Pricing";
import { Team } from "@/components/Team";
import { WhatsApp } from "@/components/WhatsApp";

// Scene order: docs/design/landing-direction.md §2.
export default function Home() {
  return (
    <>
      <Hero />
      <CompactHeader />
      <main id="main" tabIndex={-1}>
        <Demo />
        <HearIt />
        <Team />
        <WhatsApp />
        <CallerId />
        <Pricing />
        <Industries />
      </main>
      <Footer />
    </>
  );
}
