import { Phone, Play, Plus, Settings2, Trash2 } from "lucide-react";
import { MockActionButton } from "@/components/mitra/mock-action-button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { DsSection, Specimen } from "./ds-section";

const variants = ["default", "secondary", "ghost", "danger", "link"] as const;
const sizes = ["sm", "default", "lg"] as const;
const sizeLabels: Record<(typeof sizes)[number], string> = { sm: "sm · 40px", default: "default · 48px", lg: "lg · 56px" };

export function Controls() {
  return (
    <>
      <DsSection id="buttons" title="Buttons" description="One primary button per view. Buttons start with a verb. Small sizes keep a 44px tap area.">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {variants.map((variant) => (
            <Specimen key={variant} label={`variant="${variant}"${variant === "default" ? " (primary)" : ""}`}>
              <div className="flex flex-wrap items-center gap-3">
                {sizes.map((size) => (
                  <Button key={size} variant={variant} size={size}>
                    {variant === "danger" ? "Delete routine" : "Start test call"}
                  </Button>
                ))}
              </div>
              <span className="text-[13px] text-text-muted">{sizes.map((size) => sizeLabels[size]).join("  ·  ")}</span>
            </Specimen>
          ))}
          <Specimen label="Icons, states, full-width mobile CTA">
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="secondary">
                <Play aria-hidden />
                Hear sample
              </Button>
              <Button variant="secondary" size="icon" aria-label="Call">
                <Phone aria-hidden />
              </Button>
              <Button variant="ghost" size="icon-sm" aria-label="Settings">
                <Settings2 aria-hidden />
              </Button>
              <Button variant="danger" size="icon" aria-label="Delete">
                <Trash2 aria-hidden />
              </Button>
              <Button disabled>Go live</Button>
            </div>
            <Button size="lg" className="w-full">
              Go live
            </Button>
          </Specimen>
        </div>
      </DsSection>

      <DsSection id="inputs" title="Inputs" description="48px tall, label above, helper text below, inline validation that explains the fix.">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <Specimen label="Default">
            <div className="flex flex-col gap-2">
              <Label htmlFor="ds-name">Business name</Label>
              <Input id="ds-name" placeholder="Sunrise Clinic" />
              <p className="text-[13px] leading-5 text-text-muted">Customers hear this when Priya answers.</p>
            </div>
          </Specimen>
          <Specimen label="Error">
            <div className="flex flex-col gap-2">
              <Label htmlFor="ds-phone">Phone number</Label>
              <Input id="ds-phone" defaultValue="98765" aria-invalid aria-describedby="ds-phone-error" inputMode="tel" />
              <p id="ds-phone-error" className="text-[13px] leading-5 text-danger-fg">
                We couldn&apos;t reach this number. Check it has 10 digits and try again.
              </p>
            </div>
          </Specimen>
          <Specimen label="Disabled">
            <div className="flex flex-col gap-2">
              <Label htmlFor="ds-city">City</Label>
              <Input id="ds-city" defaultValue="Hyderabad" disabled />
            </div>
          </Specimen>
        </div>
      </DsSection>

      <DsSection id="primitives" title="Base components" description="shadcn/ui, restyled to Mitra tokens.">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          <Specimen label="Badge">
            <div className="flex flex-wrap gap-2">
              <Badge>New</Badge>
              <Badge variant="secondary">Soon</Badge>
              <Badge variant="outline">From website</Badge>
              <Badge variant="destructive">Blocked</Badge>
            </div>
          </Specimen>
          <Specimen label="Tabs (max 4)">
            <Tabs defaultValue="overview">
              <TabsList>
                <TabsTrigger value="overview">Overview</TabsTrigger>
                <TabsTrigger value="voice">Voice</TabsTrigger>
                <TabsTrigger value="hours">Hours</TabsTrigger>
              </TabsList>
              <TabsContent value="overview" className="pt-2 text-text-muted">Priya is working.</TabsContent>
              <TabsContent value="voice" className="pt-2 text-text-muted">Warm, Telugu and English.</TabsContent>
              <TabsContent value="hours" className="pt-2 text-text-muted">Every day, 9 am to 9 pm.</TabsContent>
            </Tabs>
          </Specimen>
          <Card>
            <CardHeader>
              <CardTitle>Card</CardTitle>
              <CardDescription>16px radius, 20–24px padding, border first.</CardDescription>
            </CardHeader>
            <CardContent className="text-text-muted">Clickable cards lift 2px on hover.</CardContent>
          </Card>
          <Specimen label="Skeleton (no spinners over 300ms)">
            <div className="flex items-center gap-3">
              <Skeleton className="size-10 rounded-full" />
              <div className="flex flex-1 flex-col gap-2">
                <Skeleton className="h-4 w-3/5" />
                <Skeleton className="h-3 w-2/5" />
              </div>
            </div>
          </Specimen>
          <Specimen label="Avatar · Separator · Tooltip">
            <div className="flex items-center gap-4">
              <Avatar>
                <AvatarFallback>LR</AvatarFallback>
              </Avatar>
              <Separator orientation="vertical" className="h-8" />
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="secondary" size="sm">Hover me</Button>
                </TooltipTrigger>
                <TooltipContent>Tooltips explain, never hide key info.</TooltipContent>
              </Tooltip>
            </div>
          </Specimen>
          <Specimen label="Dialog · Sheet · Menu · Toast">
            <div className="flex flex-wrap gap-3">
              <Dialog>
                <DialogTrigger asChild>
                  <Button variant="secondary" size="sm">Open dialog</Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Pause Priya?</DialogTitle>
                    <DialogDescription>Calls will go to your phone until you turn her back on.</DialogDescription>
                  </DialogHeader>
                  <DialogFooter>
                    <Button variant="secondary">Keep working</Button>
                    <Button>Pause Priya</Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
              <Sheet>
                <SheetTrigger asChild>
                  <Button variant="secondary" size="sm">Open sheet</Button>
                </SheetTrigger>
                <SheetContent side="bottom">
                  <SheetHeader>
                    <SheetTitle>Pick a time</SheetTitle>
                    <SheetDescription>Bottom sheet on mobile; use a dialog on desktop.</SheetDescription>
                  </SheetHeader>
                  <SheetFooter>
                    <Button size="lg" className="w-full">Save time</Button>
                  </SheetFooter>
                </SheetContent>
              </Sheet>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="secondary" size="sm">Open menu</Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent>
                  <DropdownMenuLabel>Priya</DropdownMenuLabel>
                  <DropdownMenuItem>
                    <Play aria-hidden /> Hear sample
                  </DropdownMenuItem>
                  <DropdownMenuItem>
                    <Plus aria-hidden /> Teach something
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem variant="destructive">
                    <Trash2 aria-hidden /> Remove
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
              <MockActionButton toastMessage="Saved. Priya will use this from the next call.">Show toast</MockActionButton>
            </div>
          </Specimen>
        </div>
      </DsSection>
    </>
  );
}
