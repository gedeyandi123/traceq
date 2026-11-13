import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

import { API_URL } from "./src/api/url";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const config: NextConfig = {
  // A cited document opens through the same origin: /api/... is the read-only API.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
};

export default withNextIntl(config);
