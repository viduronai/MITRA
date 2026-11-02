/*
 * /how-it-works, /safety and /about. Safety facts follow
 * docs/08-COMPLIANCE-SECURITY.md (plain language, not legal advice).
 */

export const howItWorks = {
  meta: {
    title: "How it works",
    description:
      "Teach Mitra your business in minutes, test it on your own phone, then go live. Every call starts with an AI disclosure and ends with a summary on WhatsApp.",
  },
  hero: {
    eyebrow: "How it works",
    title: ["Teach it once.", "It works every day."],
    accent: "It works every day.",
    sub: "No scripts to write and no software to learn. Tell Mitra about your business, hear it on your own phone, and switch it on.",
    primary: "Call me now",
    secondary: "See pricing",
  },
  steps: {
    label: "Three steps",
    title: ["From sign-up to", "first call."],
    accent: "first call.",
    lead: "Most owners finish setup in one sitting. You can change anything later from the app or by WhatsApp.",
    items: [
      {
        n: "01",
        title: "Teach",
        text: "Paste your website or type a few lines: services, prices, timings, location. Mitra turns it into facts you confirm with a tap.",
        ui: ["Timings · Mon–Sat 9 AM–8 PM ✓", "Consultation · ₹500 ✓", "Parking · Basement, free ?"],
      },
      {
        n: "02",
        title: "Test",
        text: "Mitra calls your own phone. Talk to it like a customer would. Anything it gets wrong, you correct in plain words.",
        ui: ["Mitra: Namaskaram, Sunrise Clinic…", "You: Sunday open aa?", "Fix: “We close on Sundays.” ✓"],
      },
      {
        n: "03",
        title: "Go live",
        text: "Forward your calls, connect your leads, pick a voice tier. Mitra starts answering, and you get a report every evening.",
        ui: ["Receptionist · Working", "Reminder Caller · Working", "Today: 46 calls · 19 booked"],
      },
    ],
  },
  call: {
    label: "On every call",
    title: ["What happens", "when the phone rings."],
    accent: "when the phone rings.",
    items: [
      { title: "It picks up in under a second", text: "No IVR menu and no hold music. In the caller's language: Telugu, Hindi or English." },
      { title: "It says it's an AI assistant", text: "Every call starts with a short disclosure and a recording notice. You can reword it, never remove it." },
      { title: "It understands and acts", text: "Books, reschedules, answers from your confirmed facts, or transfers to your staff when it should." },
      { title: "It follows up on WhatsApp", text: "Confirmations, locations and payment links go out right after the call." },
      { title: "You get the summary", text: "Every evening on WhatsApp: numbers first, and anything that needs you on top." },
    ],
  },
  team: {
    label: "AI team",
    title: ["One job each.", "Nothing dropped."],
    accent: "Nothing dropped.",
    lead: "Add AI employees as you need them. Each has one job, its own voice tier and its own working hours.",
    items: [
      { title: "Receptionist", text: "Answers every incoming call, books and routes.", note: "Inbound" },
      { title: "Lead Caller", text: "Calls every new enquiry within a minute.", note: "Outbound · to people who asked" },
      { title: "Reminder Caller", text: "Confirms appointments and visits, the day before.", note: "Outbound · existing customers" },
      { title: "Payment Caller", text: "Reminds dues politely and sends the UPI link.", note: "Outbound · existing customers" },
    ],
  },
  control: {
    label: "You stay in charge",
    title: ["Nothing important", "happens without you."],
    accent: "without you.",
    items: [
      { title: "Approvals on WhatsApp", text: "Discounts, refunds and reschedules beyond your rules wait for your Approve tap." },
      { title: "Pause any time", text: "One tap pauses an employee or everything. Calls go back to your own phone." },
      { title: "Working hours and limits", text: "Set when each employee may call, and how often a customer may be called." },
      { title: "Every call recorded and summarised", text: "Listen, read the transcript, and correct Mitra from the call itself." },
    ],
  },
  faqHead: { label: "Questions", title: ["Before you", "switch it on."], accent: "switch it on." },
  faq: [
    { q: "Do I need technical skills?", a: "No. If you can use WhatsApp, you can set up Mitra. We also set it up with you during the pilot." },
    { q: "Will my customers know it's an AI?", a: "Yes. Every call begins with a disclosure. People are comfortable with it when the help is fast and accurate." },
    { q: "What if Mitra doesn't know an answer?", a: "It says someone will get back, notes the question and puts it in your report so you can teach it the answer once." },
    { q: "Can I use my current phone number?", a: "Yes. Forward your business number to Mitra, or take a new local number from us." },
  ],
  cta: { title: ["Your phone rings.", "Mitra answers."], accent: "Mitra answers.", primary: "Call me now", secondary: "See pricing" },
};

