/*
 * DRAFT legal pages. Based on docs/08-COMPLIANCE-SECURITY.md (DPDP roles,
 * residency, retention). NOT reviewed by counsel: every page carries the
 * "draft — legal review pending" banner until it is.
 */

export type LegalSection = { id: string; title: string; body: string[] };
export type LegalPageCopy = {
  meta: { title: string; description: string };
  eyebrow: string;
  title: string[];
  accent: string;
  updated: string;
  intro: string;
  sections: LegalSection[];
};

export const legalShared = {
  draftLabel: "Draft",
  draft: "Draft — legal review pending. This text explains our intent in plain words and will change before launch. It is not yet a binding notice or contract.",
  tocLabel: "Contents",
  contact: "Questions about this page? Write to us through the WhatsApp link on our home page.",
};

export const privacy: LegalPageCopy = {
  meta: {
    title: "Privacy notice (draft)",
    description: "How Mitra collects, uses, stores and deletes personal data, in plain language. Draft pending legal review.",
  },
  eyebrow: "Privacy notice",
  title: ["Your data,", "plainly."],
  accent: "plainly.",
  updated: "Draft of 20 October 2026",
  intro:
    "Mitra is a product of Viduron AI, Hyderabad. This notice explains what personal data we handle, why, where it is stored and how you can ask us to delete it, in line with India's Digital Personal Data Protection Act, 2023 and its Rules.",
  sections: [
    {
      id: "roles",
      title: "Who is responsible",
      body: [
        "For businesses that use Mitra (for example a clinic or a builder), the business decides why and how its customers are called. Under the DPDP Act the business is the Data Fiduciary and Mitra is its Data Processor, acting only on its instructions under a data processing agreement.",
        "For our own users (business owners, staff and agency partners) and for visitors to this website, Viduron AI is the Data Fiduciary.",
      ],
    },
    {
      id: "what",
      title: "What we collect",
      body: [
        "Website visitors: if you request a demo call, your mobile number, chosen language and business type. We store the number only as a one-way hash plus its last four digits, and delete the request after 30 days.",
        "Business accounts: your name, phone number, business details and the facts you teach Mitra.",
        "Calls handled for a business: the phone number of the person called or calling, call recordings, transcripts, summaries and outcomes (for example an appointment booked).",
      ],
    },
    {
      id: "why",
      title: "Why we use it",
      body: [
        "To place and answer calls a business has asked for, send follow-ups such as WhatsApp confirmations, produce reports for the business, bill for usage and keep the service secure.",
        "We do not sell personal data, and we do not use customers' calls to train AI models unless the business explicitly opts in.",
      ],
    },
    {
      id: "consent",
      title: "Consent and opting out",
      body: [
        "Outbound calls are made only to people with a consent record or an existing relationship with the business. Every call starts by saying it is an AI assistant and that the call may be recorded.",
        "Anyone can say \"don't call me\" during a call; the number is suppressed immediately for that business. Numbers on the Do-Not-Disturb registry are not called for promotional purposes.",
      ],
    },
    {
      id: "where",
      title: "Where it is stored",
      body: [
        "Personal data, recordings, transcripts and search indexes are stored in India (AWS Mumbai and Hyderabad regions), encrypted in transit and at rest.",
        "Some AI model providers may process call audio or text. We prefer India-hosted or zero-retention providers and remove personal details before processing outside India where feasible.",
      ],
    },
    {
      id: "retention",
      title: "How long we keep it",
      body: [
        "Call recordings: 90 days by default (a business can choose 30 to 365 days). Transcripts: 1 year. Billing records: 8 years, as tax law requires. Demo call requests: 30 days.",
      ],
    },
    {
      id: "rights",
      title: "Your rights",
      body: [
        "You can ask to access, correct or erase your personal data, withdraw consent, and nominate someone to act for you. If a business called you through Mitra, you can ask that business or us; we will act on the business's instructions and confirm when data is erased.",
        "You can also complain to the Data Protection Board of India.",
      ],
    },
    {
      id: "security",
      title: "Security and breaches",
      body: [
        "Each business's data is isolated at the database level, access is role-based and logged, and our support team can see an account only with the business's permission. If a breach affects you, we will notify you and the Board as the law requires.",
      ],
    },
  ],
};

export const terms: LegalPageCopy = {
  meta: {
    title: "Terms of use (draft)",
    description: "The rules for using Mitra: accounts, acceptable use, calling rules, billing and liability. Draft pending legal review.",
  },
  eyebrow: "Terms of use",
  title: ["The rules,", "in plain words."],
  accent: "in plain words.",
  updated: "Draft of 20 October 2026",
  intro:
    "These terms are between you and Viduron AI (\"we\"), which makes Mitra. By creating an account or requesting a demo call you agree to them. They will be finalised after legal review.",
  sections: [
    {
      id: "service",
      title: "The service",
      body: [
        "Mitra provides AI employees that answer and place phone calls, send follow-up messages and report to you. Features may change as the product develops; we will tell you about material changes in advance.",
      ],
    },
    {
      id: "account",
      title: "Your account",
      body: [
        "You must be authorised to act for the business you register, keep your login secure and give us accurate information. You are responsible for what your staff do in your account.",
      ],
    },
    {
      id: "calling",
      title: "Calling rules you agree to",
      body: [
        "You will call only people who consented or have an existing relationship with you, for the purposes you configure. You will not use Mitra for promotional calls to numbers on the Do-Not-Disturb registry, for harassment, fraud, debt intimidation, political campaigning or anything unlawful.",
        "Mitra always discloses that it is an AI assistant. You may reword the disclosure but must not remove or disguise it.",
        "The facts you give Mitra (prices, timings, offers) must be accurate. Mitra repeats what you confirm.",
      ],
    },
    {
      id: "billing",
      title: "Billing",
      body: [
        "Mitra is prepaid. You top up a wallet and are charged per second of connected talk-time at your chosen tier's rate (minimum 10 seconds per connected call), plus pass-through extras at cost. Prices exclude GST. Unanswered calls are not charged.",
        "Credits are valid for 12 months from top-up. Bonus credits have no cash value. Refunds of unused paid credits follow the policy published at launch.",
      ],
    },
    {
      id: "data",
      title: "Data",
      body: [
        "You own your business data and your customers' data. We process it on your instructions as described in our Privacy notice and data processing agreement.",
      ],
    },
    {
      id: "availability",
      title: "Availability and limits",
      body: [
        "We work hard to keep Mitra running, but telephony networks and AI systems can fail. Mitra is not an emergency service. To the extent the law allows, our liability is limited to the fees you paid in the three months before a claim.",
      ],
    },
    {
      id: "ending",
      title: "Suspension and ending",
      body: [
        "You can stop using Mitra at any time. We may suspend accounts that break the calling rules or put people at risk, and will tell you why.",
      ],
    },
    {
      id: "law",
      title: "Governing law",
      body: ["These terms are governed by the laws of India, with courts at Hyderabad, Telangana having jurisdiction."],
    },
  ],
};
