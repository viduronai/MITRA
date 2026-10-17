"use client";

import { toast } from "sonner";
import { Button } from "@/components/ui/button";

/**
 * TEMPORARY: stands in for a real action until the API exists — it only
 * confirms with a toast.
 */
export function MockActionButton({
  toastMessage,
  children,
}: {
  toastMessage: string;
  children: React.ReactNode;
}) {
  return (
    <Button variant="secondary" size="sm" onClick={() => toast.success(toastMessage)}>
      {children}
    </Button>
  );
}
