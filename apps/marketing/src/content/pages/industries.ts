/*
 * /clinics, /real-estate, /education. One template, three industries.
 * Guardrails follow docs/08-COMPLIANCE-SECURITY.md §5. Cost examples use the
 * same maths as the /pricing calculator (calls × minutes × 30 days × rate).
 */

import type { ScriptLine } from "../types";

export type IndustryPageCopy = {
  slug: "clinics" | "real-estate" | "education";
  meta: { title: string; description: string };
  hero: { eyebrow: string; title: string[]; accent: string; sub: string; sample: string };
  stats: { value: string; label: string }[];
  jobs: { label: string; title: string[]; accent: string; lead: string; items: { title: string; text: string; note: string }[] };
  call: {
    label: string;
    title: string[];
    accent: string;
    lead: string;
    business: string;
    meta: string;
    lines: ScriptLine[];
    outcomes: string[];
  };
  guardrails: { label: string; title: string[]; accent: string; lead: string; items: { title: string; text: string }[] };
  cost: { label: string; title: string[]; accent: string; calls: number; minutes: number; text: string };
  faq: { q: string; a: string }[];
};

export const industryShared = {
  speakers: { mitra: "Mitra", caller: "Caller" },
  live: "Sample call",
  outcomesLabel: "What happened after the call",
  primary: "Call me now",
  pricingLink: "Open the calculator",
  safetyLink: "How Mitra stays safe",
  faqLabel: "Questions",
  faqTitle: ["Asked by owners", "like you."],
  faqAccent: "like you.",
  costPerMonth: "/ month on Natural",
  costVs: "One telecaller costs about ₹18,000 a month.",
  cta: { title: ["Your phone rings.", "Mitra answers."], accent: "Mitra answers.", secondary: "See pricing" },
};

const clinics: IndustryPageCopy = {
  slug: "clinics",
  meta: {
    title: "AI receptionist for clinics",
    description:
      "Mitra answers every patient call in Telugu, Hindi and English, books and reminds appointments, and never gives medical advice. From ₹3 a minute.",
  },
  hero: {
    eyebrow: "For clinics & hospitals",
    title: ["Every patient call,", "answered."],
    accent: "answered.",
    sub: "Mitra picks up at 7 AM and at 11 PM, books the slot, sends the reminder and tells you who's coming. Your front desk gets to look after the people in the room.",
    sample: "Read a sample call",
  },
  stats: [
    { value: "24×7", label: "Calls answered, including Sundays and lunch hours" },
    { value: "<1s", label: "To pick up. No hold music, no IVR menu" },
    { value: "3", label: "Languages at launch: Telugu, Hindi, English" },
  ],
  jobs: {
    label: "What Mitra does",
    title: ["A receptionist that", "never misses a ring."],
    accent: "never misses a ring.",
    lead: "Set up the jobs you want. Each AI employee does one, well, and reports to you on WhatsApp every evening.",
    items: [
      { title: "Appointment booking", text: "Checks the doctor's real availability, offers two slots, books and confirms on WhatsApp with the address.", note: "Receptionist · Natural" },
      { title: "No-show reminders", text: "Calls the day before, confirms or reschedules, and frees the slot when someone cancels.", note: "Reminder Caller · Smart" },
      { title: "Lab report calls", text: "Tells patients their report is ready and sends a secure link after a date-of-birth or OTP check.", note: "Reminder Caller · Smart" },
      { title: "Follow-up visits", text: "Reminds patients about review visits and vaccinations on the schedule your doctor sets.", note: "Routine · Natural" },
    ],
  },
  call: {
    label: "Hear it",
    title: ["A real booking,", "start to finish."],
    accent: "start to finish.",
    lead: "Telugu and English, the way patients actually talk. Mitra introduces itself as an AI assistant at the start of every call.",
    business: "Sunrise Dental Clinic",
    meta: "Telugu + English · 0:48",
    lines: [
      { who: "mitra", text: "Namaskaram, Sunrise Dental Clinic. I'm Mitra, the clinic's AI assistant. How can I help?" },
      { who: "caller", text: "Doctor garu appointment kavali, tooth pain undi." },
      { who: "mitra", text: "Sorry to hear that. Dr. Kiran has 11:30 today or 5:15 this evening. Which suits you?" },
      { who: "caller", text: "Evening 5:15 okay." },
      { who: "mitra", text: "Booked for 5:15 today. I've sent the address and a reminder on WhatsApp." },
    ],
    outcomes: ["Booked 5:15 PM", "WhatsApp confirmation sent", "Added to tonight's report"],
  },
  guardrails: {
    label: "Guardrails",
    title: ["Helpful.", "Never a doctor."],
    accent: "Never a doctor.",
    lead: "These rules are written into the system, not left to a prompt. Owners can't switch them off by accident.",
    items: [
      { title: "No diagnosis, no prescriptions", text: "Mitra never interprets symptoms, reports or dosages. It says the doctor or nurse will call back, and alerts your staff." },
      { title: "Emergencies go to 112", text: "Words like chest pain, heavy bleeding or unconscious trigger immediate guidance to call 112, a transfer to your staff and an alert to you." },
      { title: "Reports only after a check", text: "Lab reports are shared through a secure link, only after the patient confirms their date of birth or an OTP." },
      { title: "Patient data stays in India", text: "Recordings and transcripts are stored in India, encrypted, and deleted on your retention schedule." },
    ],
  },
  cost: {
    label: "What it costs",
    title: ["A busy clinic,", "in rupees."],
    accent: "in rupees.",
    calls: 40,
    minutes: 2,
    text: "40 connected calls a day, about 2 minutes each, for 30 days.",
  },
  faq: [
    { q: "Can patients still reach a human?", a: "Yes. Mitra transfers to your staff whenever a patient asks, and always for anything medical or urgent." },
    { q: "Does it work with my existing clinic number?", a: "Yes. Patients keep calling your usual number; calls are forwarded to Mitra when you choose, for example after hours or when the desk is busy." },
    { q: "How does Mitra know the doctor's schedule?", a: "You share slots once (or connect your clinic software as integrations arrive). Mitra only offers times that are actually free." },
    { q: "Will patients know they're talking to an AI?", a: "Yes. Every call starts with a short disclosure in the caller's language. It can be reworded, never removed." },
  ],
};

