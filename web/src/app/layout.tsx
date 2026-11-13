import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import type { ReactNode } from "react";

import { LOCALE } from "@/i18n/request";

import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("app");
  return { title: t("title"), description: t("tagline") };
}

export default async function RootLayout({ children }: { children: ReactNode }) {
  const t = await getTranslations("app");
  return (
    <html lang={LOCALE}>
      <body>
        <header>
          <a href="/">{t("title")}</a> <span className="muted">{t("tagline")}</span>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
