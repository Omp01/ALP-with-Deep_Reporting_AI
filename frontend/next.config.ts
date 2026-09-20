import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Lets a second dev server (for example an end-to-end run) use its own build
  // directory instead of fighting over `.next`.
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
};

export default nextConfig;