const realEstate: IndustryPageCopy = {
  slug: "real-estate",
  meta: {
    title: "AI lead calling for real estate",
    description:
      "Mitra calls every portal lead within a minute, qualifies budget and location, books site visits and follows up, in Telugu, Hindi and English.",
  },
  hero: {
    eyebrow: "For builders & brokers",
    title: ["Call every lead", "before they cool."],
    accent: "before they cool.",
    sub: "A property-portal lead at 9:40 PM gets a call at 9:41 PM. Mitra asks the right questions, books the site visit and keeps following up until they decide.",
    sample: "Read a sample call",
  },
  stats: [
    { value: "60s", label: "From enquiry to first call, day or night" },
    { value: "100%", label: "Of leads called. None left in a spreadsheet" },
    { value: "3", label: "Languages: Telugu, Hindi, English" },
  ],
  jobs: {
    label: "What Mitra does",
    title: ["Your fastest", "sales caller."],
    accent: "sales caller.",
    lead: "A team of AI employees hands each lead along, so every enquiry gets a call, a visit and a follow-up.",
    items: [
      { title: "Lead qualification", text: "Asks budget, location, configuration and timeline, then tags the lead hot, warm or later.", note: "Lead Caller · Natural" },
      { title: "Site visit booking", text: "Books the visit, shares the location pin on WhatsApp and tells your site executive who's coming.", note: "Visit Coordinator · Natural" },
      { title: "Follow-ups", text: "Calls back after the visit with the answers they asked for, until they say yes or no.", note: "Sales Assistant · Signature" },
      { title: "Payment reminders", text: "Reminds buyers of instalment dates and sends the payment link, politely.", note: "Payment Caller · Smart" },
    ],
  },
  call: {
    label: "Hear it",
    title: ["Enquiry to site visit", "in one call."],
    accent: "in one call.",
    lead: "Hindi and English, with prices only from the facts sheet you approve. Mitra introduces itself as an AI assistant.",
    business: "Greenfield Homes",
    meta: "Hindi + English · 1:12",
    lines: [
      { who: "mitra", text: "Namaste, Greenfield Homes se Mitra bol rahi hoon, AI assistant. Aapne 2BHK ke baare mein poocha tha?" },
      { who: "caller", text: "Haan, Kokapet side. Budget around 85 lakh." },
      { who: "mitra", text: "Kokapet mein 82 lakh ka east-facing 2BHK hai, ready to move. Site visit Saturday ko karein?" },
      { who: "caller", text: "Saturday morning theek hai." },
      { who: "mitra", text: "Saturday 10 baje fix. Ravi aapko gate par milenge. Location WhatsApp kar rahi hoon." },
    ],
    outcomes: ["Qualified: hot lead", "Site visit Sat 10:00", "Ravi notified"],
  },
  guardrails: {
    label: "Guardrails",
    title: ["Accurate,", "every time."],
    accent: "every time.",
    lead: "Real estate runs on trust. Mitra says only what you've confirmed, and calls only people who asked to hear from you.",
    items: [
      { title: "Prices from your sheet only", text: "Prices, availability and offers come from your facts pack or live sheet. If it isn't there, Mitra says someone will confirm." },
      { title: "No legal or RERA claims", text: "Mitra doesn't make promises about approvals, returns or legal status. Those questions go to your team." },
      { title: "Only people who enquired", text: "Outbound calls go to leads with a consent record, at permitted hours, with frequency caps." },
      { title: "Your number, your name", text: "Calls come from your verified business number, so buyers see your name, not an unknown caller." },
    ],
  },
  cost: {
    label: "What it costs",
    title: ["A month of leads,", "in rupees."],
    accent: "in rupees.",
    calls: 60,
    minutes: 3,
    text: "60 connected calls a day, about 3 minutes each, for 30 days.",
  },
  faq: [
    { q: "Can Mitra pick up leads from portals and ads?", a: "Yes. Leads arrive from your forms, portals and ad campaigns; integrations are added as we onboard builders. Until then, a shared sheet works." },
    { q: "What if a buyer asks something Mitra doesn't know?", a: "It says a person will confirm, notes the question, and your team gets it in the WhatsApp report." },
    { q: "Can it call in the evening?", a: "Only within permitted calling hours, and only to people who enquired. Mitra queues the rest for the next allowed window." },
    { q: "Can I choose a premium voice for high-value projects?", a: "Yes. Put your Sales Assistant on Signature and your reminder caller on Smart. Tiers are per employee." },
  ],
};

