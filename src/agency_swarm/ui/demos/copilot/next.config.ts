import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  env: {
    NEXT_PUBLIC_AG_UI_BACKEND_URL: process.env.NEXT_PUBLIC_AG_UI_BACKEND_URL,
  },
  /* config options here */
};

export default nextConfig;
