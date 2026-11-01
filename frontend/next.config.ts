import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1"],
  // A static site in dist/, served by FastAPI (main.py). trailingSlash makes each page
  // a folder with an index.html, so /chat works with no rewrite rules.
  output: "export",
  distDir: "dist",
  trailingSlash: true,
  turbopack: {
    root: process.cwd(),
  },
  experimental: {
    turbopackMinify: false,
  },
};

export default nextConfig;