const education: IndustryPageCopy = {
  slug: "education",
  meta: {
    title: "AI calling for coaching centres & schools",
    description:
      "Mitra answers parents' questions, books demo classes, fills batches and reminds fees politely, in Telugu, Hindi and English. From ₹3 a minute.",
  },
  hero: {
    eyebrow: "For coaching centres & schools",
    title: ["Parents call.", "Mitra has the answer."],
    accent: "has the answer.",
    sub: "Fees, timings, batches, demo classes. Mitra answers in the parent's language, books the demo and follows up, and reminds fee dates without awkwardness.",
    sample: "Read a sample call",
  },
  stats: [
    { value: "24×7", label: "Admission enquiries answered, even during class" },
    { value: "<1s", label: "To pick up during the admission rush" },
    { value: "3", label: "Languages: Telugu, Hindi, English" },
  ],
  jobs: {
    label: "What Mitra does",
    title: ["Your admissions desk,", "always open."],
    accent: "always open.",
    lead: "From the first enquiry to the last instalment, each job has its own AI employee.",
    items: [
      { title: "Admission enquiries", text: "Answers questions on courses, fees, batch timings and faculty from the facts you approve.", note: "Receptionist · Natural" },
      { title: "Demo class booking", text: "Books the demo, confirms on WhatsApp and reminds the parent the evening before.", note: "Visit Coordinator · Natural" },
      { title: "Batch follow-ups", text: "Calls parents after the demo to answer doubts and help them decide before the batch fills.", note: "Sales Assistant · Natural" },
      { title: "Fee reminders", text: "Reminds instalments politely, takes a new date if needed and sends the UPI link.", note: "Payment Caller · Smart" },
    ],
  },
  call: {
    label: "Hear it",
    title: ["A fee reminder", "nobody dreads."],
    accent: "nobody dreads.",
    lead: "Polite, short and useful. Mitra introduces itself as an AI assistant and agrees a new date when a parent needs one.",
    business: "Bright Future Coaching",
    meta: "English · 0:41",
    lines: [
      { who: "mitra", text: "Hello, this is Mitra, the AI assistant from Bright Future Coaching. Is this Mr. Rao, Anjali's father?" },
      { who: "caller", text: "Yes, tell me." },
      { who: "mitra", text: "A quick reminder: the second term instalment of ₹12,000 is due on Friday." },
      { who: "caller", text: "Can I pay on Monday instead?" },
      { who: "mitra", text: "Of course. I've noted Monday and sent the UPI link on WhatsApp. Thank you!" },
    ],
    outcomes: ["New date: Monday", "UPI link sent", "Accounts notified"],
  },
  guardrails: {
    label: "Guardrails",
    title: ["Warm,", "never pushy."],
    accent: "never pushy.",
    lead: "Parents trust you with their children. Mitra keeps that trust.",
    items: [
      { title: "No pressure tactics", text: "No fake deadlines or guaranteed results. Mitra shares facts you approve and lets parents decide." },
      { title: "Fees from your sheet only", text: "Fees, discounts and scholarships come only from your facts pack. Exceptions wait for your approval on WhatsApp." },
      { title: "Calls only at sensible hours", text: "Reminders go out in permitted hours, with caps on how often a family is called." },
      { title: "Opt-outs honoured at once", text: "If a parent says “don't call”, Mitra acknowledges it and that number is suppressed immediately." },
    ],
  },
  cost: {
    label: "What it costs",
    title: ["An admission season,", "in rupees."],
    accent: "in rupees.",
    calls: 50,
    minutes: 2,
    text: "50 connected calls a day, about 2 minutes each, for 30 days.",
  },
  faq: [
    { q: "Can Mitra speak to parents in Telugu and students in English?", a: "Yes. Mitra follows the caller's language and can switch mid-call when people mix languages." },
    { q: "Can it handle the admission-season rush?", a: "Yes. Five calls at the same time by default, raised automatically as volume grows. No busy tone during peak week." },
    { q: "Who approves discounts?", a: "You do. Discount and fee-exception requests come to you on WhatsApp with Approve and Decline buttons." },
    { q: "Do I pay for calls parents don't pick up?", a: "No. You pay only for connected talk-time, billed per second." },
  ],
};

export const industryPages = { clinics, "real-estate": realEstate, education };
