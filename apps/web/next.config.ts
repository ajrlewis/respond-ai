import type { NextConfig } from "next";

const upstreamApiBase = (process.env.API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000")
  .trim()
  .replace(/\/+$/, "");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${upstreamApiBase}/api/:path*`,
      },
      {
        source: "/auth/:path*",
        destination: `${upstreamApiBase}/auth/:path*`,
      },
    ];
  },
};

export default nextConfig;
