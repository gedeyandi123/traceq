import type { Metadata } from "next";
import localFont from "next/font/local";
import { NextIntlClientProvider } from "next-intl";
import { getMessages, getTranslations } from "next-intl/server";
import type { ReactNode } from "react";

import { LOCALE } from "@/i18n/request";

import "./globals.css";

// Inter (OFL-1.1), Latin subset, from the pinned package and served from the build: no
// request to a font host at build or run time (ADR 0011 / ADR 0014).
const inter = localFont({
  src: "../../node_modules/@fontsource-variable/inter/files/inter-latin-wght-normal.woff2",
  weight: "100 900",
  display: "swap",
  variable: "--font-inter",
});

/** A page's title reads "<screen> · TraceQ"; a page without one reads "TraceQ". */
export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("app");
  return { title: { default: t("title"), template: `%s · ${t("title")}` }, description: t("tagline") };
}

export default async function RootLayout({ children }: { children: ReactNode }) {
  const allMessages = await getMessages();
  const clientMessages = {
    ui: allMessages.ui,
    common: allMessages.common,
    app: allMessages.app,
    runHeader: allMessages.runHeader,
    runs: allMessages.runs,
    signin: allMessages.signin,
  };
  return (
    <html lang={LOCALE} className={inter.variable}>
      <body className="min-h-screen bg-canvas text-ink antialiased">
        <NextIntlClientProvider locale={LOCALE} messages={clientMessages}>
          {children}
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