export const safety = {
  meta: {
    title: "Safety & trust",
    description:
      "How Mitra stays honest and safe: AI disclosure on every call, consent and Do-Not-Disturb checks, calling hours, data stored in India, and your verified caller ID.",
  },
  hero: {
    eyebrow: "Safety & trust",
    title: ["Trust isn't a feature.", "It's the product."],
    accent: "It's the product.",
    sub: "Mitra talks to your customers in your name. These are the rules it follows on every call, written in plain words. Most of them are enforced in code, so nobody can switch them off by mistake.",
  },
  toc: {
    label: "On this page",
    items: [
      { id: "disclosure", label: "AI disclosure" },
      { id: "consent", label: "Consent & DND" },
      { id: "caller-id", label: "Caller ID" },
      { id: "data", label: "Your data" },
      { id: "sensitive", label: "Sensitive calls" },
      { id: "controls", label: "Your controls" },
    ],
  },
  disclosure: {
    label: "AI disclosure",
    title: ["Mitra always says", "it's an AI."],
    accent: "it's an AI.",
    lead: "Every call starts by saying who is calling, that it's an AI assistant, and that the call may be recorded. Businesses can reword it in their own style, but can't remove it.",
    examples: [
      { lang: "en", label: "English", text: "Hi, this is Priya, an AI assistant from Sunrise Clinic. This call may be recorded to help serve you better." },
      { lang: "te", label: "తెలుగు", text: "నమస్కారం, నేను Priya, Sunrise Clinic నుంచి AI assistant ని. మీ సేవ కోసం ఈ call record అవ్వచ్చు." },
      { lang: "hi", label: "हिंदी", text: "नमस्ते, मैं Priya, Sunrise Clinic की AI assistant हूँ। बेहतर सेवा के लिए यह call record हो सकती है।" },
    ],
  },
  consent: {
    label: "Consent & Do-Not-Disturb",
    title: ["Calls only to people", "who expect them."],
    accent: "who expect them.",
    lead: "Before any outbound call, Mitra's compliance check runs. If any rule fails, the call doesn't happen, and the owner sees why in plain words.",
    items: [
      { title: "Consent first", text: "Mitra calls only people who enquired, are existing customers, or opted in. No cold calling lists." },
      { title: "Do-Not-Disturb respected", text: "Numbers registered on DND are checked and skipped for anything promotional." },
      { title: "Opt-out in one sentence", text: "“Don't call me”, “call cheyakandi”, “mat karo call”: Mitra acknowledges politely and the number is suppressed at once." },
      { title: "Allowed hours only", text: "Calls go out only in permitted hours, in the customer's time zone. Anything outside waits for the next window." },
      { title: "Frequency caps", text: "By default no more than 3 attempts a day and 7 a week per person, and no repeated calls to people who don't pick up." },
    ],
  },
  callerId: {
    label: "Trusted Caller ID",
    title: ["Your real number.", "Your real name."],
    accent: "Your real name.",
    lead: "Mitra calls from the business's own number or a dedicated local number registered in its name, with a verified name where the network supports it. No number rotation, no personal SIMs, no SIM boxes: those are spam tactics and we don't use them.",
  },
  data: {
    label: "Your data",
    title: ["Stored in India.", "Kept only as long as needed."],
    accent: "Kept only as long as needed.",
    items: [
      { title: "Stored in India", text: "Recordings, transcripts and customer details are stored in AWS Mumbai and Hyderabad." },
      { title: "Encrypted", text: "Encrypted in transit and at rest. Phone numbers are stored encrypted with a hashed index, never in plain text logs." },
      { title: "Each business sealed off", text: "Every business's data is isolated at the database level, and tested automatically." },
      { title: "Not used to train models", text: "Your calls are never used to train AI models unless you explicitly opt in." },
      { title: "Deleted on schedule", text: "Recordings are kept 90 days by default (you can choose 30–365), transcripts 1 year, billing records 8 years for tax." },
      { title: "Forget a customer", text: "One request erases a customer's recordings, transcripts and memory across the system." },
    ],
  },
  sensitive: {
    label: "Sensitive calls",
    title: ["Knows when to", "hand over."],
    accent: "hand over.",
    items: [
      { title: "Never medical advice", text: "No diagnosis, prescriptions or report reading. Mitra says the doctor or nurse will call and alerts staff." },
      { title: "Emergencies", text: "If a caller mentions chest pain, bleeding, unconsciousness or self-harm, Mitra advises calling 112 immediately and alerts a person." },
      { title: "No promises it can't keep", text: "No guaranteed loan approvals, returns or legal claims. Prices only from facts the business confirmed." },
      { title: "Can't be talked out of its rules", text: "A caller can't change Mitra's instructions mid-call, and actions like refunds need the owner's approval." },
    ],
  },
  controls: {
    label: "Your controls",
    title: ["The owner is", "always in charge."],
    accent: "always in charge.",
    items: [
      { title: "Pause anything, instantly", text: "Pause one employee or all of them from the app or WhatsApp." },
      { title: "Approvals", text: "Exceptions and money matters wait for the owner's tap." },
      { title: "A plain-language log", text: "See every skipped call and the reason: “18 people skipped: on Do-Not-Disturb list.”" },
      { title: "Support access only with permission", text: "Mitra's team can look at your account only when you approve it, and every access is logged." },
    ],
  },
  note: "This page explains how Mitra works in plain language. It isn't legal advice. Rules on telemarketing, caller ID and data protection in India are still being rolled out, and our legal team reviews our defaults before each launch.",
  noteLinks: [
    { label: "Privacy notice", href: "/privacy" },
    { label: "Terms of use", href: "/terms" },
  ],
  cta: { title: ["Hear it say", "“I'm an AI assistant.”"], accent: "“I'm an AI assistant.”", primary: "Call me now", secondary: "How it works" },
};

