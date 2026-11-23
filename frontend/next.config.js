/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export: the Amplify app is a static (WEB) platform, and the
  // page is fully client-side (API calls happen at runtime in the browser).
  output: "export",
};
module.exports = nextConfig;
