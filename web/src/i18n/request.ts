import { getRequestConfig } from "next-intl/server";

import messages from "../../messages/id.json";

/** Bahasa Indonesia only in the slice (spec #29); English strings come later. */
export const LOCALE = "id";

export default getRequestConfig(async () => ({ locale: LOCALE, messages }));
