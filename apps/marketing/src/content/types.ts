/* Shapes shared by every locale's copy. */

export type ScriptLine = { who: "mitra" | "caller"; text: string };
export type Scenario = {
  id: "clinic" | "realestate" | "reminder";
  label: string;
  /** Segment label on narrow phones. */
  short: string;
  business: string;
  language: string;
  duration: string;
  lines: ScriptLine[];
};

export type ChatMessage =
  | { kind: "report"; title: string; rows: [string, string][]; note: string; actions: string[] }
  | { kind: "bot"; text: string; actions?: string[] }
  | { kind: "owner"; text: string }
  | { kind: "voice"; seconds: string; transcript: string };

export type IndustryCard = {
  id: string;
  name: string;
  line: string;
  tasks: string[];
  scenario: Scenario["id"] | null;
  href: string;
};

export type Locale = "en" | "te" | "hi";
