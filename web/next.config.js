/** @type {import('next').NextConfig} */
const basePath = process.env.PAGES_BASE_PATH || "";
const nextConfig = {
  reactStrictMode: true,
  output: "export",
  basePath,
  images: { unoptimized: true },
  trailingSlash: true,
};

module.exports = nextConfig;
