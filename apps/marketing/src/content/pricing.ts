/*
 * /pricing copy in every locale. Facts: docs/09-ROADMAP-PRICING-METRICS.md §3
 * (indicative, excl. GST). Rates and thresholds live in `rates` so the
 * calculator and every locale read the same numbers.
 */

import type { Locale } from "./types";

export const rates = {
  smart: 3,
  natural: 4.5,
  signature: 6,
  /** One full-time telecaller, per month (07-SCREENS §2.4). */
  telecallerMonthly: 18000,
  /** Talk-minutes one telecaller handles a month: ₹18,000 at ≈ ₹12 per productive minute (09 §3.4). */
  telecallerMinutes: 1500,
  daysPerMonth: 30,
} as const;

export type TierId = "smart" | "natural" | "signature";

const en = {
  meta: {
    title: "Pricing",
    description:
      "From ₹3 a minute, no monthly fee. Billed per second of connected talk-time; unanswered calls are free. Every feature at every tier.",
  },
  hero: {
    eyebrow: "Pricing",
    title: ["Pay only when", "Mitra talks."],
    accent: "talks.",
    sub: "From ₹3 a minute. No monthly fee, no setup fee, no feature paywalls. Billed per second of connected talk-time.",
    primary: "Calculate my cost",
    secondary: "Call me now",
  },
  tiers: {
    label: "Voice tiers",
    title: ["Three voices.", "Every feature."],
    accent: "Every feature.",
    lead: "The tier only changes how Mitra sounds. Set it per employee: your receptionist on Natural, your reminder caller on Smart.",
    perMinute: "/ min",
    featured: "Trial runs on this tier",
    sample: "Hear",
    sampleSoon: "Voice sample on the way.",
    bestFor: "Best for",
    items: [
      {
        id: "smart" as TierId,
        name: "Smart",
        line: "Good natural voices on an efficient stack.",
        changes: ["Natural voices", "Basic back-channels (“hmm”, “okay”)"],
        bestFor: "Reminders, confirmations, payment nudges, big lists",
      },
      {
        id: "natural" as TierId,
        name: "Natural",
        line: "Premium Indic voices with the full human layer.",
        changes: ["Premium Telugu, Hindi, English voices", "Fillers, dialect and formality tuning"],
        bestFor: "Receptionist, lead calling",
      },
      {
        id: "signature" as TierId,
        name: "Signature",
        line: "Top-tier voices, trained to sound like your best caller.",
        changes: ["Top-tier voices", "Priority capacity at peak hours"],
        bestFor: "Premium brands, high-value real estate",
      },
    ],
    includedLabel: "Included at every tier",
    included: ["AI teams", "Routines", "Approvals", "WhatsApp Manager", "Integrations", "Reports"],
    free: "Start with 100 free minutes on Natural. No card needed.",
  },
  calc: {
    label: "Calculator",
    title: ["What would it", "cost me?"],
    accent: "cost me?",
    lead: "Move the sliders to match a normal day. Unanswered calls cost nothing, so count only calls that connect.",
    calls: "Connected calls per day",
    minutes: "Average call length",
    minutesUnit: "min",
    tier: "Voice tier",
    result: "Your estimate",
    perMonth: "/ month",
    breakdown: "{calls} calls × {minutes} min × 30 days = {total} minutes",
    mitra: "Mitra",
    telecallers: "Telecallers for the same talk-time",
    telecallerOne: "1 telecaller",
    telecallerMany: "{n} telecallers",
    save: "About {amount} less every month.",
    note: "Estimate excludes GST. A telecaller costs about ₹18,000 a month and talks about 1,500 minutes in that time (≈ ₹12 a productive minute).",
  },
  bonus: {
    label: "Wallet",
    title: ["Top up more,", "get more."],
    accent: "get more.",
    lead: "Prepaid wallet, no subscription. Top up by UPI, card or net banking. Credits stay valid for 12 months.",
    head: ["Top-up", "Bonus credits"],
    rows: [
      ["₹10,000 or more", "+5%"],
      ["₹25,000 or more", "+10%"],
      ["₹1,00,000 or more", "+15%"],
    ],
    facts: ["Minimum top-up ₹500", "UPI AutoPay top-up (optional)", "Credits valid 12 months"],
  },
  extras: {
    label: "Extras",
    title: ["Passed through", "at cost."],
    accent: "at cost.",
    lead: "A few things come from telecom and messaging providers. We charge exactly what they charge us and show it upfront.",
    items: [
      { name: "Dedicated local number", price: "≈ ₹499 / month", note: "Waived in any month with ₹3,000+ usage" },
      { name: "Verified business caller ID", price: "At cost", note: "Truecaller Business and CNAP name registration" },
      { name: "WhatsApp template messages", price: "Meta's rate", note: "Reminders, confirmations, heads-up messages" },
      { name: "SMS fallback", price: "Operator rate", note: "Only when WhatsApp isn't available" },
    ],
    volume: "Over 25,000 minutes a month, or running an agency?",
    volumeLink: "See partner rates",
    concurrency: "5 calls at the same time by default, raised automatically as you grow.",
  },
  faq: {
    label: "Questions",
    title: ["Pricing,", "plainly."],
    accent: "plainly.",
    items: [
      {
        q: "What exactly is a “connected minute”?",
        a: "Time when Mitra and the other person are actually talking. We bill per second, with a 10-second minimum per connected call. Ringing time doesn't count.",
      },
      {
        q: "Do I pay for calls nobody answers?",
        a: "No. Unanswered, busy and voicemail calls are free, and so are calls our compliance checks stop before dialling (for example, numbers on Do-Not-Disturb).",
      },
      {
        q: "Is there a monthly fee or a contract?",
        a: "No. You top up a wallet and use it. Stop any time; unused credits stay valid for 12 months.",
      },
      {
        q: "Can I mix tiers?",
        a: "Yes. The tier is set per AI employee, and you can change it whenever you like. The new rate applies from the next call.",
      },
      {
        q: "Do I need a new phone number?",
        a: "Not necessarily. You can connect your existing business number, or take a local number from us (about ₹499 a month, waived when you use ₹3,000 or more that month).",
      },
      {
        q: "Are prices inclusive of GST?",
        a: "No. All prices are before GST, which is added to your top-up invoice.",
      },
      {
        q: "What does the free start include?",
        a: "100 free minutes on the Natural tier when you sign up, with every feature switched on. No card needed.",
      },
    ],
  },
  cta: {
    title: ["Your phone rings.", "Mitra answers."],
    accent: "Mitra answers.",
    text: "Get a real demo call in 30 seconds, in Telugu, Hindi or English.",
    primary: "Call me now",
    secondary: "How it works",
  },
};

