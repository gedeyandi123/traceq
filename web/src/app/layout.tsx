import type { Metadata } from "next";
import localFont from "next/font/local";
import { getTranslations } from "next-intl/server";
import Link from "next/link";
import type { ReactNode } from "react";

import { SessionBar } from "@/components/SessionBar";
import { LOCALE } from "@/i18n/request";

import "./globals.css";
import s from "./layout.module.css";

// Inter (OFL-1.1), Latin subset, served from the build: no request to a font host.
const inter = localFont({
  src: "../../node_modules/@fontsource-variable/inter/files/inter-latin-wght-normal.woff2",
  weight: "100 900",
  display: "swap",
  variable: "--font-inter",
});

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("app");
  return { title: { default: t("title"), template: `%s · ${t("title")}` }, description: t("tagline") };
}

function Mark() {
  return (
    <svg className={s.mark} viewBox="0 0 24 24" aria-hidden="true">
      <rect x="1" y="1" width="22" height="22" rx="5" fill="currentColor" opacity="0.16" />
      <path d="M6 7h7M6 12h4M6 17h7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M15 12l2 2 3.5-4" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default async function RootLayout({ children }: { children: ReactNode }) {
  const t = await getTranslations("app");
  return (
    <html lang={LOCALE} className={inter.variable}>
      <body>
        <header className={s.appbar}>
          <div className={s.appbarInner}>
            <Link href="/" className={s.brand}>
              <Mark />
              <span>{t("title")}</span>
            </Link>
            <span className={s.tagline}>{t("tagline")}</span>
            <div className={s.session}>
              <SessionBar />
            </div>
          </div>
        </header>
        <main className={s.main}>{children}</main>
      </body>
    </html>
  );
}
