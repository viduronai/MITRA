import {
  CircleCheckBig,
  Ellipsis,
  House,
  Megaphone,
  Phone,
  Plug,
  Radio,
  Repeat,
  Sparkles,
  UserRound,
  Users,
  type LucideIcon,
} from "lucide-react";

export type NavKey =
  | "home"
  | "calls"
  | "team"
  | "customers"
  | "more"
  | "routines"
  | "campaigns"
  | "live"
  | "approvals"
  | "ask"
  | "connect";

export interface NavItem {
  key: NavKey;
  href: string;
  icon: LucideIcon;
  /** In the desktop secondary list: live (a link) instead of "Soon". */
  ready?: boolean;
}

/** Mobile bottom bar and the top of the desktop sidebar (docs/07 §1). */
export const primaryNav: NavItem[] = [
  { key: "home", href: "/", icon: House },
  { key: "calls", href: "/calls", icon: Phone },
  { key: "team", href: "/team", icon: Users },
  { key: "customers", href: "/customers", icon: UserRound },
  { key: "more", href: "/more", icon: Ellipsis },
];

/** Desktop-only; items without `ready` show disabled with a "Soon" badge until P2. */
export const upcomingNav: NavItem[] = [
  { key: "routines", href: "/routines", icon: Repeat, ready: true },
  { key: "campaigns", href: "/campaigns", icon: Megaphone, ready: true },
  { key: "live", href: "/live", icon: Radio, ready: true },
  { key: "ask", href: "/ask", icon: Sparkles, ready: true },
  { key: "approvals", href: "/approvals", icon: CircleCheckBig, ready: true },
  { key: "connect", href: "/connect", icon: Plug },
];

export function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}
