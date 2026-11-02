/*
 * /agencies. Wholesale rates: docs/09-ROADMAP-PRICING-METRICS.md §3.3
 * (Smart ₹2.4 · Natural ₹3.6 · Signature ₹4.8; agency sets its own retail price;
 * no platform fee until the white-label domain launches).
 */

import type { TierId } from "../pricing";

export const wholesale: Record<TierId, number> = { smart: 2.4, natural: 3.6, signature: 4.8 };

export const agencies = {
  meta: {
    title: "For agencies: white-label AI calling",
    description:
      "Sell AI calling teams to your clients under your own brand. Wholesale from ₹2.4 a minute, you set the retail price, no platform fee during early access.",
  },
  hero: {
    eyebrow: "Partner programme",
    title: ["Sell AI calling teams", "under your brand."],
    accent: "under your brand.",
    sub: "You already run your clients' ads and leads. Now answer and call those leads too, with AI employees in Telugu, Hindi and English, on your logo, at your price.",
    primary: "Apply to partner",
    secondary: "Work out my margin",
  },
  rates: {
    label: "Wholesale rates",
    title: ["You buy at wholesale.", "You set the price."],
    accent: "You set the price.",
    lead: "Per connected minute, billed per second, excluding GST. No platform fee during early access; a small monthly fee applies only once the white-label domain launches.",
    perMinute: "/ min wholesale",
    retailHint: "Public price ₹{retail}",
  },
  calc: {
    label: "Margin calculator",
    title: ["What you could", "earn each month."],
    accent: "earn each month.",
    clients: "Clients on Mitra",
    minutes: "Talk-minutes per client a month",
    tier: "Voice tier",
    retail: "Your price per minute",
    revenue: "You bill clients",
    cost: "You pay Mitra",
    margin: "Your margin",
    perMonth: "/ month",
    marginPct: "{pct}% margin",
    note: "Estimate before GST. Your clients' unanswered calls are free for you too.",
  },
  brand: {
    label: "White-label",
    title: ["Your logo.", "Your colours."],
    accent: "Your colours.",
    lead: "Clients log in to a console with your name on it. Try it: type your agency name and pick a colour.",
    nameLabel: "Agency name",
    namePlaceholder: "Skyline Digital",
    colorLabel: "Brand colour",
    colors: [
      { name: "Blue", value: "#2f6bff" },
      { name: "Teal", value: "#0f9d8a" },
      { name: "Violet", value: "#7b4dff" },
      { name: "Saffron", value: "#e07a10" },
    ],
    preview: "Console preview",
    client: "Sunrise Dental Clinic",
    today: "Today",
    stats: [
      ["Calls answered", "46"],
      ["Appointments", "19"],
      ["Leads called", "27"],
    ],
    action: "Add AI employee",
    powered: "Powered by Mitra",
  },
  how: {
    label: "How it works",
    title: ["Partnering,", "step by step."],
    accent: "step by step.",
    items: [
      { title: "Apply", text: "Tell us about your agency and clients. We reply within one working day.", note: "Day 1" },
      { title: "Onboard with us", text: "We set up your first two clients together, so you learn the setup on real accounts.", note: "Week 1" },
      { title: "Brand and price", text: "Add your logo and colours, set your retail rates, and invite clients to your console.", note: "Week 2" },
      { title: "Grow", text: "Bill clients your way. We handle voices, telephony, compliance checks and uptime.", note: "Ongoing" },
    ],
  },
  form: {
    label: "Apply",
    title: ["Become a", "Mitra partner."],
    accent: "Mitra partner.",
    lead: "Early access is open to agencies in Telangana and Andhra Pradesh first, then across India.",
    fields: {
      name: "Your name",
      agency: "Agency name",
      city: "City",
      phone: "Mobile number",
      email: "Work email",
      clients: "Clients you could bring",
      message: "Anything we should know? (optional)",
    },
    clientOptions: ["1–5", "6–20", "21–50", "50+"],
    consent: "I agree that Mitra may contact me about the partner programme.",
    submit: "Send application",
    errors: {
      required: "Please fill this in.",
      phone: "Enter a 10-digit Indian mobile number starting with 6, 7, 8 or 9.",
      email: "Enter a valid email address.",
      consent: "Please tick the box so we can contact you.",
    },
    successTitle: "Thanks, {name}.",
    successBody: "We'll reply within one working day on WhatsApp or email.",
    previewNote: "Preview: the partner inbox opens before launch, so this application isn't sent yet.",
    again: "Edit application",
  },
  faq: {
    label: "Questions",
    title: ["Partner", "questions."],
    accent: "questions.",
    items: [
      { q: "Do my clients see the Mitra name?", a: "No. The console, reports and WhatsApp messages carry your brand. A small “Powered by Mitra” line can be hidden on the white-label domain." },
      { q: "Who bills the client?", a: "You do, at whatever rate you set. You top up your partner wallet at wholesale rates and we never contact your clients about billing." },
      { q: "Who handles compliance?", a: "Every call passes Mitra's compliance checks (consent, Do-Not-Disturb, calling hours, AI disclosure). Your clients still agree to the calling rules in our terms." },
      { q: "Is there a minimum commitment?", a: "No minimums during early access. Volume beyond 25,000 minutes a month across your clients gets custom rates." },
    ],
  },
  cta: { title: ["Your brand.", "Mitra's voice."], accent: "Mitra's voice.", primary: "Hear a demo call", secondary: "See public pricing" },
};
