import {
  CircleCheckBig,
  Ellipsis,
  House,
  Phone,
  Plug,
  Repeat,
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
  | "approvals"
  | "connect";

export interface NavItem {
  key: NavKey;
  href: string;
  icon: LucideIcon;
}

/** Mobile bottom bar and the top of the desktop sidebar (docs/07 §1). */
export const primaryNav: NavItem[] = [
  { key: "home", href: "/", icon: House },
  { key: "calls", href: "/calls", icon: Phone },
  { key: "team", href: "/team", icon: Users },
  { key: "customers", href: "/customers", icon: UserRound },
  { key: "more", href: "/more", icon: Ellipsis },
];

/** Desktop-only, shown disabled with a "Soon" badge until P2. */
export const upcomingNav: NavItem[] = [
  { key: "routines", href: "/routines", icon: Repeat },
  { key: "approvals", href: "/approvals", icon: CircleCheckBig },
  { key: "connect", href: "/connect", icon: Plug },
];

export function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}