export type PricingCopy = typeof en;

const te: PricingCopy = {
  meta: {
    title: "ధరలు",
    description:
      "నిమిషానికి ₹3 నుంచి, monthly fee లేదు. Connect అయిన call కి second లెక్కన bill; ఎత్తని calls free. ప్రతి tier లో అన్ని features.",
  },
  hero: {
    eyebrow: "ధరలు",
    title: ["Mitra మాట్లాడినప్పుడే", "కట్టండి."],
    accent: "కట్టండి.",
    sub: "నిమిషానికి ₹3 నుంచి. Monthly fee లేదు, setup fee లేదు, features కి extra charge లేదు. Connect అయిన talk-time కి second లెక్కన bill.",
    primary: "నా ఖర్చు లెక్కించండి",
    secondary: "నాకు call చేయండి",
  },
  tiers: {
    label: "Voice tiers",
    title: ["మూడు voices.", "అన్ని features."],
    accent: "అన్ని features.",
    lead: "Tier మారిస్తే Mitra గొంతు మాత్రమే మారుతుంది. ఒక్కో ఉద్యోగికి వేరే tier పెట్టొచ్చు: receptionist కి Natural, reminder caller కి Smart.",
    perMinute: "/ నిమిషం",
    featured: "Trial ఈ tier లోనే",
    sample: "వినండి",
    sampleSoon: "Voice sample త్వరలో వస్తుంది.",
    bestFor: "దీనికి బాగుంటుంది",
    items: [
      {
        id: "smart",
        name: "Smart",
        line: "తక్కువ ఖర్చులో మంచి natural voices.",
        changes: ["Natural voices", "చిన్న back-channels (“hmm”, “okay”)"],
        bestFor: "Reminders, confirmations, payment గుర్తుచేయడం, పెద్ద lists",
      },
      {
        id: "natural",
        name: "Natural",
        line: "Premium Indic voices, పూర్తి human touch తో.",
        changes: ["Premium తెలుగు, हिंदी, English voices", "Fillers, యాస, మర్యాద tuning"],
        bestFor: "Receptionist, lead calling",
      },
      {
        id: "signature",
        name: "Signature",
        line: "Top-tier voices, మీ best caller లాగా మాట్లాడేలా training.",
        changes: ["Top-tier voices", "Peak hours లో priority capacity"],
        bestFor: "Premium brands, high-value real estate",
      },
    ],
    includedLabel: "ప్రతి tier లో ఉన్నవి",
    included: ["AI teams", "Routines", "Approvals", "WhatsApp Manager", "Integrations", "Reports"],
    free: "Natural tier లో 100 free నిమిషాలతో మొదలుపెట్టండి. Card అవసరం లేదు.",
  },
  calc: {
    label: "Calculator",
    title: ["నాకు ఎంత", "అవుతుంది?"],
    accent: "అవుతుంది?",
    lead: "మామూలు రోజుకి తగ్గట్టు sliders జరపండి. ఎత్తని calls కి ఖర్చు లేదు, కాబట్టి connect అయిన calls మాత్రమే లెక్కపెట్టండి.",
    calls: "రోజుకి connect అయ్యే calls",
    minutes: "ఒక్కో call సగటు సమయం",
    minutesUnit: "ని.",
    tier: "Voice tier",
    result: "మీ అంచనా",
    perMonth: "/ నెల",
    breakdown: "{calls} calls × {minutes} ని. × 30 రోజులు = {total} నిమిషాలు",
    mitra: "Mitra",
    telecallers: "ఇదే talk-time కి telecallers",
    telecallerOne: "1 telecaller",
    telecallerMany: "{n} telecallers",
    save: "నెలకు సుమారు {amount} తక్కువ.",
    note: "అంచనాలో GST లేదు. ఒక telecaller కి నెలకు సుమారు ₹18,000, ఆ సమయంలో సుమారు 1,500 నిమిషాలు మాట్లాడతారు (పని నిమిషానికి ≈ ₹12).",
  },
  bonus: {
    label: "Wallet",
    title: ["ఎక్కువ top-up,", "ఎక్కువ bonus."],
    accent: "ఎక్కువ bonus.",
    lead: "Prepaid wallet, subscription లేదు. UPI, card లేదా net banking తో top-up. Credits 12 నెలలు valid.",
    head: ["Top-up", "Bonus credits"],
    rows: [
      ["₹10,000 లేదా ఎక్కువ", "+5%"],
      ["₹25,000 లేదా ఎక్కువ", "+10%"],
      ["₹1,00,000 లేదా ఎక్కువ", "+15%"],
    ],
    facts: ["కనీస top-up ₹500", "UPI AutoPay top-up (మీ ఇష్టం)", "Credits 12 నెలలు valid"],
  },
  extras: {
    label: "Extras",
    title: ["ఖర్చు ఎంతో", "అంతే."],
    accent: "అంతే.",
    lead: "కొన్ని telecom, messaging providers నుంచి వస్తాయి. వాళ్ళు మాకు ఎంత వేస్తారో మీకు అంతే, ముందే చూపిస్తాం.",
    items: [
      { name: "Dedicated local number", price: "≈ ₹499 / నెల", note: "₹3,000+ వాడిన నెలలో free" },
      { name: "Verified business caller ID", price: "ఖర్చుకే", note: "Truecaller Business, CNAP పేరు registration" },
      { name: "WhatsApp template messages", price: "Meta rate", note: "Reminders, confirmations, ముందస్తు messages" },
      { name: "SMS fallback", price: "Operator rate", note: "WhatsApp లేనప్పుడు మాత్రమే" },
    ],
    volume: "నెలకు 25,000 నిమిషాలకు పైగా, లేదా agency నడుపుతున్నారా?",
    volumeLink: "Partner rates చూడండి",
    concurrency: "మొదట ఒకేసారి 5 calls, మీ వాడకం పెరిగే కొద్దీ ఆటోమేటిక్ గా పెరుగుతుంది.",
  },
  faq: {
    label: "ప్రశ్నలు",
    title: ["ధరల గురించి,", "సూటిగా."],
    accent: "సూటిగా.",
    items: [
      {
        q: "“Connected minute” అంటే ఏంటి?",
        a: "Mitra, అవతలి వ్యక్తి నిజంగా మాట్లాడుకునే సమయం. Second లెక్కన bill, ఒక్కో connected call కి కనీసం 10 seconds. Ring అయ్యే సమయం లెక్కలోకి రాదు.",
      },
      {
        q: "ఎవరూ ఎత్తని calls కి కట్టాలా?",
        a: "లేదు. ఎత్తని, busy, voicemail calls free. Dial చేయకముందే మా compliance checks ఆపేసిన calls కూడా free (ఉదా: Do-Not-Disturb numbers).",
      },
      {
        q: "Monthly fee లేదా contract ఉందా?",
        a: "లేదు. Wallet top-up చేసి వాడుకోండి. ఎప్పుడైనా ఆపేయొచ్చు; మిగిలిన credits 12 నెలలు valid.",
      },
      {
        q: "వేర్వేరు tiers కలిపి వాడొచ్చా?",
        a: "వాడొచ్చు. Tier ఒక్కో AI ఉద్యోగికి విడిగా, ఎప్పుడైనా మార్చుకోవచ్చు. కొత్త rate తర్వాతి call నుంచి.",
      },
      {
        q: "కొత్త phone number కావాలా?",
        a: "అవసరం లేదు. మీ business number నే connect చేయొచ్చు, లేదా మా దగ్గర local number తీసుకోవచ్చు (నెలకు సుమారు ₹499, ఆ నెల ₹3,000+ వాడితే free).",
      },
      {
        q: "ధరల్లో GST ఉందా?",
        a: "లేదు. అన్ని ధరలు GST కి ముందు; GST మీ top-up invoice లో కలుస్తుంది.",
      },
      {
        q: "Free start లో ఏం వస్తుంది?",
        a: "Sign up చేయగానే Natural tier లో 100 free నిమిషాలు, అన్ని features on. Card అవసరం లేదు.",
      },
    ],
  },
  cta: {
    title: ["మీ ఫోన్ మోగుతుంది.", "Mitra answer చేస్తుంది."],
    accent: "Mitra answer చేస్తుంది.",
    text: "30 seconds లో నిజమైన demo call, తెలుగు, हिंदी లేదా English లో.",
    primary: "నాకు call చేయండి",
    secondary: "ఎలా పని చేస్తుంది",
  },
};

