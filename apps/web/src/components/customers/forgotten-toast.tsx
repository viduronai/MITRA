"use client";

import { useEffect } from "react";
import { toast } from "sonner";

/** One confirmation toast after "Forget this customer" redirects back to the list. */
export function ForgottenToast({ message }: { message: string }) {
  useEffect(() => {
    toast.success(message);
    window.history.replaceState(null, "", "/customers");
  }, [message]);
  return null;
}
