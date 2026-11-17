import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { NotFoundView } from "@/components/NotFoundView";

/** The browser tab reads "<title> · TraceQ" (the root layout's template); translations only, no fetch. */
export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("app"))("notFoundTitle") };
}

/** The 404 of every route, and of a run the API does not know (`notFound()`). The status stays 404. */
export default function NotFound() {
  return <NotFoundView />;
}