const hi: PricingCopy = {
  meta: {
    title: "क़ीमत",
    description:
      "₹3 प्रति मिनट से, कोई monthly fee नहीं। Connect हुई call का billing हर second के हिसाब से; न उठाई गई calls मुफ़्त। हर tier में सारे features.",
  },
  hero: {
    eyebrow: "क़ीमत",
    title: ["पैसे तभी, जब", "Mitra बात करे।"],
    accent: "Mitra बात करे।",
    sub: "₹3 प्रति मिनट से। कोई monthly fee नहीं, कोई setup fee नहीं, features पर कोई रोक नहीं। Connect हुई बातचीत का billing हर second के हिसाब से।",
    primary: "मेरा ख़र्च निकालें",
    secondary: "मुझे call करें",
  },
  tiers: {
    label: "Voice tiers",
    title: ["तीन आवाज़ें।", "सारे features."],
    accent: "सारे features.",
    lead: "Tier से सिर्फ़ Mitra की आवाज़ बदलती है। हर कर्मचारी का tier अलग रखें: receptionist Natural पर, reminder caller Smart पर।",
    perMinute: "/ मिनट",
    featured: "Trial इसी tier पर",
    sample: "सुनें",
    sampleSoon: "Voice sample जल्द आ रहा है।",
    bestFor: "इसके लिए सही",
    items: [
      {
        id: "smart",
        name: "Smart",
        line: "कम ख़र्च में अच्छी natural आवाज़ें।",
        changes: ["Natural आवाज़ें", "छोटे back-channels (“हम्म”, “okay”)"],
        bestFor: "Reminders, confirmations, payment याद दिलाना, बड़ी lists",
      },
      {
        id: "natural",
        name: "Natural",
        line: "Premium Indic आवाज़ें, पूरे human touch के साथ।",
        changes: ["Premium हिंदी, తెలుగు, English आवाज़ें", "Fillers, लहजा और अदब की tuning"],
        bestFor: "Receptionist, lead calling",
      },
      {
        id: "signature",
        name: "Signature",
        line: "Top-tier आवाज़ें, आपके best caller जैसी बोलने की training.",
        changes: ["Top-tier आवाज़ें", "Peak hours में priority capacity"],
        bestFor: "Premium brands, high-value real estate",
      },
    ],
    includedLabel: "हर tier में शामिल",
    included: ["AI teams", "Routines", "Approvals", "WhatsApp Manager", "Integrations", "Reports"],
    free: "Natural tier पर 100 मुफ़्त मिनट से शुरू करें। Card की ज़रूरत नहीं।",
  },
  calc: {
    label: "Calculator",
    title: ["मेरा कितना", "ख़र्च होगा?"],
    accent: "ख़र्च होगा?",
    lead: "Sliders को एक आम दिन के हिसाब से रखें। न उठाई गई calls का कोई पैसा नहीं, इसलिए सिर्फ़ connect होने वाली calls गिनें।",
    calls: "रोज़ connect होने वाली calls",
    minutes: "एक call का औसत समय",
    minutesUnit: "मि.",
    tier: "Voice tier",
    result: "आपका अनुमान",
    perMonth: "/ महीना",
    breakdown: "{calls} calls × {minutes} मि. × 30 दिन = {total} मिनट",
    mitra: "Mitra",
    telecallers: "इतनी ही बातचीत के लिए telecallers",
    telecallerOne: "1 telecaller",
    telecallerMany: "{n} telecallers",
    save: "हर महीने लगभग {amount} कम।",
    note: "अनुमान में GST शामिल नहीं। एक telecaller का ख़र्च लगभग ₹18,000 महीना है और वो इस दौरान लगभग 1,500 मिनट बात करते हैं (≈ ₹12 प्रति काम का मिनट)।",
  },
  bonus: {
    label: "Wallet",
    title: ["ज़्यादा top-up,", "ज़्यादा bonus."],
    accent: "ज़्यादा bonus.",
    lead: "Prepaid wallet, कोई subscription नहीं। UPI, card या net banking से top-up करें। Credits 12 महीने valid रहते हैं।",
    head: ["Top-up", "Bonus credits"],
    rows: [
      ["₹10,000 या ज़्यादा", "+5%"],
      ["₹25,000 या ज़्यादा", "+10%"],
      ["₹1,00,000 या ज़्यादा", "+15%"],
    ],
    facts: ["कम से कम top-up ₹500", "UPI AutoPay top-up (अगर चाहें)", "Credits 12 महीने valid"],
  },
  extras: {
    label: "Extras",
    title: ["जितना ख़र्च,", "उतना ही।"],
    accent: "उतना ही।",
    lead: "कुछ चीज़ें telecom और messaging providers से आती हैं। वो हमसे जितना लेते हैं, हम आपसे उतना ही लेते हैं, और पहले से बताते हैं।",
    items: [
      { name: "Dedicated local number", price: "≈ ₹499 / महीना", note: "जिस महीने ₹3,000+ इस्तेमाल हो, उसमें मुफ़्त" },
      { name: "Verified business caller ID", price: "लागत पर", note: "Truecaller Business और CNAP नाम registration" },
      { name: "WhatsApp template messages", price: "Meta का rate", note: "Reminders, confirmations, पहले से सूचना" },
      { name: "SMS fallback", price: "Operator rate", note: "सिर्फ़ जब WhatsApp न हो" },
    ],
    volume: "महीने में 25,000 से ज़्यादा मिनट, या agency चलाते हैं?",
    volumeLink: "Partner rates देखें",
    concurrency: "शुरुआत में एक साथ 5 calls, इस्तेमाल बढ़ने पर अपने आप बढ़ जाती हैं।",
  },
  faq: {
    label: "सवाल",
    title: ["क़ीमत,", "साफ़-साफ़।"],
    accent: "साफ़-साफ़।",
    items: [
      {
        q: "“Connected minute” का मतलब क्या है?",
        a: "वो समय जब Mitra और सामने वाला सच में बात कर रहे हों। Billing हर second के हिसाब से, हर connected call पर कम से कम 10 seconds. Ring होने का समय नहीं गिना जाता।",
      },
      {
        q: "जो calls कोई नहीं उठाता, उनका पैसा लगेगा?",
        a: "नहीं। न उठाई गई, busy और voicemail calls मुफ़्त हैं। जिन calls को हमारी compliance checks dial से पहले रोक दें (जैसे Do-Not-Disturb numbers), वो भी मुफ़्त।",
      },
      {
        q: "कोई monthly fee या contract है?",
        a: "नहीं। Wallet top-up करें और इस्तेमाल करें। कभी भी रोक दें; बचे हुए credits 12 महीने valid रहते हैं।",
      },
      {
        q: "क्या अलग-अलग tiers मिला सकते हैं?",
        a: "हाँ। Tier हर AI कर्मचारी के लिए अलग है और कभी भी बदला जा सकता है। नया rate अगली call से लागू होता है।",
      },
      {
        q: "क्या नया phone number चाहिए?",
        a: "ज़रूरी नहीं। आप अपना मौजूदा business number जोड़ सकते हैं, या हमसे local number ले सकते हैं (लगभग ₹499 महीना, उस महीने ₹3,000+ इस्तेमाल पर मुफ़्त)।",
      },
      {
        q: "क्या क़ीमतों में GST शामिल है?",
        a: "नहीं। सारी क़ीमतें GST से पहले की हैं; GST आपके top-up invoice में जुड़ता है।",
      },
      {
        q: "Free start में क्या मिलता है?",
        a: "Sign up करते ही Natural tier पर 100 मुफ़्त मिनट, सारे features चालू। Card की ज़रूरत नहीं।",
      },
    ],
  },
  cta: {
    title: ["आपका फ़ोन बजता है।", "Mitra जवाब देती है।"],
    accent: "Mitra जवाब देती है।",
    text: "30 seconds में असली demo call, हिंदी, తెలుగు या English में।",
    primary: "मुझे call करें",
    secondary: "कैसे काम करता है",
  },
};

export const pricingContent: Record<Locale, PricingCopy> = { en, te, hi };
