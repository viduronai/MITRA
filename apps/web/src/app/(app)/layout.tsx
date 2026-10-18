import { getTranslations } from "next-intl/server";
import { AppHeader } from "@/components/shell/app-header";
import { BottomNav } from "@/components/shell/bottom-nav";
import { Sidebar } from "@/components/shell/sidebar";
import { getBusiness, getEmployee } from "@/lib/data";
import { employee as mockEmployee } from "@/lib/mock-data";

export default async function AppLayout({ children }: LayoutProps<"/">) {
  const [t, business, employee] = await Promise.all([getTranslations("nav"), getBusiness(), getEmployee()]);

  return (
    <div className="flex min-h-dvh">
      <a
        href="#main"
        className="sr-only z-50 rounded-lg bg-surface px-4 py-3 font-medium shadow-md focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        {t("skip")}
      </a>
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <AppHeader
          businessName={business?.name ?? ""}
          employee={employee && { name: employee.name, status: employee.status }}
          liveCalls={mockEmployee.liveCalls}
        />
        <main
          id="main"
          className="mx-auto w-full max-w-[1200px] flex-1 px-4 pt-6 pb-28 md:px-8 md:pt-8 md:pb-12"
        >
          {children}
        </main>
      </div>
      <BottomNav />
    </div>
  );
}
