/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Keep production verification from overwriting an active dev server's cache.
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