export const about = {
  meta: {
    title: "About",
    description:
      "Mitra is made in Hyderabad by Viduron AI: AI employees that sound like your best staff, for the clinics, builders and coaching centres India runs on.",
  },
  hero: {
    eyebrow: "About Mitra",
    title: ["Made in Hyderabad,", "for the businesses", "India runs on."],
    accent: "India runs on.",
    sub: "Mitra means friend. We're building the AI employee every small business deserves: one that answers every call, speaks the customer's language and tells the owner the truth.",
  },
  why: {
    label: "Why we started",
    title: ["Every missed call", "is a missed customer."],
    accent: "is a missed customer.",
    paragraphs: [
      "Walk into any clinic, builder's office or coaching centre and you'll see the same thing: a phone that rings while the person who should answer it is busy with someone in front of them. Leads go cold. Patients don't show up. Fees get chased by the owner at 10 PM.",
      "Big companies solve this with call centres. Small businesses can't, and the AI tools that exist are built for English-speaking enterprises, priced by the month and sound like robots. We thought the people who run India's neighbourhoods deserved better.",
    ],
  },
  principles: {
    label: "What we believe",
    title: ["Four rules", "we build by."],
    accent: "we build by.",
    items: [
      { title: "Sound human, be honest", text: "Mitra should sound like your best staff, and always say it's an AI." },
      { title: "Speak like India speaks", text: "Telugu, Hindi and English, mixed the way people really talk. More languages next." },
      { title: "Owners stay in control", text: "Reports on WhatsApp, approvals with a tap, pause any time." },
      { title: "Pay for what you use", text: "No monthly fee, no feature paywalls. If Mitra doesn't talk, you don't pay." },
    ],
  },
  company: {
    label: "The company",
    title: ["A Viduron AI", "product."],
    accent: "product.",
    text: "Mitra is built by Viduron AI, an applied-AI company in Hyderabad. We start with clinics, builders and coaching centres in Telangana and Andhra Pradesh, and grow from there with partner agencies across India.",
    link: "Visit viduronai.in",
    facts: ["Hyderabad, India", "Telugu · Hindi · English", "Data stored in India"],
  },
  cta: { title: ["Hear Mitra", "for yourself."], accent: "for yourself.", primary: "Call me now", secondary: "See pricing" },
};
